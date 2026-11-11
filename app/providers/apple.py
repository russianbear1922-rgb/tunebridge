from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from ..config import MAX_TRACKS
from ..models import Playlist, Track
from .base import ProviderError, RateLimitError, SourceProvider, clean_url, normalize_space

_APPLE_HOSTS = {"music.apple.com", "geo.music.apple.com", "itunes.apple.com"}
_APPLE_ID_RE = re.compile(r"^pl\.[A-Za-z0-9]+$")
_SERVER_DATA_RE = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ru,en;q=0.8"}
_COUNT_RE = re.compile(r"(\d+)\s*(?:songs?|tracks?|песен|треков|titres?|chansons?)", re.IGNORECASE)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plain_text(value: str | None, limit: int = 800) -> str | None:
    if not value:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    text = normalize_space(text.replace("\r", " ").replace("\n", " "))
    return text[:limit] or None


def _artwork_url(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    dictionary = node.get("dictionary")
    if not isinstance(dictionary, dict):
        return None
    url = dictionary.get("url")
    if not isinstance(url, str) or not url:
        return None
    url = url.replace("{w}x{h}bb.{f}", "1200x1200bb.jpg")
    return clean_url(url)


def parse_apple_url(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if _APPLE_ID_RE.match(value):
        return value
    if not re.match(r"^https?://", value, re.I):
        host_guess = value.split("/", 1)[0].lower()
        if host_guess not in _APPLE_HOSTS:
            return None
        value = "https://" + value
    parsed = urlparse(value)
    if (parsed.hostname or "").lower() not in _APPLE_HOSTS:
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if "playlist" not in parts:
        return None
    for part in parts[parts.index("playlist") + 1 :]:
        if _APPLE_ID_RE.match(part):
            return part
    return None


def _layout(payload: dict[str, Any]) -> dict[str, Any]:
    for node in payload.get("data") or []:
        if not isinstance(node, dict):
            continue
        page = node.get("data")
        if isinstance(page, dict) and isinstance(page.get("sections"), list):
            return page
    return {}


def _find_section(sections: list[Any], item_kind: str, id_prefix: str | None = None) -> dict[str, Any] | None:
    for section in sections:
        if not isinstance(section, dict):
            continue
        if section.get("itemKind") == item_kind:
            return section
        if id_prefix and str(section.get("id") or "").startswith(id_prefix):
            return section
    return None


def _parse_track(item: Any) -> Track | None:
    if not isinstance(item, dict):
        return None
    descriptor = item.get("contentDescriptor") or {}
    identifiers = descriptor.get("identifiers") or {}
    track_id = identifiers.get("storeAdamID")
    title = normalize_space(item.get("title"))
    if not track_id or not title:
        return None
    artists = [
        normalize_space(link.get("title"))
        for link in item.get("subtitleLinks") or []
        if isinstance(link, dict) and normalize_space(link.get("title"))
    ]
    tertiary = item.get("tertiaryLinks") or []
    album = None
    if tertiary and isinstance(tertiary[0], dict):
        album = normalize_space(tertiary[0].get("title")) or None
    duration = _as_int(item.get("duration"))
    return Track(
        id=str(track_id),
        title=title,
        artists=artists,
        album=album,
        duration_ms=duration if duration and duration > 0 else None,
        cover_url=_artwork_url(item.get("artwork")),
        url=clean_url(descriptor.get("url")),
        source="apple",
        explicit=bool(item.get("showExplicitBadge", False)),
    )


def _fetch_page(url: str) -> tuple[dict[str, Any], str]:
    try:
        response = requests.get(url, timeout=25, headers=_HEADERS)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise ProviderError("Нет связи с Apple Music", "Проверьте интернет-соединение и попробуйте снова.") from exc
    if response.status_code == 404:
        raise ProviderError("Плейлист Apple Music не найден", "Проверьте ссылку — возможно, он удалён или скрыт.")
    if response.status_code == 429:
        raise RateLimitError("Apple Music")
    if not response.ok:
        raise ProviderError("Apple Music вернул ошибку", "Попробуйте ещё раз через минуту.")
    markup = response.content.decode("utf-8", errors="replace")
    match = _SERVER_DATA_RE.search(markup)
    if not match:
        raise ProviderError(
            "Apple Music вернул неожиданный ответ",
            "Убедитесь, что плейлист публичный, и попробуйте снова.",
        )
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ProviderError("Apple Music вернул неожиданный ответ", "Попробуйте ещё раз.") from exc
    return payload, markup


class AppleMusicProvider(SourceProvider):
    id = "apple"
    name = "Apple Music"

    def list_playlists(self) -> list[Playlist]:
        raise ProviderError(
            "Apple Music не требует входа",
            "Откройте публичный плейлист по ссылке — аккаунт не нужен.",
        )

    def resolve_url(self, url: str) -> Playlist:
        playlist_id = parse_apple_url(url)
        if not playlist_id:
            raise ProviderError(
                "Не удалось разобрать ссылку Apple Music",
                "Нужна ссылка вида music.apple.com/…/playlist/…",
            )
        raw = (url or "").strip()
        fetch_url = raw if re.match(r"^https?://", raw, re.I) else f"https://music.apple.com/us/playlist/{playlist_id}"
        payload, _ = _fetch_page(fetch_url)
        page = _layout(payload)
        sections = page.get("sections") or []
        header_section = _find_section(sections, "containerDetailHeaderLockup")
        header = (header_section or {}).get("items") or []
        header = header[0] if header and isinstance(header[0], dict) else {}
        track_section = _find_section(sections, "trackLockup", "track-list")
        items = (track_section or {}).get("items") or []

        tracks: list[Track] = []
        for item in items:
            converted = _parse_track(item)
            if converted is not None:
                tracks.append(converted)
            if len(tracks) >= MAX_TRACKS:
                break
        if not tracks:
            raise ProviderError(
                "В плейлисте Apple Music нет доступных треков",
                "Возможно, он пуст или недоступен в вашем регионе.",
            )

        footer_section = _find_section(sections, "containerDetailTracklistFooterLockup", "track-list-footer")
        footer = (footer_section or {}).get("items") or []
        footer_text = ""
        if footer and isinstance(footer[0], dict):
            footer_text = str(footer[0].get("description") or "")
        count_match = _COUNT_RE.search(footer_text)
        declared = _as_int(count_match.group(1)) if count_match else 0

        warnings: list[str] = []
        if len(tracks) >= MAX_TRACKS:
            tracks = tracks[:MAX_TRACKS]
            warnings.append(f"Плейлист обрезан до {MAX_TRACKS} треков.")
        if declared and declared > len(tracks):
            warnings.append(f"Apple Music отдал {len(tracks)} из {declared} треков — остальные не попали на страницу.")

        owner = None
        for link in header.get("subtitleLinks") or []:
            if isinstance(link, dict) and link.get("title"):
                owner = normalize_space(link["title"])
                break
        description = _plain_text((header.get("modalPresentationDescriptor") or {}).get("paragraphText"))
        descriptor = header.get("contentDescriptor") or {}
        canonical = clean_url(descriptor.get("url")) or fetch_url
        return Playlist(
            id=playlist_id,
            service=self.id,
            title=normalize_space(header.get("title")) or "Без названия",
            description=description,
            owner=owner,
            cover_url=_artwork_url(header.get("artwork")),
            url=canonical,
            track_count=max(declared, len(tracks)),
            tracks=tracks,
            warnings=warnings,
        )

    def get_playlist(self, ref: str) -> Playlist:
        return self.resolve_url(ref)


_apple = AppleMusicProvider()


def get_provider() -> AppleMusicProvider:
    return _apple
