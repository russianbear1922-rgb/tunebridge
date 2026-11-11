from __future__ import annotations

import unittest

from app.providers.apple import _parse_track
from app.providers.soundcloud import _CLIENT_ID_RE, _map_track
from app.providers.spotify import _playlist_from_embed


class SoundcloudClientIdTest(unittest.TestCase):
    def test_quoted_asset_value(self) -> None:
        match = _CLIENT_ID_RE.search('client_id:"xk6BGxLCsQJ5Ss0bH6sRdsZhts3gTNaU",client_is_expiring:!1')
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "xk6BGxLCsQJ5Ss0bH6sRdsZhts3gTNaU")

    def test_plain_query_value(self) -> None:
        match = _CLIENT_ID_RE.search("client_id=abcdefghijklmnopqrstuvwx&foo=bar")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "abcdefghijklmnopqrstuvwx")


class SoundcloudTrackTest(unittest.TestCase):
    def test_maps_artist_isrc_and_cover(self) -> None:
        track = _map_track(
            {
                "id": 42,
                "title": "  Deep  House  ",
                "publisher_metadata": {"artist": "Mira Vale", "isrc": "QZ123", "explicit": True},
                "user": {"username": "label"},
                "duration": 215000,
                "artwork_url": "https://i1.sndcdn.com/artworks-1-large.jpg",
                "permalink_url": "https://soundcloud.com/label/deep-house",
                "genre": "House",
            },
            None,
        )
        self.assertIsNotNone(track)
        self.assertEqual(track.id, "42")
        self.assertEqual(track.title, "Deep House")
        self.assertEqual(track.artists, ["Mira Vale"])
        self.assertEqual(track.isrc, "QZ123")
        self.assertTrue(track.explicit)
        self.assertTrue(track.cover_url.endswith("-t500x500.jpg"))

    def test_skips_items_without_title(self) -> None:
        self.assertIsNone(_map_track({"id": 1, "title": "  "}, None))


class SpotifyEmbedTest(unittest.TestCase):
    def test_parses_playlist_entity(self) -> None:
        playlist = _playlist_from_embed(
            {
                "title": "Today’s Top Hits",
                "subtitle": "Spotify",
                "coverArt": {"sources": [{"url": "https://i.scdn.co/image/abc"}]},
                "trackList": [
                    {
                        "uri": "spotify:track:4uLU6hMCjMI75M1A2tKUQC",
                        "title": "One",
                        "subtitle": "Artist A, Artist B",
                        "duration": 123000,
                    },
                    {"uri": "spotify:local:something", "title": "Skip me"},
                ],
            },
            "37i9dQZF1DXcBWIGoYBM5M",
        )
        self.assertEqual(playlist.title, "Today’s Top Hits")
        self.assertEqual(playlist.owner, "Spotify")
        self.assertEqual(playlist.track_count, 1)
        self.assertEqual(playlist.tracks[0].artists, ["Artist A", "Artist B"])
        self.assertEqual(playlist.cover_url, "https://i.scdn.co/image/abc")
        self.assertEqual(playlist.warnings, [])


class AppleTrackTest(unittest.TestCase):
    def test_maps_lockup(self) -> None:
        track = _parse_track(
            {
                "contentDescriptor": {
                    "identifiers": {"storeAdamID": "1440833098"},
                    "url": "https://music.apple.com/us/song/one/1440833098",
                },
                "title": "One",
                "subtitleLinks": [{"title": "Artist A"}],
                "tertiaryLinks": [{"title": "Album"}],
                "duration": 215000,
                "artwork": {"dictionary": {"url": "https://is1.mzstatic.com/image/{w}x{h}bb.{f}"}},
                "showExplicitBadge": True,
            }
        )
        self.assertIsNotNone(track)
        self.assertEqual(track.id, "1440833098")
        self.assertEqual(track.artists, ["Artist A"])
        self.assertEqual(track.album, "Album")
        self.assertEqual(track.duration_ms, 215000)
        self.assertTrue(track.explicit)
        self.assertEqual(track.cover_url, "https://is1.mzstatic.com/image/1200x1200bb.jpg")

    def test_skips_items_without_identifier(self) -> None:
        self.assertIsNone(_parse_track({"title": "One"}))


if __name__ == "__main__":
    unittest.main()
