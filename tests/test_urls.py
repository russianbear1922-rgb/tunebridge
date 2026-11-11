from __future__ import annotations

import unittest

from app.providers.apple import parse_apple_url
from app.providers.soundcloud import parse_soundcloud_url
from app.providers.spotify import parse_spotify_url
from app.providers.yandex import parse_yandex_url
from app.providers.youtube import parse_youtube_url


class YandexUrlTest(unittest.TestCase):
    def test_playlist_url(self) -> None:
        self.assertEqual(
            parse_yandex_url("https://music.yandex.ru/playlists/f0e1d2c3-4567-89ab-cdef-0123456789ab"),
            ("uuid", "f0e1d2c3-4567-89ab-cdef-0123456789ab"),
        )

    def test_playlist_url_without_scheme(self) -> None:
        self.assertEqual(parse_yandex_url("music.yandex.com/playlists/abc123"), ("uuid", "abc123"))

    def test_bare_uuid(self) -> None:
        self.assertEqual(
            parse_yandex_url("f0e1d2c3456789abcdef0123456789ab"),
            ("uuid", "f0e1d2c3456789abcdef0123456789ab"),
        )

    def test_legacy_user_playlist(self) -> None:
        self.assertEqual(
            parse_yandex_url("https://music.yandex.ru/users/mira.vale/playlists/123456"),
            ("legacy", "mira.vale", "123456"),
        )

    def test_album_and_track_are_not_playlists(self) -> None:
        self.assertEqual(parse_yandex_url("https://music.yandex.ru/album/12345"), ("error", "album"))
        self.assertEqual(parse_yandex_url("https://music.yandex.ru/album/12345/track/678"), ("error", "track"))

    def test_foreign_or_invalid_links(self) -> None:
        self.assertIsNone(parse_yandex_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"))
        self.assertIsNone(parse_yandex_url("https://music.yandex.ru/"))
        self.assertIsNone(parse_yandex_url(""))
        self.assertIsNone(parse_yandex_url("   "))


class YoutubeUrlTest(unittest.TestCase):
    def test_playlist_query(self) -> None:
        self.assertEqual(
            parse_youtube_url("https://music.youtube.com/playlist?list=PLabc123def"),
            "PLabc123def",
        )
        self.assertEqual(
            parse_youtube_url("https://www.youtube.com/watch?v=abc&list=PLxyz987"),
            "PLxyz987",
        )

    def test_playlist_path(self) -> None:
        self.assertEqual(
            parse_youtube_url("https://music.youtube.com/playlist/PLpath12345"),
            "PLpath12345",
        )

    def test_bare_id(self) -> None:
        self.assertEqual(parse_youtube_url("PLbare123456"), "PLbare123456")

    def test_invalid_links(self) -> None:
        self.assertIsNone(parse_youtube_url("https://youtu.be/abc"))
        self.assertIsNone(parse_youtube_url("https://example.com/playlist?list=PL123456789"))
        self.assertIsNone(parse_youtube_url("https://music.youtube.com/"))
        self.assertIsNone(parse_youtube_url(""))
        self.assertIsNone(parse_youtube_url("short"))


class SpotifyUrlTest(unittest.TestCase):
    def test_playlist_url(self) -> None:
        self.assertEqual(
            parse_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

    def test_international_path(self) -> None:
        self.assertEqual(
            parse_spotify_url("https://open.spotify.com/intl-ru/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc"),
            "37i9dQZF1DXcBWIGoYBM5M",
        )

    def test_uri_and_bare_id(self) -> None:
        self.assertEqual(parse_spotify_url("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"), "37i9dQZF1DXcBWIGoYBM5M")
        self.assertEqual(parse_spotify_url("37i9dQZF1DXcBWIGoYBM5M"), "37i9dQZF1DXcBWIGoYBM5M")

    def test_invalid_links(self) -> None:
        self.assertIsNone(parse_spotify_url("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"))
        self.assertIsNone(parse_spotify_url("https://open.spotify.com/playlist/short"))
        self.assertIsNone(parse_spotify_url(""))
        self.assertIsNone(parse_spotify_url("not a link"))


class SoundcloudUrlTest(unittest.TestCase):
    def test_set_url(self) -> None:
        self.assertEqual(
            parse_soundcloud_url("https://soundcloud.com/labsone01/sets/2025-deep-house-mix?si=abc"),
            "https://soundcloud.com/labsone01/sets/2025-deep-house-mix",
        )

    def test_without_scheme_and_mobile_host(self) -> None:
        self.assertEqual(
            parse_soundcloud_url("soundcloud.com/artist/sets/mix"),
            "https://soundcloud.com/artist/sets/mix",
        )
        self.assertEqual(
            parse_soundcloud_url("https://m.soundcloud.com/artist/sets/mix"),
            "https://soundcloud.com/artist/sets/mix",
        )

    def test_short_link(self) -> None:
        self.assertEqual(
            parse_soundcloud_url("https://on.soundcloud.com/abc123"),
            "https://on.soundcloud.com/abc123",
        )

    def test_not_a_set(self) -> None:
        self.assertIsNone(parse_soundcloud_url("https://soundcloud.com/artist/track"))
        self.assertIsNone(parse_soundcloud_url("https://soundcloud.com/artist"))
        self.assertIsNone(parse_soundcloud_url("https://example.com/artist/sets/mix"))
        self.assertIsNone(parse_soundcloud_url(""))
        self.assertIsNone(parse_soundcloud_url("not a link"))


class AppleUrlTest(unittest.TestCase):
    def test_playlist_url(self) -> None:
        self.assertEqual(
            parse_apple_url(
                "https://music.apple.com/ru/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb?l=en"
            ),
            "pl.f4d106fed2bd41149aaacabb233eb5eb",
        )

    def test_geo_and_itunes_hosts(self) -> None:
        self.assertEqual(
            parse_apple_url("https://geo.music.apple.com/us/playlist/mix/pl.abc123"),
            "pl.abc123",
        )
        self.assertEqual(
            parse_apple_url("https://itunes.apple.com/ru/playlist/mix/pl.abc123"),
            "pl.abc123",
        )

    def test_without_scheme_and_bare_id(self) -> None:
        self.assertEqual(
            parse_apple_url("music.apple.com/us/playlist/mix/pl.abc123"),
            "pl.abc123",
        )
        self.assertEqual(parse_apple_url("pl.abc123"), "pl.abc123")

    def test_not_a_playlist(self) -> None:
        self.assertIsNone(parse_apple_url("https://music.apple.com/us/album/12345"))
        self.assertIsNone(parse_apple_url("https://music.apple.com/us/playlist/mix"))
        self.assertIsNone(parse_apple_url("https://open.spotify.com/playlist/pl.abc123"))
        self.assertIsNone(parse_apple_url(""))
        self.assertIsNone(parse_apple_url("pl."))


if __name__ == "__main__":
    unittest.main()
