from __future__ import annotations

import html
import re
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse

from yandex_music import Client
from yandex_music.exceptions import (
    NetworkError,
    NotFoundError,
    TimedOutError,
    UnauthorizedError,
    YandexMusicError,
)

from ..config import MAX_TRACKS, YANDEX_DEVICE_PATH
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
from .base import AuthError, NotConnectedError, ProviderError, SourceProvider, clean_url, normalize_space

_YANDEX_HOST_RE = re.compile(r"(^|\.)music\.yandex\.(ru|com|by|kz|uz)$", re.IGNORECASE)
_UUID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,}$")
_KIND_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cover_url(uri: str | None, size: str = "600x600") -> str | None:
    if not uri:
        return None
    value = uri.replace("%%", size)
    if value.startswith("//"):
        value = "https:" + value
    elif not value.startswith(("http://", "https://")):
        value = "https://" + value
    return clean_url(value)


def _plain_description(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = normalize_space(text.replace("\r", " ").replace("\n", " "))
    return text[:800] or None


def parse_yandex_url(raw: str) -> tuple[str, ...] | None:
    value = (raw or "").strip()
    if not value:
        return None
    if _UUID_RE.match(value) and "/" not in value:
        return ("uuid", value)
    if not re.match(r"^https?://", value, re.I) and re.match(r"^music\.yandex\.", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if not _YANDEX_HOST_RE.search(parsed.hostname or ""):
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if "track" in parts:
        return ("error", "track")
    if "album" in parts and "playlists" not in parts:
        return ("error", "album")
    if len(parts) >= 2 and parts[0] in {"playlists", "playlist"}:
        return ("uuid", parts[1])
    if len(parts) >= 4 and parts[0] == "users" and parts[2] in {"playlists", "playlist"}:
        return ("legacy", parts[1], parts[3])
    return None


class YandexProvider(SourceProvider):
    id = "yandex"
    name = "Яндекс Музыка"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client_cache: tuple[int | None, str | None, Client] | None = None

    def _token(self) -> str | None:
        token = get_service_credentials(self.id).get("token")
        return token if isinstance(token, str) and token else None

    def is_connected(self) -> bool:
        return bool(self._token())

    def profile(self) -> dict[str, Any] | None:
        profile = get_service_credentials(self.id).get("profile")
        return profile if isinstance(profile, dict) else None

    def invalidate(self) -> None:
        with self._lock:
            self._client_cache = None

    def _client(self, require_auth: bool = False) -> Client:
        token = self._token()
        if require_auth and not token:
            raise NotConnectedError(self.name)
        user_id = scoped_user_id()
        with self._lock:
            if self._client_cache and self._client_cache[0] == user_id and self._client_cache[1] == token:
                return self._client_cache[2]
            client = Client(token) if token else Client()
            try:
                if token:
                    client = client.init()
            except UnauthorizedError as exc:
                raise AuthError(self.name) from exc
            except (NetworkError, TimedOutError) as exc:
                raise ProviderError(
                    "Нет связи с Яндекс Музыкой",
                    "Проверьте интернет-соединение и попробуйте снова.",
                ) from exc
            self._client_cache = (user_id, token, client)
            return client

    def _handle_error(self, exc: Exception, *, not_found: str | None = None) -> ProviderError:
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, UnauthorizedError):
            return AuthError(self.name)
        if isinstance(exc, NotFoundError):
            return ProviderError(
                not_found or "Плейлист не найден",
                "Проверьте ссылку. Возможно, плейлист удалён или скрыт владельцем.",
            )
        if isinstance(exc, (NetworkError, TimedOutError)):
            return ProviderError(
                "Нет связи с Яндекс Музыкой",
                "Проверьте интернет-соединение и попробуйте снова.",
            )
        return ProviderError(
            "Яндекс Музыка вернула ошибку",
            "Попробуйте ещё раз. Если ошибка повторяется — обновите подключение аккаунта.",
        )

    def list_playlists(self) -> list[Playlist]:
        client = self._client(require_auth=True)
        try:
            items = client.users_playlists_list()
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        result: list[Playlist] = []
        for playlist in items or []:
            summary = self._to_playlist(playlist, include_tracks=False)
            result.append(summary)
        return result[:200]

    def resolve_url(self, url: str) -> Playlist:
        parsed = parse_yandex_url(url)
        if not parsed:
            raise ProviderError(
                "Не удалось разобрать ссылку на плейлист",
                "Нужна ссылка вида music.yandex.ru/playlists/… или /users/…/playlists/…",
            )
        if parsed[0] == "error":
            what = "трек" if parsed[1] == "track" else "альбом"
            raise ProviderError(
                f"Это ссылка на {what}, а не на плейлист",
                "Откройте плейлист в Яндекс Музыке и скопируйте ссылку из адресной строки.",
            )
        client = self._client(require_auth=False)
        try:
            if parsed[0] == "uuid":
                playlist = client.playlist(parsed[1])
            else:
                playlist = client.users_playlists(parsed[2], user_id=parsed[1])
        except Exception as exc:  # noqa: BLE001
            raise self._handle_error(exc) from exc
        if playlist is None:
            raise ProviderError(
                "Плейлист не найден",
                "Проверьте ссылку. Возможно, плейлист удалён или скрыт владельцем.",
            )
        return self._to_playlist(playlist, include_tracks=True)

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)

    def _to_playlist(self, playlist: Any, include_tracks: bool) -> Playlist:
        warnings: list[str] = []
        raw_tracks = list(playlist.tracks or [])
        if include_tracks and (not raw_tracks or any(item.track is None for item in raw_tracks)):
            try:
                fetched = playlist.fetch_tracks()
                if fetched:
                    raw_tracks = list(fetched)
            except Exception:  # noqa: BLE001
                warnings.append("Не удалось загрузить полный список треков.")
        covers = _cover_url(getattr(playlist, "cover", None).uri if getattr(playlist, "cover", None) else None)
        owner = None
        if playlist.owner is not None:
            owner = (
                getattr(playlist.owner, "display_name", None)
                or getattr(playlist.owner, "name", None)
                or getattr(playlist.owner, "login", None)
            )
        playlist_uuid = getattr(playlist, "playlist_uuid", None)
        owner_login = getattr(playlist.owner, "login", None) if playlist.owner else None
        kind = getattr(playlist, "kind", None)
        if playlist_uuid:
            url = f"https://music.yandex.ru/playlists/{playlist_uuid}"
            playlist_id = str(playlist_uuid)
        elif owner_login and kind is not None:
            url = f"https://music.yandex.ru/users/{owner_login}/playlists/{kind}"
            playlist_id = f"{owner_login}:{kind}"
        else:
            url = None
            playlist_id = str(getattr(playlist, "id", "") or f"yandex-{kind}")

        tracks: list[Track] = []
        if include_tracks:
            for item in raw_tracks:
                track = getattr(item, "track", None)
                if track is None:
                    continue
                converted = self._to_track(track, covers)
                if converted is not None:
                    tracks.append(converted)
                if len(tracks) >= MAX_TRACKS:
                    warnings.append(f"Плейлист обрезан до {MAX_TRACKS} треков.")
                    break

        declared = _as_int(getattr(playlist, "track_count", None))
        count = len(tracks) if include_tracks else (declared or 0)
        return Playlist(
            id=playlist_id,
            service=self.id,
            title=getattr(playlist, "title", None) or "Без названия",
            description=_plain_description(getattr(playlist, "description", None)),
            owner=owner,
            cover_url=covers,
            url=url,
            track_count=count,
            tracks=tracks,
            warnings=warnings,
        )

    def _to_track(self, track: Any, fallback_cover: str | None) -> Track | None:
        track_id = _as_int(getattr(track, "id", None)) or getattr(track, "id", None)
        if track_id is None:
            return None
        title = getattr(track, "title", None)
        if not title:
            return None
        artists = [artist.name for artist in (getattr(track, "artists", None) or []) if getattr(artist, "name", None)]
        if not artists and getattr(track, "ugc_artist_name", None):
            artists = [track.ugc_artist_name]
        albums = getattr(track, "albums", None) or []
        album = albums[0] if albums else None
        album_title = getattr(album, "title", None) if album else None
        album_id = getattr(album, "id", None) if album else None
        url = None
        if album_id is not None:
            url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
        cover = _cover_url(getattr(track, "cover_uri", None)) or fallback_cover
        return Track(
            id=str(track_id),
            title=title,
            artists=[name for name in artists if name],
            album=album_title,
            duration_ms=_as_int(getattr(track, "duration_ms", None)),
            isrc=getattr(track, "isrc", None),
            cover_url=cover,
            url=url,
            source=self.id,
            explicit=bool(getattr(track, "explicit", False)),
        )


_yandex = YandexProvider()


def get_provider() -> YandexProvider:
    return _yandex


def _profile_from_client(client: Client) -> dict[str, Any]:
    try:
        status = client.me
        if callable(status):
            status = status()
    except Exception as exc:  # noqa: BLE001
        raise _yandex._handle_error(exc) from exc
    account = getattr(status, "account", None) if status is not None else None
    if account is None:
        return {}
    return {
        "name": getattr(account, "display_name", None)
        or getattr(account, "full_name", None)
        or getattr(account, "login", None),
        "login": getattr(account, "login", None),
        "uid": getattr(account, "uid", None),
    }


def connect_with_token(token: str) -> dict[str, Any]:
    value = (token or "").strip()
    if value.lower().startswith("oauth "):
        value = value[6:].strip()
    if not value:
        raise ProviderError("Пустой токен", "Вставьте OAuth-токен Яндекс Музыки.")
    try:
        client = Client(value).init()
        profile = _profile_from_client(client)
    except UnauthorizedError as exc:
        raise AuthError("Яндекс Музыка", "Токен не подошёл. Получите новый токен или войдите по коду.") from exc
    except (NetworkError, TimedOutError) as exc:
        raise ProviderError("Нет связи с Яндекс Музыкой", "Проверьте интернет и попробуйте снова.") from exc
    except YandexMusicError as exc:
        raise ProviderError("Не удалось проверить токен", "Попробуйте получить новый токен.") from exc
    set_service_credentials("yandex", {"token": value, "profile": profile})
    _yandex.invalidate()
    return profile


def _device_state() -> dict[str, Any]:
    if scoped_user_id() is not None:
        value = get_service_credentials("yandex_device")
    else:
        value = read_json(YANDEX_DEVICE_PATH, {})
    return value if isinstance(value, dict) else {}


def _save_device_state(state: dict[str, Any]) -> None:
    if scoped_user_id() is not None:
        set_service_credentials("yandex_device", state)
    else:
        write_json(YANDEX_DEVICE_PATH, state)


def _clear_device_state() -> None:
    if scoped_user_id() is not None:
        remove_service_credentials("yandex_device")
    else:
        remove_file(YANDEX_DEVICE_PATH)


def start_device_flow() -> dict[str, Any]:
    client = Client()
    try:
        code = client.request_device_code(device_name="TuneBridge")
    except (NetworkError, TimedOutError) as exc:
        raise ProviderError("Нет связи с Яндексом", "Проверьте интернет и попробуйте снова.") from exc
    except YandexMusicError as exc:
        raise ProviderError(
            "Не удалось начать вход в Яндекс Музыку",
            "Попробуйте позже или вставьте токен вручную.",
        ) from exc
    _save_device_state(
        {
            "device_code": code.device_code,
            "user_code": code.user_code,
            "verification_url": code.verification_url,
            "interval": code.interval,
            "expires_at": time.time() + max(60, int(code.expires_in or 300)),
        }
    )
    return {
        "user_code": code.user_code,
        "verification_url": code.verification_url,
        "expires_in": code.expires_in,
        "interval": code.interval,
    }


def poll_device_flow() -> dict[str, Any]:
    data = _device_state()
    if not data.get("device_code"):
        raise ProviderError("Вход не начат", "Нажмите «Получить код» ещё раз.")
    if float(data.get("expires_at", 0)) < time.time():
        _clear_device_state()
        raise ProviderError("Код устарел", "Получите новый код и подтвердите вход.")
    try:
        token = Client().poll_device_token(data["device_code"])
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "expired" in message:
            _clear_device_state()
            raise ProviderError("Код устарел", "Получите новый код и подтвердите вход.") from exc
        if "denied" in message:
            _clear_device_state()
            raise ProviderError("Вход отменён", "Попробуйте снова и подтвердите доступ.") from exc
        raise ProviderError(
            "Не удалось завершить вход",
            "Попробуйте ещё раз или вставьте токен вручную.",
        ) from exc
    if token is None:
        return {"status": "pending"}
    profile = connect_with_token(token.access_token)
    _clear_device_state()
    return {"status": "connected", "profile": profile}


def disconnect() -> None:
    remove_service_credentials("yandex")
    _clear_device_state()
    _yandex.invalidate()
