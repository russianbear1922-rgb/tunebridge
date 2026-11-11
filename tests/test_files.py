from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path

from app.models import Playlist, Track
from app.providers.files import (
    build_csv,
    build_export_zip,
    build_json,
    build_m3u,
    parse_duration_ms,
    parse_import,
    split_artist_title,
)
from app.providers.base import ProviderError

FIXTURES = Path(__file__).parent / "fixtures"


def make_playlist(tracks: list[Track] | None = None) -> Playlist:
    return Playlist(
        id="imported",
        service="file",
        title="Тестовый плейлист",
        track_count=len(tracks or []),
        tracks=tracks or [],
    )


class ParseDurationTest(unittest.TestCase):
    def test_seconds_and_milliseconds(self) -> None:
        self.assertEqual(parse_duration_ms(222), 222000)
        self.assertEqual(parse_duration_ms(222.9), 222000)
        self.assertEqual(parse_duration_ms(222000), 222000)

    def test_clock_formats(self) -> None:
        self.assertEqual(parse_duration_ms("3:42"), 222000)
        self.assertEqual(parse_duration_ms("1:02:03"), 3723000)
        self.assertEqual(parse_duration_ms("0:59"), 59000)

    def test_invalid_values(self) -> None:
        self.assertIsNone(parse_duration_ms(None))
        self.assertIsNone(parse_duration_ms(""))
        self.assertIsNone(parse_duration_ms("soon"))
        self.assertIsNone(parse_duration_ms(0))
        self.assertIsNone(parse_duration_ms(-5))


class SplitArtistTitleTest(unittest.TestCase):
    def test_common_delimiters(self) -> None:
        self.assertEqual(split_artist_title("Mira Vale - Неоновый дождь"), (["Mira Vale"], "Неоновый дождь"))
        self.assertEqual(split_artist_title("Neon Harbour – Midnight Drive"), (["Neon Harbour"], "Midnight Drive"))
        self.assertEqual(split_artist_title("A — B"), (["A"], "B"))

    def test_multiple_artists(self) -> None:
        self.assertEqual(
            split_artist_title("Mira Vale; Полярный круг - Северный ветер"),
            (["Mira Vale", "Полярный круг"], "Северный ветер"),
        )
        self.assertEqual(split_artist_title("June feat. Wolves - Falling Slowly")[0], ["June", "Wolves"])

    def test_without_delimiter(self) -> None:
        self.assertEqual(split_artist_title("  Просто   название "), ([], "Просто название"))


class M3UImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.content = (FIXTURES / "sample.m3u").read_text(encoding="utf-8")

    def test_parses_fixture(self) -> None:
        playlist = parse_import("sample.m3u", self.content)
        self.assertEqual(playlist.id, "imported")
        self.assertEqual(playlist.service, "file")
        self.assertEqual(playlist.title, "Тестовый плейлист")
        self.assertEqual(playlist.track_count, 4)
        self.assertEqual(len(playlist.tracks), 4)

        first = playlist.tracks[0]
        self.assertEqual(first.artists, ["Mira Vale"])
        self.assertEqual(first.title, "Неоновый дождь")
        self.assertEqual(first.duration_ms, 222000)
        self.assertEqual(first.url, "https://example.com/track/1")

        self.assertEqual(playlist.tracks[3].artists, ["June & The Wolves"])
        self.assertEqual(playlist.tracks[3].title, "Falling Slowly")

    def test_without_playlist_header_uses_filename(self) -> None:
        playlist = parse_import("my mix.m3u8", "#EXTM3U\n#EXTINF:100,Artist - Song\nurl\n")
        self.assertEqual(playlist.title, "my mix")
        self.assertEqual(playlist.tracks[0].title, "Song")

    def test_extension_line_without_url(self) -> None:
        playlist = parse_import("tail.m3u", "#EXTM3U\n#EXTINF:0,Artist - Song\n")
        self.assertEqual(len(playlist.tracks), 1)
        self.assertIsNone(playlist.tracks[0].duration_ms)
        self.assertIsNone(playlist.tracks[0].url)

    def test_txt_is_treated_as_m3u(self) -> None:
        playlist = parse_import("list.txt", "Mira Vale - Неоновый дождь\nNeon Harbour - Midnight Drive\n")
        self.assertEqual(playlist.title, "list")
        self.assertEqual([track.title for track in playlist.tracks], ["Неоновый дождь", "Midnight Drive"])
        self.assertEqual(playlist.tracks[1].artists, ["Neon Harbour"])

    def test_empty_file_rejected(self) -> None:
        with self.assertRaises(ProviderError):
            parse_import("empty.m3u", "#EXTM3U\n")

    def test_size_limit(self) -> None:
        with self.assertRaises(ProviderError) as ctx:
            parse_import("big.m3u", "x" * (5 * 1024 * 1024 + 1))
        self.assertIn("5 МБ", ctx.exception.hint)

    def test_track_limit_truncates_with_warning(self) -> None:
        lines = ["#EXTM3U"] + [f"#EXTINF:100,Artist - Song {index}\nurl{index}" for index in range(2005)]
        playlist = parse_import("long.m3u", "\n".join(lines))
        self.assertEqual(len(playlist.tracks), 2000)
        self.assertTrue(playlist.warnings)
        self.assertIn("2000", playlist.warnings[0])


class CsvImportTest(unittest.TestCase):
    def test_header_and_durations(self) -> None:
        content = (
            "title,artist,album,duration_ms,isrc,url\n"
            "Неоновый дождь,Mira Vale,Neon,3:42,,https://example.com/1\n"
            "Midnight Drive,Neon Harbour; Guest,Drive,245000,USRC123,https://example.com/2\n"
        )
        playlist = parse_import("mix.csv", content)
        self.assertEqual(len(playlist.tracks), 2)
        first, second = playlist.tracks
        self.assertEqual(first.title, "Неоновый дождь")
        self.assertEqual(first.artists, ["Mira Vale"])
        self.assertEqual(first.album, "Neon")
        self.assertEqual(first.duration_ms, 222000)
        self.assertEqual(second.artists, ["Neon Harbour", "Guest"])
        self.assertEqual(second.duration_ms, 245000)
        self.assertEqual(second.isrc, "USRC123")

    def test_bom_and_russian_headers(self) -> None:
        content = "\ufeffНазвание,Исполнитель\nСеверный ветер,Полярный круг\n"
        playlist = parse_import("ru.csv", content)
        self.assertEqual(playlist.tracks[0].title, "Северный ветер")
        self.assertEqual(playlist.tracks[0].artists, ["Полярный круг"])

    def test_csv_without_header_falls_back_to_lines(self) -> None:
        playlist = parse_import("plain.csv", "Mira Vale - Неоновый дождь\n")
        self.assertEqual(playlist.tracks[0].title, "Неоновый дождь")

    def test_rows_without_title_skipped(self) -> None:
        playlist = parse_import("mix.csv", "title,artist\n,Mira Vale\nSong,Artist\n")
        self.assertEqual(len(playlist.tracks), 1)


class JsonImportTest(unittest.TestCase):
    def test_full_payload(self) -> None:
        payload = {
            "playlist": {"title": "Мой плейлист", "description": "Описание"},
            "tracks": [
                {"title": "Неоновый дождь", "artists": [{"name": "Mira Vale"}], "duration": "3:42"},
                {"name": "Midnight Drive", "artist": "Neon Harbour; Guest", "duration_ms": 245000},
                "June & The Wolves - Falling Slowly",
            ],
        }
        playlist = parse_import("mix.json", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(playlist.title, "Мой плейлист")
        self.assertEqual(playlist.description, "Описание")
        self.assertEqual(len(playlist.tracks), 3)
        self.assertEqual(playlist.tracks[0].artists, ["Mira Vale"])
        self.assertEqual(playlist.tracks[0].duration_ms, 222000)
        self.assertEqual(playlist.tracks[1].artists, ["Neon Harbour", "Guest"])
        self.assertEqual(playlist.tracks[2].title, "Falling Slowly")
        self.assertEqual(playlist.tracks[2].artists, ["June & The Wolves"])

    def test_plain_list(self) -> None:
        playlist = parse_import("list.json", json.dumps(["Mira Vale - Неоновый дождь"]))
        self.assertEqual(playlist.track_count, 1)
        self.assertEqual(playlist.tracks[0].title, "Неоновый дождь")

    def test_invalid_json_rejected(self) -> None:
        with self.assertRaises(ProviderError):
            parse_import("broken.json", "{not json")


class ExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.playlist = make_playlist(
            [
                Track(id="a", title="Неоновый дождь", artists=["Mira Vale"], duration_ms=222000, url="https://example.com/1"),
                Track(id="b", title="Falling Slowly", artists=["June & The Wolves"], duration_ms=261000),
            ]
        )

    def test_m3u_round_trip(self) -> None:
        content = build_m3u(self.playlist)
        self.assertTrue(content.startswith("#EXTM3U"))
        self.assertIn("#PLAYLIST:Тестовый плейлист", content)
        self.assertIn("#EXTINF:222,Mira Vale - Неоновый дождь", content)
        self.assertIn("https://music.youtube.com/search?q=", content)

        restored = parse_import("export.m3u8", content)
        self.assertEqual([track.title for track in restored.tracks], ["Неоновый дождь", "Falling Slowly"])
        self.assertEqual(restored.tracks[1].artists, ["June & The Wolves"])
        self.assertEqual(restored.tracks[0].duration_ms, 222000)

    def test_csv_round_trip(self) -> None:
        content = build_csv(self.playlist)
        self.assertTrue(content.startswith("\ufeff"))
        restored = parse_import("export.csv", content)
        self.assertEqual([track.title for track in restored.tracks], ["Неоновый дождь", "Falling Slowly"])
        self.assertEqual(restored.tracks[0].duration_ms, 222000)

    def test_json_round_trip(self) -> None:
        content = build_json(self.playlist)
        data = json.loads(content)
        self.assertEqual(data["playlist"]["title"], "Тестовый плейлист")
        self.assertEqual(data["tracks"][0]["title"], "Неоновый дождь")

        restored = parse_import("export.json", content)
        self.assertEqual(restored.title, "Тестовый плейлист")
        self.assertEqual(len(restored.tracks), 2)

    def test_zip_selected_formats(self) -> None:
        data = build_export_zip(self.playlist, ["csv"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        self.assertEqual(names, {"playlist.csv", "README.txt"})

    def test_zip_defaults_to_all_formats(self) -> None:
        data = build_export_zip(self.playlist, [])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        self.assertEqual(names, {"playlist.m3u8", "playlist.csv", "playlist.json", "README.txt"})


if __name__ == "__main__":
    unittest.main()
