from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..config import MAX_TRACKS
from ..models import Playlist, Track
from .base import ProviderError, normalize_space

_HEADER_HINTS = {"title", "name", "track", "song", "artist", "artists", "название", "исполнитель"}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_duration_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        if number <= 0:
            return None
        return number * 1000 if number < 10000 else number
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return parse_duration_ms(float(text))
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", text)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return ((hours * 60 + minutes) * 60 + seconds) * 1000
    return None


def split_artist_title(value: str) -> tuple[list[str], str]:
    text = normalize_space(value)
    for delimiter in (" - ", " – ", " — "):
        if delimiter in text:
            artist, title = text.split(delimiter, 1)
            artists = [
                part.strip()
                for part in re.split(r"\s*(?:;|/|\bfeat\.?(?=\s|$)|\bft\.?(?=\s|$))\s*", artist)
                if part.strip()
            ]
            return artists, title.strip()
    return [], text


def _track(title: str, artists: list[str], *, album: str | None = None, duration_ms: int | None = None,
           isrc: str | None = None, url: str | None = None, index: int = 0) -> Track:
    return Track(
        id=f"file-{index}",
        title=normalize_space(title) or "Без названия",
        artists=[normalize_space(name) for name in artists if normalize_space(name)],
        album=normalize_space(album) or None,
        duration_ms=duration_ms,
        isrc=normalize_space(isrc) or None,
        cover_url=None,
        url=url,
        source="file",
    )


def _parse_m3u(content: str) -> tuple[str | None, list[Track]]:
    playlist_title = None
    tracks: list[Track] = []
    pending_title: str | None = None
    pending_duration: int | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("#PLAYLIST:"):
            playlist_title = normalize_space(line.split(":", 1)[1])
            continue
        if upper.startswith("#EXTINF:"):
            payload = line[8:]
            duration_text, _, display = payload.partition(",")
            pending_duration = parse_duration_ms(duration_text.strip())
            pending_title = normalize_space(display) or None
            continue
        if line.startswith("#"):
            continue
        if pending_title is not None:
            artists, title = split_artist_title(pending_title)
            tracks.append(_track(title, artists, duration_ms=pending_duration, url=line, index=len(tracks)))
            pending_title = None
            pending_duration = None
            continue
        artists, title = split_artist_title(line)
        if title:
            tracks.append(_track(title, artists, index=len(tracks)))
    if pending_title is not None:
        artists, title = split_artist_title(pending_title)
        tracks.append(_track(title, artists, duration_ms=pending_duration, index=len(tracks)))
    return playlist_title, tracks


def _parse_csv(content: str) -> tuple[str | None, list[Track]]:
    text = content.lstrip("\ufeff")
    sample = text.splitlines()[0] if text.splitlines() else ""
    if not any(hint in sample.casefold() for hint in _HEADER_HINTS):
        _, tracks = _parse_m3u(text)
        return None, tracks
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, []
    fields = {name.strip().casefold(): name for name in reader.fieldnames if name}
    title_key = next((fields[key] for key in ("title", "name", "track", "song", "название") if key in fields), None)
    artist_key = next((fields[key] for key in ("artist", "artists", "исполнитель") if key in fields), None)
    album_key = next((fields[key] for key in ("album", "альбом") if key in fields), None)
    duration_key = next((fields[key] for key in ("duration_ms", "duration", "length", "длительность") if key in fields), None)
    isrc_key = fields.get("isrc")
    url_key = next((fields[key] for key in ("url", "link", "spotify", "youtube") if key in fields), None)
    tracks: list[Track] = []
    for row in reader:
        title = normalize_space(row.get(title_key) if title_key else "")
        if not title:
            continue
        artist_text = normalize_space(row.get(artist_key) if artist_key else "")
        artists = [part.strip() for part in re.split(r"\s*;\s*", artist_text) if part.strip()] if artist_text else []
        tracks.append(
            _track(
                title,
                artists,
                album=row.get(album_key) if album_key else None,
                duration_ms=parse_duration_ms(row.get(duration_key)) if duration_key else None,
                isrc=row.get(isrc_key) if isrc_key else None,
                url=normalize_space(row.get(url_key)) if url_key else None,
                index=len(tracks),
            )
        )
    return None, tracks


def _parse_json(content: str) -> tuple[str | None, str | None, list[Track]]:
    data = json.loads(content)
    title = None
    description = None
    items: list[Any]
    if isinstance(data, dict):
        if isinstance(data.get("playlist"), dict):
            meta = data["playlist"]
            title = meta.get("title")
            description = meta.get("description")
            items = data.get("tracks") or meta.get("tracks") or []
        else:
            title = data.get("title")
            description = data.get("description")
            items = data.get("tracks") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []
    tracks: list[Track] = []
    for item in items:
        if isinstance(item, str):
            artists, name = split_artist_title(item)
            tracks.append(_track(name, artists, index=len(tracks)))
            continue
        if not isinstance(item, dict):
            continue
        title_value = item.get("title") or item.get("name") or item.get("track")
        if not title_value:
            continue
        artists_value = item.get("artists") or item.get("artist")
        if isinstance(artists_value, str):
            artists = [part.strip() for part in re.split(r"\s*;\s*", artists_value) if part.strip()]
        elif isinstance(artists_value, list):
            artists = [
                value.get("name") if isinstance(value, dict) else str(value)
                for value in artists_value
                if value
            ]
        else:
            artists = []
        tracks.append(
            _track(
                str(title_value),
                [str(name) for name in artists if name],
                album=item.get("album"),
                duration_ms=parse_duration_ms(item.get("duration_ms") or item.get("duration")),
                isrc=item.get("isrc"),
                url=item.get("url"),
                index=len(tracks),
            )
        )
    return title, description, tracks


def parse_import(filename: str, content: str) -> Playlist:
    if len(content.encode("utf-8", errors="ignore")) > 5 * 1024 * 1024:
        raise ProviderError("Файл слишком большой", "Максимальный размер — 5 МБ.")
    name = (filename or "playlist").strip()
    lower = name.casefold()
    title: str | None = None
    description: str | None = None
    warnings: list[str] = []
    try:
        if lower.endswith((".m3u", ".m3u8")):
            title, tracks = _parse_m3u(content)
        elif lower.endswith(".csv"):
            title, tracks = _parse_csv(content)
        elif lower.endswith(".json"):
            title, description, tracks = _parse_json(content)
        else:
            title, tracks = _parse_m3u(content)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "Не удалось прочитать JSON",
            "Проверьте, что файл не повреждён и содержит плейлист.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(
            "Не удалось прочитать файл",
            "Поддерживаются M3U, M3U8, CSV, JSON и обычный текст со строками «Артист - Название».",
        ) from exc
    if len(tracks) > MAX_TRACKS:
        warnings.append(f"Импорт обрезан до {MAX_TRACKS} треков.")
        tracks = tracks[:MAX_TRACKS]
    if not tracks:
        raise ProviderError(
            "В файле не нашлось треков",
            "Для M3U нужны строки #EXTINF, для CSV — заголовки title/artist, для JSON — массив треков.",
        )
    fallback_title = re.sub(r"\.(m3u8?|csv|json|txt)$", "", name, flags=re.I) or "Импортированный плейлист"
    return Playlist(
        id="imported",
        service="file",
        title=normalize_space(title) or fallback_title,
        description=description,
        owner=None,
        cover_url=None,
        url=None,
        track_count=len(tracks),
        tracks=tracks,
        warnings=warnings,
    )


def _search_url(track: Track) -> str:
    query = " ".join([*track.artists[:2], track.title]).strip()
    return f"https://music.youtube.com/search?q={quote(query)}" if query else "https://music.youtube.com"


def build_m3u(playlist: Playlist) -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{playlist.title}", "# Created by TuneBridge"]
    for track in playlist.tracks:
        artists = ", ".join(track.artists)
        display = f"{artists} - {track.title}" if artists else track.title
        seconds = int((track.duration_ms or 0) / 1000)
        lines.append(f"#EXTINF:{seconds},{display}")
        lines.append(track.url or _search_url(track))
    return "\n".join(lines) + "\n"


def build_csv(playlist: Playlist) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["title", "artist", "album", "duration_ms", "isrc", "url"])
    for track in playlist.tracks:
        writer.writerow(
            [
                track.title,
                "; ".join(track.artists),
                track.album or "",
                track.duration_ms or "",
                track.isrc or "",
                track.url or "",
            ]
        )
    return "\ufeff" + buffer.getvalue()


def build_json(playlist: Playlist) -> str:
    payload = {
        "generator": "TuneBridge",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "playlist": {
            "title": playlist.title,
            "description": playlist.description,
            "owner": playlist.owner,
            "source_service": playlist.service,
            "url": playlist.url,
            "track_count": len(playlist.tracks),
        },
        "tracks": [track.model_dump() for track in playlist.tracks],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _readme(playlist: Playlist) -> str:
    return (
        f"{playlist.title}\n"
        f"{'=' * len(playlist.title)}\n\n"
        f"Треков: {len(playlist.tracks)}\n"
        f"Источник: {playlist.service}\n"
        f"Экспортировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        "Файлы:\n"
        "  playlist.m3u8 — плейлист для плееров и сервисов импорта (Soundiiz и др.).\n"
        "  playlist.csv  — таблица для Excel / Google Sheets и импорта по столбцам.\n"
        "  playlist.json — полные данные о треках для скриптов.\n\n"
        "M3U содержит метаданные треков; ссылка после #EXTINF ведёт на поиск\n"
        "в YouTube Music, если у трека нет прямой ссылки на источник.\n"
        "Для переноса в Spotify или YouTube Music удобнее CSV: title + artist.\n\n"
        "Сделано в TuneBridge.\n"
    )


def build_export_zip(playlist: Playlist, formats: list[str]) -> bytes:
    allowed = {"m3u", "csv", "json"}
    selected = [fmt for fmt in formats if fmt in allowed]
    if not selected:
        selected = ["m3u", "csv", "json"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if "m3u" in selected:
            archive.writestr("playlist.m3u8", build_m3u(playlist))
        if "csv" in selected:
            archive.writestr("playlist.csv", build_csv(playlist))
        if "json" in selected:
            archive.writestr("playlist.json", build_json(playlist))
        archive.writestr("README.txt", _readme(playlist))
    return buffer.getvalue()
