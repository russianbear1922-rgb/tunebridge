from __future__ import annotations

import hashlib
import random
import time
from typing import Any

from ..models import Playlist, Track
from .base import ProviderError, SourceProvider, TargetProvider, normalize_space

_DEMO_TRACKS: list[tuple[str, list[str], str, int]] = [
    ("Неоновый дождь", ["Mira Vale"], "Городские огни", 222),
    ("Midnight Drive", ["Neon Harbour"], "Afterglow", 245),
    ("Северный ветер", ["Полярный круг"], "Тишина", 198),
    ("Falling Slowly", ["June & The Wolves"], "Paper Skies", 261),
    ("Танцуй со мной", ["Аля Ветер"], "Первый снег", 207),
    ("Glass House", ["Ora Lane"], "Rooms", 233),
    ("Не отпускай", ["КИТ и Море"], "Не отпускай", 219),
    ("Velvet Morning", ["The Slow Club"], "Sunday Tapes", 256),
    ("Пыль на пластинке", ["Диджей Пыль"], "Винил", 184),
    ("Runaway Signal", ["Static Bloom"], "Frequency", 203),
    ("Тёплый асфальт", ["Ромашка"], "Лето внутри", 192),
    ("Paper Planes", ["Milo Grey"], "Small Hours", 228),
    ("Океан внутри", ["Sasha More"], "Глубина", 241),
    ("Golden Hour", ["Lena Fox"], "Golden Hour", 214),
    ("Полночь на кухне", ["Тост и Джем"], "Квартира", 176),
    ("Echoes of Us", ["Wilderness"], "Echoes", 267),
    ("Свет в окне", ["Тихий Дом"], "Свет", 236),
    ("Sunday Static", ["The Low Keys"], "Analog Dreams", 251),
]

_ARTISTS_POOL = ["Mira Vale", "Neon Harbour", "Полярный круг", "Ora Lane", "Static Bloom", "Lena Fox", "Тихий Дом"]
_ALBUMS_POOL = ["Afterglow", "Paper Skies", "Frequency", "Analog Dreams", "Глубина", "Small Hours"]


def _stable(value: str) -> int:
    return int(hashlib.md5(value.encode("utf-8")).hexdigest()[:8], 16)


def _demo_track(index: int, title: str, artists: list[str], album: str, duration: int) -> Track:
    return Track(
        id=f"demo-{index}",
        title=title,
        artists=artists,
        album=album,
        duration_ms=duration * 1000,
        cover_url=None,
        url=None,
        source="demo",
    )


def build_demo_playlist() -> Playlist:
    tracks = [
        _demo_track(index, title, artists, album, duration)
        for index, (title, artists, album, duration) in enumerate(_DEMO_TRACKS)
    ]
    return Playlist(
        id="demo-playlist",
        service="demo",
        title="Ночная поездка",
        description="Демонстрационный плейлист: 18 треков, чтобы посмотреть весь путь без подключения аккаунтов.",
        owner="TuneBridge Demo",
        cover_url="/static/img/demo-cover.svg",
        url=None,
        track_count=len(tracks),
        tracks=tracks,
        warnings=[],
    )


class DemoProvider(SourceProvider, TargetProvider):
    id = "demo"
    name = "Демо-плеер"
    search_workers = 2
    batch_size = 4
    supports_search = True
    auth_required = False

    def is_connected(self) -> bool:
        return True

    def list_playlists(self) -> list[Playlist]:
        playlist = build_demo_playlist()
        playlist.tracks = []
        return [playlist]

    def resolve_url(self, url: str) -> Playlist:
        return build_demo_playlist()

    def get_playlist(self, ref: str) -> Playlist:
        return build_demo_playlist()

    def _candidate(self, source: Track, suffix: str, *, title: str | None = None,
                   artists: list[str] | None = None, duration_delta: int = 0) -> Track:
        base = title or source.title
        name = f"{base} {suffix}".strip()
        return Track(
            id=f"demo-cand-{_stable(source.id + suffix + base)}",
            title=name,
            artists=artists or source.artists,
            album=source.album or "Demo Album",
            duration_ms=(source.duration_ms or 200000) + duration_delta * 1000,
            cover_url=None,
            url=None,
            source="demo",
        )

    def search(self, track: Track) -> list[Track]:
        time.sleep(0.14)
        bucket = _stable(track.id) % 12
        if bucket <= 6:
            return [
                self._candidate(track, ""),
                self._candidate(track, "(Remastered 2011)", duration_delta=2),
            ]
        if bucket <= 8:
            return [
                self._candidate(track, "(Remastered)", duration_delta=1),
                self._candidate(track, ""),
            ]
        if bucket == 9:
            return [
                self._candidate(track, "(Live at Home)", duration_delta=8),
                self._candidate(track, ""),
            ]
        if bucket == 10:
            return [
                self._candidate(track, "(Radio Edit)", duration_delta=-25),
                self._candidate(track, "", artists=["Unknown Cover Band"]),
            ]
        index = _stable(track.id + "missing")
        return [
            Track(
                id=f"demo-cand-{index}",
                title=f"{_ALBUMS_POOL[index % len(_ALBUMS_POOL)]} (Instrumental)",
                artists=[_ARTISTS_POOL[index % len(_ARTISTS_POOL)]],
                album=_ALBUMS_POOL[(index + 1) % len(_ALBUMS_POOL)],
                duration_ms=180000 + (index % 60) * 1000,
                source="demo",
            )
        ]

    def search_query(self, query: str) -> list[Track]:
        value = normalize_space(query) or "Demo"
        rng = random.Random(_stable(value))
        results: list[Track] = []
        for index in range(6):
            artist = _ARTISTS_POOL[(rng.randrange(len(_ARTISTS_POOL)) + index) % len(_ARTISTS_POOL)]
            results.append(
                Track(
                    id=f"demo-manual-{_stable(value + str(index))}",
                    title=value if index == 0 else f"{value} (version {index + 1})",
                    artists=[artist],
                    album=_ALBUMS_POOL[index % len(_ALBUMS_POOL)],
                    duration_ms=(150 + rng.randrange(120)) * 1000,
                    source="demo",
                )
            )
        return results

    def create_playlist(self, title: str, description: str, options: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.35)
        if not normalize_space(title):
            raise ProviderError("Нужно название плейлиста", "Введите название перед переносом.")
        return {"id": f"demo-created-{_stable(title)}", "url": None, "demo": True}

    def add_batch(self, playlist_id: str, tracks: list[Track]) -> None:
        time.sleep(0.45)


_demo = DemoProvider()


def get_provider() -> DemoProvider:
    return _demo
