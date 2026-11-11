from __future__ import annotations

import json
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests
import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import CacheFileHandler, SpotifyPKCE

from .. import credentials
from ..config import MAX_TRACKS, SPOTIFY_CACHE_PATH, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES
from ..matching import AUTO_THRESHOLD, build_queries, score_candidates
from ..models import Playlist, Track
from ..storage import (
    get_service_credentials,
    remove_file,
    remove_service_credentials,
    scoped_user_id,
    set_service_credentials,
)
from .base import (
    AuthError,
    NotConnectedError,
    ProviderError,
    RateLimitError,
    SourceProvider,
    TargetProvider,
    clean_url,
    normalize_space,
)

_SPOTIFY_URL_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?playlist/|spotify:playlist:)([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9]{16,64}$")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_EMBED_LIMIT = 100
_EMBED_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_pending_lock = threading.Lock()
_pending_oauth: dict[str, tuple[int | None, SpotifyPKCE]] = {}
_PENDING_LIMIT = 20


class ScopedCacheHandler(CacheHandler):
    """Keeps the Spotify token in the encrypted per-user store instead of a file."""

    def __init__(self, user_id: int):
        self._user_id = int(user_id)

    def get_cached_token(self) -> dict[str, Any] | None:
        return credentials.load(self._user_id, "spotify_token")

    def save_token_to_cache(self, token_info: dict[str, Any]) -> None:
        credentials.save(self._user_id, "spotify_token", dict(token_info))


def _cache_handler() -> CacheHandler:
    user_id = scoped_user_id()
    if user_id is not None:
        return ScopedCacheHandler(user_id)
    return CacheFileHandler(cache_path=str(SPOTIFY_CACHE_PATH))


def _clear_token_cache() -> None:
    user_id = scoped_user_id()
    if user_id is not None:
        credentials.delete(user_id, "spotify_token")
    else:
        remove_file(SPOTIFY_CACHE_PATH)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_spotify_url(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    match = _SPOTIFY_URL_RE.search(value)
    if match and _SPOTIFY_ID_RE.match(match.group(1)):
        return match.group(1)
    if _SPOTIFY_ID_RE.match(value):
        return value
    return None


def _embed_cover(entity: dict[str, Any]) -> str | None:
    cover = entity.get("coverArt") or {}
    sources = cover.get("sources") if isinstance(cover, dict) else None
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict) and source.get("url"):
                return clean_url(source["url"])
    visual = entity.get("visualIdentity") or {}
    images = visual.get("image") if isinstance(visual, dict) else None
    if isinstance(images, list):
        for image in images:
            url = image.get("url") if isinstance(image, dict) else None
            if url:
                return clean_url(url)
    return None


def _playlist_from_embed(entity: dict[str, Any], playlist_id: str) -> Playlist:
    cover = _embed_cover(entity)
    items = entity.get("trackList") or []
    tracks: list[Track] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "")
        if not uri.startswith("spotify:track:"):
            continue
        track_id = uri.rsplit(":", 1)[-1]
        if not track_id:
            continue
        artists = [name.strip() for name in str(item.get("subtitle") or "").split(",") if name.strip()]
        duration = _as_int(item.get("duration"))
        tracks.append(
            Track(
                id=track_id,
                title=item.get("title") or "Без названия",
                artists=artists,
                duration_ms=duration,
                cover_url=cover,
                url=f"https://open.spotify.com/track/{track_id}",
                source="spotify",
                explicit=bool(item.get("isExplicit", False)),
            )
        )
    warnings: list[str] = []
    if len(items) >= _EMBED_LIMIT:
        warnings.append(
            "Spotify отдаёт без входа до 100 треков. Подключите аккаунт, чтобы перенести плейлист целиком."
        )
    owner = normalize_space(entity.get("subtitle")) or None
    return Playlist(
        id=playlist_id,
        service="spotify",
        title=normalize_space(entity.get("title") or entity.get("name")) or "Без названия",
        description=None,
        owner=owner,
        cover_url=cover,
        url=f"https://open.spotify.com/playlist/{playlist_id}",
        track_count=len(tracks),
        tracks=tracks,
        warnings=warnings,
    )


def _fetch_public_playlist(playlist_id: str) -> Playlist:
    url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": _EMBED_UA, "Accept-Language": "ru,en;q=0.8"})
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ProviderError(
            "Нет связи со Spotify",
            "Проверьте интернет-соединение и попробуйте снова.",
        ) from exc
    if response.status_code == 404:
        raise ProviderError(
            "Плейлист Spotify недоступен без входа",
            "Возможно, он приватный. Подключите аккаунт Spotify, чтобы открыть его.",
            fatal=True,
        )
    if response.status_code == 429:
        raise RateLimitError("Spotify")
    if not response.ok:
        raise ProviderError(
            "Spotify вернул ошибку",
            "Попробуйте ещё раз. Если ошибка повторяется — подключите аккаунт Spotify.",
        )
    html = response.content.decode("utf-8", errors="replace")
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise ProviderError(
            "Spotify вернул неожиданный ответ",
            "Попробуйте ещё раз или подключите аккаунт Spotify.",
        )
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ProviderError("Spotify вернул неожиданный ответ", "Попробуйте ещё раз.") from exc
    entity = (
        ((payload.get("props") or {}).get("pageProps") or {})
        .get("state", {})
        .get("data", {})
        .get("entity")
    )
    if not isinstance(entity, dict) or entity.get("type") != "playlist":
        raise ProviderError(
            "Плейлист Spotify недоступен без входа",
            "Возможно, он приватный. Подключите аккаунт Spotify, чтобы открыть его.",
            fatal=True,
        )
    return _playlist_from_embed(entity, playlist_id)


class SpotifyProvider(SourceProvider, TargetProvider):
    id = "spotify"
    name = "Spotify"
    search_workers = 4
    batch_size = 100
    supports_search = True
    auth_required = True

    def __init__(self) -> None:
        self._local = threading.local()
        self._generation = 0
        self._gen_lock = threading.Lock()

    def invalidate(self) -> None:
        with self._gen_lock:
            self._generation += 1

    def _credentials(self) -> dict[str, Any]:
        return get_service_credentials(self.id)

    def client_id(self) -> str | None:
        value = self._credentials().get("client_id")
        return value if isinstance(value, str) and value else None

    def is_connected(self) -> bool:
        if not self.client_id():
            return False
        user_id = scoped_user_id()
        if user_id is not None:
            return credentials.load(user_id, "spotify_token") is not None
        return SPOTIFY_CACHE_PATH.exists()

    def profile(self) -> dict[str, Any] | None:
        profile = self._credentials().get("profile")
        return profile if isinstance(profile, dict) else None

    def _pkce(self) -> SpotifyPKCE:
        client_id = self.client_id()
        if not client_id:
            raise NotConnectedError(
                self.name,
                "Укажите Client ID приложения Spotify и подключите аккаунт.",
            )
        return SpotifyPKCE(
            client_id=client_id,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope=SPOTIFY_SCOPES,
            cache_handler=_cache_handler(),
            open_browser=False,
        )

    def _client(self) -> spotipy.Spotify:
        with self._gen_lock:
            key = (self._generation, scoped_user_id() or 0)
        clients = getattr(self._local, "clients", None)
        if clients is None:
            clients = {}
            self._local.clients = clients
        client = clients.get(key)
        if client is None:
            client = spotipy.Spotify(
                auth_manager=self._pkce(),
                requests_timeout=20,
                retries=3,
                status_retries=3,
                backoff_factor=0.4,
            )
            clients[key] = client
        return client

    def _handle_error(self, exc: Exception, *, not_found: str | None = None) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, SpotifyException):
            status = getattr(exc, "http_status", None)
            if status == 401:
                return AuthError(self.name)
            if status == 403:
                return ProviderError(
                    "Spotify ограничил доступ",
                    "Проверьте, что аккаунт добавлен в приложение Spotify (Users and Access) и имеет нужные права.",
                )
            if status == 404:
                return ProviderError(
                    not_found or "Плейлист Spotify не найден",
                    "Проверьте ссылку или доступ к плейлисту.",
                )
            if status == 429:
                return RateLimitError(self.name)
            return ProviderError(
                "Spotify вернул ошибку",
                "Повторите попытку через минуту.",
            )
        if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return ProviderError(
                "Нет связи со Spotify",
                "Проверьте интернет-соединение и попробуйте снова.",
            )
        return ProviderError("Не удалось обратиться к Spotify", "Попробуйте ещё раз.")

    def _map_track(self, item: Any) -> Track | None:
        if not isinstance(item, dict):
            return None
        if item.get("is_local"):
            return None
        track_id = item.get("id")
        if not track_id:
            return None
        artists = [artist.get("name") for artist in item.get("artists") or [] if artist.get("name")]
        album = item.get("album") or {}
        images = album.get("images") or []
        cover = clean_url(images[0].get("url")) if images else None
        external = item.get("external_urls") or {}
        return Track(
            id=str(track_id),
            title=item.get("name") or "Без названия",
            artists=artists,
            album=album.get("name"),
            duration_ms=_as_int(item.get("duration_ms")),
            isrc=(item.get("external_ids") or {}).get("isrc"),
            cover_url=cover,
            url=clean_url(external.get("spotify")),
            source=self.id,
            explicit=bool(item.get("explicit", False)),
        )

    def _map_playlist(self, item: dict[str, Any]) -> Playlist:
        images = item.get("images") or []
        cover = clean_url(images[0].get("url")) if images else None
        owner = (item.get("owner") or {}).get("display_name")
        external = item.get("external_urls") or {}
        tracks_info = item.get("tracks") or {}
        total = _as_int(tracks_info.get("total")) or 0
        return Playlist(
            id=str(item.get("id") or ""),
            service=self.id,
            title=item.get("name") or "Без названия",
            description=normalize_space(item.get("description")) or None,
            owner=owner,
            cover_url=cover,
            url=clean_url(external.get("spotify")),
            track_count=total,
            tracks=[],
        )

    def list_playlists(self) -> list[Playlist]:
        if not self.is_connected():
            raise NotConnectedError(self.name)
        client = self._client()
        result: list[Playlist] = []
        offset = 0
        try:
            while offset < 200:
                page = client.current_user_playlists(limit=50, offset=offset)
                items = page.get("items") or []
                for item in items:
                    if isinstance(item, dict):
                        result.append(self._map_playlist(item))
                if not page.get("next") or not items:
                    break
                offset += len(items)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        return result

    def resolve_url(self, url: str) -> Playlist:
        playlist_id = parse_spotify_url(url)
        if not playlist_id:
            raise ProviderError(
                "Не удалось разобрать ссылку на плейлист Spotify",
                "Нужна ссылка вида open.spotify.com/playlist/…",
            )
        if self.is_connected():
            try:
                return self._resolve_authenticated(playlist_id)
            except AuthError:
                pass
        return _fetch_public_playlist(playlist_id)

    def _resolve_authenticated(self, playlist_id: str) -> Playlist:
        client = self._client()
        try:
            meta = client.playlist(playlist_id)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        if not meta:
            raise ProviderError("Плейлист Spotify не найден", "Проверьте ссылку.")
        playlist = self._map_playlist(meta)
        tracks: list[Track] = []
        offset = 0
        warnings: list[str] = []
        try:
            while len(tracks) < MAX_TRACKS:
                page = client.playlist_items(playlist_id, limit=50, offset=offset, additional_types=("track",))
                items = page.get("items") or []
                for item in items:
                    track_data = item.get("track") if isinstance(item, dict) else None
                    converted = self._map_track(track_data)
                    if converted is not None:
                        tracks.append(converted)
                if not page.get("next") or not items:
                    break
                offset += len(items)
        except Exception as exc:  # noqa: BLE001
            if not tracks:
                raise self._handle_error(exc) from exc
            warnings.append("Не удалось загрузить весь список треков Spotify.")
        if len(tracks) >= MAX_TRACKS:
            warnings.append(f"Плейлист обрезан до {MAX_TRACKS} треков.")
        playlist.tracks = tracks
        playlist.warnings = warnings
        if playlist.track_count < len(tracks):
            playlist.track_count = len(tracks)
        return playlist

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)

    def _search_items(self, query: str, limit: int = 8) -> list[Track]:
        client = self._client()
        result = client.search(q=query, type="track", limit=limit)
        items = ((result or {}).get("tracks") or {}).get("items") or []
        tracks: list[Track] = []
        for item in items:
            converted = self._map_track(item)
            if converted is not None:
                tracks.append(converted)
        return tracks

    def search(self, track: Track) -> list[Track]:
        queries = build_queries(track)
        if not queries:
            return []
        found: dict[str, Track] = {}
        for index, query in enumerate(queries):
            try:
                items = self._search_items(query, limit=8)
            except Exception as exc:  # noqa: BLE001
                raise self._handle_error(exc) from exc
            for item in items:
                found.setdefault(item.id, item)
            best = score_candidates(track, list(found.values()), limit=1)
            if best and best[0].score >= AUTO_THRESHOLD:
                break
            if index < len(queries) - 1:
                time.sleep(0.08)
        return list(found.values())[:24]

    def search_query(self, query: str) -> list[Track]:
        value = normalize_space(query)
        if not value:
            return []
        try:
            return self._search_items(value, limit=10)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc

    def create_playlist(self, title: str, description: str, options: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected():
            raise NotConnectedError(self.name)
        client = self._client()
        public = bool(options.get("public", True))
        name = normalize_space(title)[:100] or "Перенесённый плейлист"
        desc = (description or "")[:300]
        try:
            created = client.current_user_playlist_create(name=name, public=public, description=desc)
        except SpotifyException as exc:
            if getattr(exc, "http_status", None) not in {404, 405}:
                raise self._handle_error(exc) from exc
            try:
                profile = client.me()
                created = client.user_playlist_create(
                    user_id=profile["id"],
                    name=name,
                    public=public,
                    description=desc,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                raise self._handle_error(fallback_exc) from fallback_exc
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        if not created or not created.get("id"):
            raise ProviderError("Spotify не вернул созданный плейлист", "Попробуйте ещё раз.")
        return {
            "id": created["id"],
            "url": clean_url((created.get("external_urls") or {}).get("spotify")),
        }

    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        uris = [f"spotify:track:{track.id}" for track in tracks if track.id]
        if not uris:
            return
        try:
            self._client().playlist_add_items(playlist_id, uris)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc


_spotify = SpotifyProvider()


def get_provider() -> SpotifyProvider:
    return _spotify


def set_client_id(client_id: str) -> str:
    value = (client_id or "").strip()
    if not _CLIENT_ID_RE.match(value):
        raise ProviderError(
            "Неверный Client ID",
            "Скопируйте Client ID приложения из Spotify Developer Dashboard.",
        )
    creds = get_service_credentials("spotify")
    if creds.get("client_id") != value:
        _clear_token_cache()
        set_service_credentials("spotify", {"client_id": value})
        _spotify.invalidate()
    return value


def start_oauth() -> str:
    provider = _spotify
    if not provider.client_id():
        raise NotConnectedError(
            "Spotify",
            "Сначала укажите Client ID приложения Spotify.",
        )
    pkce = provider._pkce()
    state = secrets.token_urlsafe(20)
    with _pending_lock:
        if len(_pending_oauth) >= _PENDING_LIMIT:
            _pending_oauth.pop(next(iter(_pending_oauth)), None)
        _pending_oauth[state] = (scoped_user_id(), pkce)
    return pkce.get_authorize_url(state=state)


def finish_oauth(state: str, code: str) -> dict[str, Any]:
    with _pending_lock:
        pending = _pending_oauth.pop(state, None)
    if pending is None or pending[0] != scoped_user_id():
        raise ProviderError(
            "Сессия подключения Spotify истекла",
            "Начните подключение заново.",
        )
    pkce = pending[1]
    try:
        pkce.get_access_token(code, check_cache=False)
        profile_data = spotipy.Spotify(auth_manager=pkce).me()
    except Exception as exc:  # noqa: BLE001
        raise _spotify._handle_error(exc) from exc
    images = profile_data.get("images") or []
    profile = {
        "name": profile_data.get("display_name") or profile_data.get("id"),
        "id": profile_data.get("id"),
        "avatar": clean_url(images[0].get("url")) if images else None,
    }
    creds = get_service_credentials("spotify")
    creds["profile"] = profile
    set_service_credentials("spotify", creds)
    _spotify.invalidate()
    return profile


def disconnect() -> None:
    _clear_token_cache()
    creds = get_service_credentials("spotify")
    creds.pop("profile", None)
    if creds.get("client_id"):
        set_service_credentials("spotify", {"client_id": creds["client_id"]})
    else:
        remove_service_credentials("spotify")
    _spotify.invalidate()
