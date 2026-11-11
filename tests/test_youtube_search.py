from __future__ import annotations

import unittest
from unittest.mock import patch

from app.models import Track
from app.providers.youtube import YouTubeProvider


def item(title: str, artist: str, video_id: str = "vid1", duration: str | None = None,
         result_type: str = "song") -> dict:
    data = {
        "resultType": result_type,
        "videoId": video_id,
        "title": title,
        "artists": [{"name": artist}],
    }
    if duration:
        data["duration"] = duration
    return data


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, bool]] = []

    def search(self, query: str, filter: str | None = None, limit: int = 10):
        self.calls.append((query, filter == "songs"))
        return self.handler(query, filter == "songs", limit)


def make_provider(handler) -> tuple[YouTubeProvider, FakeClient]:
    client = FakeClient(handler)
    provider = YouTubeProvider()
    provider._client = lambda: client  # type: ignore[method-assign]
    return provider, client


SOURCE = Track(id="s1", title="Midnight Drive", artists=["Neon Harbour"], duration_ms=245000)


class YouTubeSearchTest(unittest.TestCase):
    def test_falls_back_to_unfiltered_when_songs_filter_is_empty(self) -> None:
        def handler(query, filtered, limit):
            if filtered:
                return []
            return [item("Midnight Drive", "Neon Harbour", "exact", "4:05")]

        provider, client = make_provider(handler)
        with patch("app.providers.youtube.time.sleep"):
            found = provider.search(SOURCE)
        self.assertEqual([track.id for track in found], ["exact"])
        self.assertTrue(any(filtered is False for _, filtered in client.calls))

    def test_title_only_query_rescues_weak_artist_query(self) -> None:
        def handler(query, filtered, limit):
            if query.casefold() == "midnight drive":
                return [item("Midnight Drive", "Neon Harbour", "exact", "4:05")]
            return [item("Some Other Song", "Different Artist", "wrong")]

        provider, client = make_provider(handler)
        with patch("app.providers.youtube.time.sleep"):
            found = provider.search(SOURCE)
        self.assertIn("exact", [track.id for track in found])
        self.assertIn(("Midnight Drive", True), client.calls)

    def test_stops_after_first_query_on_strong_match(self) -> None:
        def handler(query, filtered, limit):
            return [item("Midnight Drive", "Neon Harbour", "exact", "4:05")]

        provider, client = make_provider(handler)
        found = provider.search(SOURCE)
        self.assertEqual([track.id for track in found], ["exact"])
        self.assertEqual(len(client.calls), 1)

    def test_accepts_album_card_with_video_id_and_parses_duration(self) -> None:
        def handler(query, filtered, limit):
            if filtered:
                return []
            return [item("СУППА РАГГА СУП", "Дабл Джи", "E49QubKO888", "2:53", "album")]

        provider, _ = make_provider(handler)
        tracks = provider._search_items("Дабл Джи СУППА РАГГА СУП", filtered=False)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].id, "E49QubKO888")
        self.assertEqual(tracks[0].duration_ms, 173000)

    def test_search_query_uses_unfiltered_fallback(self) -> None:
        def handler(query, filtered, limit):
            if filtered:
                return []
            return [item("Roots", "Bob Marley & The Wailers", "roots1")]

        provider, _ = make_provider(handler)
        tracks = provider.search_query("Roots Bob Marley")
        self.assertEqual([track.id for track in tracks], ["roots1"])

    def test_skips_items_without_video_id(self) -> None:
        def handler(query, filtered, limit):
            return [{"resultType": "artist", "title": "Neon Harbour"}]

        provider, _ = make_provider(handler)
        with patch("app.providers.youtube.time.sleep"):
            found = provider.search(SOURCE)
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
