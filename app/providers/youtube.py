from __future__ import annotations

import json
import re
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from ytmusicapi import YTMusic, setup as ytmusic_setup
from ytmusicapi.exceptions import YTMusicError, YTMusicServerError, YTMusicUserError
from ytmusicapi.helpers import get_authorization, initialize_headers, sapisid_from_cookie

from .. import browser_cookies

from ..config import MAX_TRACKS, YOUTUBE_AUTH_PATH
from ..matching import AUTO_THRESHOLD, REVIEW_THRESHOLD, build_queries, score_candidates
from ..models import Playlist, Track
from ..storage import (
    get_service_credentials,
    read_json,
    remove_file,
    remove_service_credentials,
    scoped_user_id,
    set_service_credentials,
    write_json,
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

_YT_HOSTS = {
    "music.youtube.com",
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
}
_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_YT_ORIGIN = "https://music.youtube.com"
_SAPISID_KEY = "__Secure-3PAPISID"
_COOKIE_PAIR_RE = re.compile(r"(?:^|;\s*)[A-Za-z0-9_.\-]+=")
_RAW_COOKIE_RE = re.compile(r"(?im)^\s*cookie:\s*(.+)$")
_CURL_COOKIE_RE = re.compile(r"-H\s+[\"']cookie:\s*([^\"']+)[\"']", re.I)
_RAW_AUTHUSER_RE = re.compile(r"(?im)^\s*x-goog-authuser:\s*(\d+)\s*$")


class AccountChoiceRequired(Exception):
    """В cookie несколько аккаунтов Google — нужен явный выбор."""

    def __init__(self, accounts: list[dict[str, Any]]):
        super().__init__("Выберите аккаунт YouTube Music")
        self.accounts = accounts


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _duration_seconds(item: dict[str, Any]) -> int | None:
    seconds = _as_int(item.get("duration_seconds"))
    if seconds is not None:
        return seconds
    raw = item.get("duration")
    if not isinstance(raw, str) or not raw.strip():
        return None
    parts = raw.strip().split(":")
    if not 1 < len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total or None


def parse_youtube_url(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if _PLAYLIST_ID_RE.match(value) and not re.match(r"^https?://", value, re.I):
        return value
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host not in _YT_HOSTS:
        return None
    params = parse_qs(parsed.query)
    list_values = params.get("list") or []
    if list_values and list_values[0]:
        return list_values[0]
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "playlist":
        return parts[1]
    return None


def _thumbnails_url(thumbnails: Any) -> str | None:
    if not isinstance(thumbnails, list) or not thumbnails:
        return None
    best = thumbnails[-1]
    if isinstance(best, dict):
        return clean_url(best.get("url"))
    return None


class YouTubeProvider(SourceProvider, TargetProvider):
    id = "youtube"
    name = "YouTube Music"
    search_workers = 3
    batch_size = 20
    supports_search = True
    auth_required = True

    def __init__(self) -> None:
        self._local = threading.local()
        self._lock = threading.Lock()
        self._generation = 0
        self._gen_lock = threading.Lock()

    def invalidate(self) -> None:
        with self._gen_lock:
            self._generation += 1

    def _headers(self) -> dict[str, Any] | None:
        user_id = scoped_user_id()
        if user_id is not None:
            value = get_service_credentials("youtube").get("headers")
        else:
            value = read_json(YOUTUBE_AUTH_PATH, {})
        return value if isinstance(value, dict) and value else None

    def is_connected(self) -> bool:
        return self._headers() is not None

    def profile(self) -> dict[str, Any] | None:
        profile = get_service_credentials(self.id).get("profile")
        return profile if isinstance(profile, dict) else None

    def _client(self) -> YTMusic:
        headers = self._headers()
        if headers is None:
            raise NotConnectedError(
                self.name,
                "Подключите YouTube Music — вставьте cookie из браузера.",
            )
        with self._gen_lock:
            key = (self._generation, scoped_user_id() or 0)
        clients = getattr(self._local, "clients", None)
        if clients is None:
            clients = {}
            self._local.clients = clients
        client = clients.get(key)
        if client is None:
            try:
                client = YTMusic(auth=headers, language="ru")
            except Exception as exc:  # noqa: BLE001
                raise AuthError(
                    self.name,
                    "Данные авторизации YouTube Music повреждены. Подключите аккаунт заново.",
                ) from exc
            clients[key] = client
        return client

    def _public_client(self) -> YTMusic:
        client = getattr(self._local, "public_client", None)
        if client is None:
            try:
                client = YTMusic(language="ru")
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(
                    "Нет связи с YouTube Music",
                    "Проверьте интернет-соединение и попробуйте снова.",
                ) from exc
            self._local.public_client = client
        return client

    def _handle_error(self, exc: Exception, *, not_found: str | None = None) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, YTMusicUserError):
            message = str(exc).lower()
            if any(word in message for word in ("auth", "cookie", "login", "unauthorized", "403")):
                return AuthError(self.name)
            return ProviderError(
                "YouTube Music отклонил запрос",
                "Проверьте подключение аккаунта и попробуйте снова.",
            )
        if isinstance(exc, YTMusicServerError):
            return RateLimitError(self.name)
        if isinstance(exc, YTMusicError):
            return ProviderError(
                not_found or "YouTube Music вернул ошибку",
                "Попробуйте ещё раз или обновите подключение аккаунта.",
            )
        if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return ProviderError(
                "Нет связи с YouTube Music",
                "Проверьте интернет-соединение и попробуйте снова.",
            )
        return ProviderError("Не удалось обратиться к YouTube Music", "Попробуйте ещё раз.")

    def _map_track(self, item: Any) -> Track | None:
        if not isinstance(item, dict):
            return None
        video_id = item.get("videoId")
        title = item.get("title")
        if not video_id or not title:
            return None
        artists = [
            artist.get("name")
            for artist in item.get("artists") or []
            if isinstance(artist, dict) and artist.get("name")
        ]
        album = item.get("album")
        album_name = album.get("name") if isinstance(album, dict) else None
        duration = _duration_seconds(item)
        return Track(
            id=str(video_id),
            title=title,
            artists=artists,
            album=album_name,
            duration_ms=duration * 1000 if duration is not None else None,
            cover_url=_thumbnails_url(item.get("thumbnails")),
            url=f"https://music.youtube.com/watch?v={video_id}",
            source=self.id,
            explicit=bool(item.get("isExplicit", False)),
        )

    def _map_summary(self, item: dict[str, Any]) -> Playlist:
        playlist_id = item.get("playlistId") or item.get("id") or ""
        count = _as_int(item.get("count")) or 0
        return Playlist(
            id=str(playlist_id),
            service=self.id,
            title=item.get("title") or "Без названия",
            description=None,
            owner=item.get("author"),
            cover_url=_thumbnails_url(item.get("thumbnails")),
            url=f"https://music.youtube.com/playlist?list={playlist_id}" if playlist_id else None,
            track_count=count,
            tracks=[],
        )

    def list_playlists(self) -> list[Playlist]:
        client = self._client()
        try:
            items = client.get_library_playlists(limit=None)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        result: list[Playlist] = []
        for item in items or []:
            if isinstance(item, dict) and (item.get("playlistId") or item.get("id")):
                result.append(self._map_summary(item))
        return result[:200]

    def resolve_url(self, url: str) -> Playlist:
        playlist_id = parse_youtube_url(url)
        if not playlist_id:
            raise ProviderError(
                "Не удалось разобрать ссылку YouTube Music",
                "Нужна ссылка вида music.youtube.com/playlist?list=…",
            )
        if self.is_connected():
            client = self._client()
            try:
                data = client.get_playlist(playlist_id, limit=MAX_TRACKS)
            except Exception as exc:  # noqa: BLE001
                raise self._handle_error(exc, not_found="Плейлист YouTube Music не найден") from exc
        else:
            client = self._public_client()
            try:
                data = client.get_playlist(playlist_id, limit=MAX_TRACKS)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                raise ProviderError(
                    "Нет связи с YouTube Music",
                    "Проверьте интернет-соединение и попробуйте снова.",
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(
                    "Плейлист YouTube Music недоступен без входа",
                    "Возможно, он приватный. Подключите YouTube Music, чтобы открыть его.",
                    fatal=True,
                ) from exc
        if not data:
            raise ProviderError(
                "Плейлист YouTube Music не найден",
                "Проверьте ссылку или доступ к плейлисту.",
            )
        tracks: list[Track] = []
        warnings: list[str] = []
        for item in data.get("tracks") or []:
            converted = self._map_track(item)
            if converted is not None:
                tracks.append(converted)
            if len(tracks) >= MAX_TRACKS:
                warnings.append(f"Плейлист обрезан до {MAX_TRACKS} треков.")
                break
        owner = data.get("author")
        if isinstance(owner, dict):
            owner = owner.get("name")
        declared = _as_int(data.get("trackCount")) or _as_int(data.get("track_count")) or 0
        if declared > len(tracks) and len(tracks) < MAX_TRACKS:
            warnings.append(
                f"YouTube Music отдал {len(tracks)} из {declared} треков — остальные недоступны или скрыты."
            )
        thumbnails = data.get("thumbnails")
        return Playlist(
            id=str(playlist_id),
            service=self.id,
            title=data.get("title") or "Без названия",
            description=normalize_space(data.get("description")) or None,
            owner=owner,
            cover_url=_thumbnails_url(thumbnails),
            url=f"https://music.youtube.com/playlist?list={playlist_id}",
            track_count=max(declared, len(tracks)),
            tracks=tracks,
            warnings=warnings,
        )

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)

    def _search_items(self, query: str, limit: int = 10, filtered: bool = True) -> list[Track]:
        client = self._client()
        if filtered:
            items = client.search(query, filter="songs", limit=limit)
        else:
            items = client.search(query, limit=max(limit, 12))
        tracks: list[Track] = []
        for item in items or []:
            if isinstance(item, dict) and item.get("resultType") not in (None, "song", "video", "album"):
                continue
            converted = self._map_track(item)
            if converted is not None:
                tracks.append(converted)
        return tracks

    def _best_score(self, track: Track, found: dict[str, Track]) -> float:
        best = score_candidates(track, list(found.values()), limit=1)
        return best[0].score if best else 0.0

    def search(self, track: Track) -> list[Track]:
        queries = build_queries(track)
        if not queries:
            return []
        found: dict[str, Track] = {}
        for index, query in enumerate(queries):
            try:
                items = self._search_items(query, limit=10)
            except Exception as exc:  # noqa: BLE001
                raise self._handle_error(exc) from exc
            for item in items:
                found.setdefault(item.id, item)
            if self._best_score(track, found) >= AUTO_THRESHOLD:
                break
            if index < len(queries) - 1:
                time.sleep(0.12)
        if self._best_score(track, found) < REVIEW_THRESHOLD:
            # Бывает, что фильтр songs не видит свежий релиз, а общий поиск
            # находит его первой карточкой.
            try:
                items = self._search_items(queries[0], limit=12, filtered=False)
            except Exception:  # noqa: BLE001
                items = []
            for item in items:
                found.setdefault(item.id, item)
        return list(found.values())[:24]

    def search_query(self, query: str) -> list[Track]:
        value = normalize_space(query)
        if not value:
            return []
        try:
            items = self._search_items(value, limit=10)
            if not items:
                items = self._search_items(value, limit=12, filtered=False)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        return items

    def create_playlist(self, title: str, description: str, options: dict[str, Any]) -> dict[str, Any]:
        client = self._client()
        privacy = str(options.get("privacy") or "PRIVATE").upper()
        if privacy not in {"PRIVATE", "PUBLIC", "UNLISTED"}:
            privacy = "PRIVATE"
        name = normalize_space(title)[:150] or "Перенесённый плейлист"
        desc = (description or "")[:1000]
        try:
            created = client.create_playlist(
                title=name,
                description=desc,
                privacy_status=privacy,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        playlist_id = created
        if isinstance(created, dict):
            playlist_id = created.get("playlistId") or created.get("id")
        if not playlist_id:
            raise ProviderError(
                "YouTube Music не вернул созданный плейлист",
                "Попробуйте ещё раз или проверьте подключение аккаунта.",
            )
        playlist_id = str(playlist_id)
        return {
            "id": playlist_id,
            "url": f"https://music.youtube.com/playlist?list={playlist_id}",
        }

    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        video_ids = [track.id for track in tracks if track.id]
        if not video_ids:
            return
        try:
            result = self._client().add_playlist_items(playlist_id, video_ids, duplicates=False)
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        if isinstance(result, str):
            ok = "SUCCEEDED" in result
        elif isinstance(result, dict):
            ok = "SUCCEEDED" in str(result.get("status", ""))
        else:
            ok = False
        if not ok:
            raise ProviderError(
                "YouTube Music не принял часть треков",
                "Проверьте, что плейлист не был изменён, и повторите.",
            )


_youtube = YouTubeProvider()


def get_provider() -> YouTubeProvider:
    return _youtube


def _clean_cookie(raw: str) -> str:
    value = raw.strip()
    if value.lower().startswith("cookie:"):
        value = value[7:].strip()
    if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.replace('"', "").strip()


def _looks_like_cookie(value: str) -> bool:
    text = value.strip()
    if not text or "\n" in text:
        return False
    lowered = text.lower()
    if lowered.startswith("curl") or text.startswith("{"):
        return False
    return bool(_COOKIE_PAIR_RE.search(text))


def _headers_from_cookie(cookie: str) -> dict[str, str]:
    if _SAPISID_KEY not in cookie:
        raise ProviderError(
            "В cookie нет нужного ключа",
            "Скопируйте значение заголовка cookie целиком — в нём должен быть __Secure-3PAPISID.",
        )
    try:
        sapisid = sapisid_from_cookie(cookie)
    except KeyError as exc:
        raise ProviderError(
            "Не удалось разобрать cookie",
            "Скопируйте значение заголовка cookie ещё раз, не разбивая его на части.",
        ) from exc
    if not sapisid:
        raise ProviderError(
            "Cookie пустые",
            "Похоже, вы не вошли в аккаунт. Войдите на music.youtube.com и скопируйте cookie заново.",
        )
    headers = dict(initialize_headers())
    headers.update(
        {
            "cookie": cookie,
            "origin": _YT_ORIGIN,
            "x-goog-authuser": "0",
            "authorization": get_authorization(f"{sapisid} {_YT_ORIGIN}"),
        }
    )
    return headers


def build_auth_headers(raw: str) -> dict[str, str]:
    """Принимает cookie, JSON с заголовками или cURL/блок заголовков из DevTools."""
    value = (raw or "").strip()
    if not value:
        raise ProviderError(
            "Пустое поле",
            "Вставьте значение заголовка cookie со страницы music.youtube.com.",
        )
    if value.startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProviderError("Не удалось прочитать JSON", "Вставьте cookie или заголовки заново.") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Не удалось прочитать JSON", "Нужен объект с заголовками запроса.")
        headers = {str(key): str(item) for key, item in parsed.items()}
        cookie = headers.get("cookie") or headers.get("Cookie") or ""
        if not cookie:
            raise ProviderError("В JSON нет cookie", "Подойдёт объект с ключами cookie и authorization.")
        if not headers.get("authorization"):
            headers.update(_headers_from_cookie(cookie))
        headers.setdefault("origin", _YT_ORIGIN)
        headers.setdefault("x-goog-authuser", "0")
        return headers
    if _looks_like_cookie(value):
        return _headers_from_cookie(_clean_cookie(value))
    extracted = _CURL_COOKIE_RE.search(value) or _RAW_COOKIE_RE.search(value)
    if extracted and _SAPISID_KEY in extracted.group(1):
        return _headers_from_cookie(_clean_cookie(extracted.group(1)))
    try:
        parsed = json.loads(ytmusic_setup(headers_raw=value))
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(
            "Не удалось разобрать вход",
            "Вставьте значение заголовка cookie из DevTools. cURL или блок заголовков тоже подойдут.",
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError("Не удалось разобрать вход", "Вставьте cookie или заголовки заново.")
    return {str(key): str(item) for key, item in parsed.items()}


def _explicit_authuser(raw: str) -> int | None:
    """Индекс аккаунта, если он явно указан в заголовках. Cookie его не содержит."""
    text = (raw or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return _as_int(parsed.get("x-goog-authuser"))
        return None
    match = _RAW_AUTHUSER_RE.search(text)
    return int(match.group(1)) if match else None


def _account_profile(info: dict[str, Any]) -> dict[str, Any]:
    name = (
        info.get("name")
        or info.get("accountName")
        or info.get("channelHandle")
        or info.get("channelName")
        or "YouTube Music"
    )
    return {
        "name": name,
        "id": info.get("channelId"),
        "avatar": clean_url(info.get("accountPhotoUrl")),
    }


def _find_accounts(
    headers: dict[str, Any], only: str | None = None
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Перебирает аккаунты Google, доступные в этом наборе cookie."""
    browser_auth = str(headers.get("authorization", "")).startswith("SAPISIDHASH")
    if only is not None:
        users = [str(only)]
    else:
        users = ["0", "1", "2", "3"] if browser_auth else [str(headers.get("x-goog-authuser") or "0")]
    found: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    last_error: Exception | None = None
    for user in users:
        trial = dict(headers)
        trial["x-goog-authuser"] = user
        try:
            client = YTMusic(auth=trial, language="ru")
            info = client.get_account_info() or {}
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if isinstance(info, dict) and (info.get("name") or info.get("channelId") or info.get("channelHandle")):
            found.append((user, trial, info))
        elif last_error is None:
            last_error = YTMusicUserError("Пустой профиль аккаунта")
    if not found:
        raise last_error or YTMusicUserError("Не удалось определить аккаунт")
    return found


def _save_account(headers: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    profile = _account_profile(info)
    if scoped_user_id() is not None:
        set_service_credentials("youtube", {"headers": headers, "profile": profile})
    else:
        write_json(YOUTUBE_AUTH_PATH, headers)
        set_service_credentials("youtube", {"profile": profile})
    _youtube.invalidate()
    return profile


def connect_with_headers(raw_headers: str, authuser: int | None = None) -> dict[str, Any]:
    headers = build_auth_headers(raw_headers)
    explicit = authuser if authuser is not None else _explicit_authuser(raw_headers)
    only = str(explicit) if explicit is not None else None
    try:
        accounts = _find_accounts(headers, only=only)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ProviderError(
            "Нет связи с YouTube Music",
            "Проверьте интернет-соединение и попробуйте снова.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        if only is not None:
            raise ProviderError(
                "Этот аккаунт не отвечает",
                "Повторите подключение и выберите аккаунт заново.",
            ) from exc
        raise AuthError(
            "YouTube Music",
            "Вход не подтвердился: cookie не подошли или устарели. Откройте music.youtube.com, "
            "убедитесь, что вы вошли, и скопируйте cookie заново.",
        ) from exc
    if only is None and len(accounts) > 1:
        raise AccountChoiceRequired(
            [{"authuser": int(user), **_account_profile(info)} for user, _trial, info in accounts]
        )
    _user, trial, info = accounts[0]
    return _save_account(trial, info)


def _merge_profile(profile: dict[str, Any]) -> None:
    creds = get_service_credentials("youtube")
    creds["profile"] = profile
    set_service_credentials("youtube", creds)


def _browser_report() -> str:
    parts: list[str] = []
    for item in browser_cookies.scan():
        status = item.get("status")
        label = item.get("label", "браузер")
        if status == "login":
            parts.append(f"{label} — вход найден")
        elif status == "no_youtube":
            parts.append(f"{label} — нет входа в YouTube")
        elif status == "no_login":
            parts.append(f"{label} — никто не вошёл")
        elif status == "error":
            parts.append(f"{label} — {item.get('detail', 'ошибка чтения')}")
    return "; ".join(parts)


def _browser_candidates() -> list[tuple[str, str]]:
    try:
        candidates = browser_cookies.collect_youtube_cookies()
    except browser_cookies.CookieImportError as exc:
        raise ProviderError(
            "Не удалось прочитать cookie из браузера",
            f"{exc}. Вставьте cookie вручную — инструкция в окне подключения.",
        ) from exc
    candidates = [(label, cookie) for label, cookie in candidates if _SAPISID_KEY in cookie]
    if not candidates:
        report = _browser_report()
        raise ProviderError(
            "В браузерах нет входа в YouTube Music",
            (
                f"Проверили: {report}. Войдите на music.youtube.com в браузере на этом компьютере "
                "и попробуйте снова — либо вставьте cookie вручную."
            )
            if report
            else "Войдите на music.youtube.com в браузере на этом компьютере и попробуйте снова.",
        )
    return candidates


def connect_from_browser(label: str | None = None, authuser: int | None = None) -> dict[str, Any]:
    candidates = _browser_candidates()
    if label is not None:
        chosen = next((item for item in candidates if item[0] == label), None)
        if chosen is None:
            raise ProviderError(
                "Этот браузер больше не найден",
                "Повторите поиск входа — возможно, браузер закрылся или профиль переименован.",
            )
        profile = connect_with_headers(chosen[1], authuser=authuser)
        profile["browser"] = chosen[0]
        _merge_profile(profile)
        return profile

    tried: list[str] = []
    accounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label, cookie in candidates:
        tried.append(label)
        try:
            found = _find_accounts(build_auth_headers(cookie))
        except Exception:  # noqa: BLE001
            continue
        for user, _trial, info in found:
            profile = _account_profile(info)
            key = str(profile.get("id") or profile.get("name"))
            if key in seen:
                continue
            seen.add(key)
            accounts.append({"label": label, "authuser": int(user), **profile})
    if not accounts:
        raise ProviderError(
            "Cookie нашлись, но YouTube их не принял",
            f"Проверили: {', '.join(tried)}. Откройте music.youtube.com, проверьте, что вы вошли, "
            "и попробуйте снова — или вставьте cookie вручную.",
        )
    if len(accounts) > 1:
        raise AccountChoiceRequired(accounts)
    entry = accounts[0]
    chosen = next((item for item in candidates if item[0] == entry["label"]), candidates[0])
    profile = connect_with_headers(chosen[1], authuser=entry["authuser"])
    profile["browser"] = chosen[0]
    _merge_profile(profile)
    return profile


def disconnect() -> None:
    if scoped_user_id() is None:
        remove_file(YOUTUBE_AUTH_PATH)
    remove_service_credentials("youtube")
    _youtube.invalidate()
