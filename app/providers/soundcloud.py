from __future__ import annotations

import html
import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests

from ..config import MAX_TRACKS
from ..models import Playlist, Track
from .base import ProviderError, RateLimitError, SourceProvider, clean_url, normalize_space

_SOUNDCLOUD_HOSTS = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}
_SHORT_HOSTS = {"on.soundcloud.com", "snd.sc", "www.snd.sc"}
_CLIENT_ID_RE = re.compile(r"client_id['\"]?\s*[=:]\s*['\"]?([A-Za-z0-9]{20,40})")
_ASSET_RE = re.compile(r'<script[^>]+src="([^"]+\.js)"')
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ru,en;q=0.8", "Referer": "https://soundcloud.com/"}
_CLIENT_ID_TTL = 6 * 60 * 60
_client_lock = threading.Lock()
_client_cache: tuple[float, str] | None = None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cover_url(value: str | None) -> str | None:
    if not value:
        return None
    return clean_url(re.sub(r"-(large|t\d+x\d+|crop)\.(jpg|jpeg|png)$", "-t500x500.\\2", value))


def _plain_description(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = normalize_space(text.replace("\r", " ").replace("\n", " "))
    return text[:800] or None


def parse_soundcloud_url(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if not re.match(r"^https?://", value, re.I):
        host_guess = value.split("/", 1)[0].lower()
        if host_guess in _SOUNDCLOUD_HOSTS or host_guess in _SHORT_HOSTS:
            value = "https://" + value
        else:
            return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in _SHORT_HOSTS:
        return value
    if host not in _SOUNDCLOUD_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[1] == "sets":
        return f"https://soundcloud.com/{parts[0]}/sets/{parts[2]}"
    return None


def _invalidate_client_id() -> None:
    global _client_cache
    with _client_lock:
        _client_cache = None


def _extract_client_id() -> str:
    global _client_cache
    now = time.time()
    with _client_lock:
        if _client_cache and now - _client_cache[0] < _CLIENT_ID_TTL:
            return _client_cache[1]

    try:
        response = requests.get("https://soundcloud.com/discover", timeout=20, headers=_HEADERS)
        response.raise_for_status()
        page = response.content.decode("utf-8", errors="replace")
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ProviderError("Нет связи с SoundCloud", "Проверьте интернет-соединение и попробуйте снова.") from exc
    except requests.exceptions.RequestException as exc:
        raise ProviderError("SoundCloud временно недоступен", "Попробуйте ещё раз через минуту.") from exc

    candidates: set[str] = set(_CLIENT_ID_RE.findall(page))
    if not candidates:
        assets = [src for src in _ASSET_RE.findall(page) if "sndcdn.com/assets/" in src]
        for src in assets[-12:]:
            try:
                script = requests.get(src, timeout=15, headers=_HEADERS)
                if not script.ok:
                    continue
                candidates |= set(_CLIENT_ID_RE.findall(script.content.decode("utf-8", errors="replace")))
            except requests.exceptions.RequestException:
                continue
            if candidates:
                break
    if not candidates:
        raise ProviderError(
            "SoundCloud временно недоступен",
            "Не удалось получить ключ доступа. Попробуйте ещё раз через минуту.",
        )
    client_id = sorted(candidates, key=len, reverse=True)[0]
    with _client_lock:
        _client_cache = (now, client_id)
    return client_id


def _api(path: str, params: dict[str, Any], *, retry: bool = True) -> Any:
    query = dict(params)
    query["client_id"] = _extract_client_id()
    try:
        response = requests.get(f"https://api-v2.soundcloud.com{path}", params=query, timeout=25, headers=_HEADERS)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ProviderError("Нет связи с SoundCloud", "Проверьте интернет-соединение и попробуйте снова.") from exc
    if response.status_code in {401, 403} and retry:
        _invalidate_client_id()
        return _api(path, params, retry=False)
    if response.status_code == 404:
        raise ProviderError("Плейлист SoundCloud не найден", "Проверьте ссылку — возможно, он удалён или скрыт.")
    if response.status_code == 429:
        raise RateLimitError("SoundCloud")
    if not response.ok:
        raise ProviderError("SoundCloud вернул ошибку", "Попробуйте ещё раз через минуту.")
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("SoundCloud вернул неожиданный ответ", "Попробуйте ещё раз.") from exc


def _map_track(item: Any, fallback_cover: str | None) -> Track | None:
    if not isinstance(item, dict):
        return None
    track_id = item.get("id")
    title = normalize_space(item.get("title"))
    if track_id is None or not title:
        return None
    user = item.get("user") or {}
    publisher = item.get("publisher_metadata") or {}
    artist = normalize_space(publisher.get("artist")) or normalize_space(user.get("username"))
    duration = _as_int(item.get("duration"))
    return Track(
        id=str(track_id),
        title=title,
        artists=[artist] if artist else [],
        album=normalize_space(item.get("genre")) or None,
        duration_ms=duration if duration and duration > 0 else None,
        isrc=normalize_space(publisher.get("isrc")) or None,
        cover_url=_cover_url(item.get("artwork_url")) or fallback_cover,
        url=clean_url(item.get("permalink_url")),
        source="soundcloud",
        explicit=bool(publisher.get("explicit", False)),
    )


class SoundCloudProvider(SourceProvider):
    id = "soundcloud"
    name = "SoundCloud"

    def list_playlists(self) -> list[Playlist]:
        raise ProviderError(
            "SoundCloud не требует входа",
            "Откройте публичный плейлист по ссылке — аккаунт не нужен.",
        )

    def resolve_url(self, url: str) -> Playlist:
        value = parse_soundcloud_url(url)
        if not value:
            raise ProviderError(
                "Не удалось разобрать ссылку SoundCloud",
                "Нужна ссылка вида soundcloud.com/…/sets/…",
            )
        if urlparse(value).hostname in _SHORT_HOSTS:
            try:
                redirect = requests.get(value, timeout=15, headers=_HEADERS, allow_redirects=True)
                value = redirect.url or value
            except requests.exceptions.RequestException:
                raise ProviderError(
                    "Не удалось открыть короткую ссылку SoundCloud",
                    "Проверьте интернет и попробуйте полную ссылку из адресной строки.",
                )
        data = _api("/resolve", {"url": value})
        if not isinstance(data, dict):
            raise ProviderError("SoundCloud вернул неожиданный ответ", "Попробуйте ещё раз.")
        kind = data.get("kind")
        if kind == "track":
            raise ProviderError(
                "Это ссылка на трек, а не на плейлист",
                "Откройте плейлист в SoundCloud и скопируйте ссылку на него.",
            )
        if kind != "playlist":
            raise ProviderError(
                "Это не плейлист SoundCloud",
                "Нужна ссылка вида soundcloud.com/…/sets/…",
            )

        cover = _cover_url(data.get("artwork_url"))
        declared = _as_int(data.get("track_count")) or 0
        raw_tracks = data.get("tracks") or []
        tracks: list[Track] = []
        pending: list[str] = []
        for item in raw_tracks:
            converted = _map_track(item, cover)
            if converted is not None:
                tracks.append(converted)
            elif isinstance(item, dict) and item.get("id") is not None:
                pending.append(str(item["id"]))
            elif isinstance(item, (int, str)):
                pending.append(str(item))

        for index in range(0, len(pending), 50):
            chunk = pending[index : index + 50]
            fetched = _api("/tracks", {"ids": ",".join(chunk)})
            if isinstance(fetched, list):
                for item in fetched:
                    converted = _map_track(item, cover)
                    if converted is not None:
                        tracks.append(converted)
            if len(tracks) >= MAX_TRACKS:
                break

        warnings: list[str] = []
        if len(tracks) >= MAX_TRACKS:
            tracks = tracks[:MAX_TRACKS]
            warnings.append(f"Плейлист обрезан до {MAX_TRACKS} треков.")
        if declared and len(tracks) < declared:
            warnings.append(f"SoundCloud отдал {len(tracks)} из {declared} треков — часть записей недоступна.")
        owner = normalize_space((data.get("user") or {}).get("username")) or None
        return Playlist(
            id=str(data.get("id") or ""),
            service=self.id,
            title=normalize_space(data.get("title")) or "Без названия",
            description=_plain_description(data.get("description")),
            owner=owner,
            cover_url=cover or next((track.cover_url for track in tracks if track.cover_url), None),
            url=clean_url(data.get("permalink_url")) or value,
            track_count=max(declared, len(tracks)),
            tracks=tracks,
            warnings=warnings,
        )

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)


_soundcloud = SoundCloudProvider()


def get_provider() -> SoundCloudProvider:
    return _soundcloud
