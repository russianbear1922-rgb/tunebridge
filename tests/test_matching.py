from __future__ import annotations

import unittest

from app.matching import (
    AUTO_THRESHOLD,
    REVIEW_THRESHOLD,
    artist_similarity,
    build_queries,
    duration_similarity,
    make_match,
    match_cache_key,
    normalize_text,
    score_candidate,
    search_title,
    similarity,
    stats_for,
    strip_version_suffix,
    title_similarity,
    version_markers,
)
from app.models import Match, Track


def track(
    title: str,
    artists: list[str] | None = None,
    duration_ms: int | None = None,
    track_id: str = "t1",
) -> Track:
    return Track(id=track_id, title=title, artists=artists or [], duration_ms=duration_ms)


class NormalizeTextTest(unittest.TestCase):
    def test_empty_values(self) -> None:
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(""), "")

    def test_case_diacritics_and_yo(self) -> None:
        self.assertEqual(normalize_text("Beyoncé"), "beyonce")
        self.assertEqual(normalize_text("Ёлка"), "елка")

    def test_cyrillic_short_i_preserved(self) -> None:
        self.assertEqual(normalize_text("Неоновый дождь"), "неоновый дождь")
        self.assertEqual(normalize_text("МОЙ ПЛЕЙЛИСТ"), "мой плейлист")

    def test_apostrophes_ampersand_and_punctuation(self) -> None:
        self.assertEqual(normalize_text("Don't Stop Me Now"), "dont stop me now")
        self.assertEqual(normalize_text("June & The Wolves"), "june and the wolves")
        self.assertEqual(normalize_text("AC/DC — Back in Black!"), "ac dc back in black")

    def test_whitespace_collapsed(self) -> None:
        self.assertEqual(normalize_text("  Много    пробелов \n тут "), "много пробелов тут")


class VersionMarkersTest(unittest.TestCase):
    def test_bracket_markers(self) -> None:
        self.assertEqual(version_markers("Song (Remastered 2011)"), {"remaster"})
        self.assertEqual(version_markers("Song [Live at Wembley]"), {"live"})
        self.assertEqual(version_markers("Song (Acoustic Version)"), {"acoustic"})

    def test_dash_suffix_markers(self) -> None:
        self.assertEqual(version_markers("Song - Radio Edit"), {"edit"})
        self.assertEqual(version_markers("Song – Slowed + Reverb"), {"slowed"})
        self.assertEqual(version_markers("Song — Sped Up"), {"sped"})

    def test_feature_credit_is_not_a_version(self) -> None:
        self.assertEqual(version_markers("Song (feat. Someone)"), set())

    def test_plain_title(self) -> None:
        self.assertEqual(version_markers("Midnight Drive"), set())


class StripVersionSuffixTest(unittest.TestCase):
    def test_removes_brackets_and_version_suffix(self) -> None:
        self.assertEqual(strip_version_suffix("Midnight Drive (Remastered 2011)"), "midnight drive")
        self.assertEqual(strip_version_suffix("Midnight Drive - Live at Wembley"), "midnight drive")
        self.assertEqual(strip_version_suffix("Midnight Drive [Extended Mix]"), "midnight drive")

    def test_removes_feature_credit(self) -> None:
        self.assertEqual(strip_version_suffix("Midnight Drive (feat. Someone)"), "midnight drive")
        self.assertEqual(strip_version_suffix("Midnight Drive feat. Someone"), "midnight drive")

    def test_keeps_meaningful_suffix(self) -> None:
        self.assertEqual(strip_version_suffix("Midnight Drive - Part 2"), "midnight drive part 2")

    def test_does_not_strip_dash_inside_title(self) -> None:
        self.assertEqual(strip_version_suffix("Неоновый дождь"), "неоновый дождь")


class SimilarityTest(unittest.TestCase):
    def test_identical_and_empty(self) -> None:
        self.assertEqual(similarity("midnight drive", "midnight drive"), 1.0)
        self.assertEqual(similarity("", "midnight drive"), 0.0)

    def test_containment(self) -> None:
        self.assertEqual(similarity("midnight", "midnight drive"), 0.92)

    def test_unrelated_titles_score_low(self) -> None:
        self.assertLess(similarity("midnight drive", "совершенно другой трек"), 0.5)

    def test_title_similarity_ignores_version_suffix(self) -> None:
        self.assertEqual(title_similarity("Midnight Drive", "Midnight Drive (Remastered)"), 1.0)
        self.assertEqual(title_similarity("Midnight Drive", "Midnight Drive - Live"), 1.0)

    def test_title_similarity_between_different_songs(self) -> None:
        self.assertLess(title_similarity("Midnight Drive", "Северный ветер"), 0.5)


class ArtistSimilarityTest(unittest.TestCase):
    def test_case_insensitive_exact_member(self) -> None:
        self.assertEqual(artist_similarity(["Mira Vale"], ["MIRA VALE"]), 1.0)

    def test_shared_artist_among_many(self) -> None:
        self.assertEqual(
            artist_similarity(["June & The Wolves", "Mira Vale"], ["Mira Vale", "Someone Else"]),
            1.0,
        )

    def test_unrelated_artists(self) -> None:
        self.assertLess(artist_similarity(["Mira Vale"], ["Полярный круг"]), 0.6)

    def test_missing_artists(self) -> None:
        self.assertEqual(artist_similarity([], ["Mira Vale"]), 0.0)
        self.assertEqual(artist_similarity(["Mira Vale"], []), 0.0)


class DurationSimilarityTest(unittest.TestCase):
    def test_unknown_duration_is_neutral(self) -> None:
        self.assertEqual(duration_similarity(None, 222000), 0.5)
        self.assertEqual(duration_similarity(222000, None), 0.5)

    def test_distance_tiers(self) -> None:
        base = 222000
        self.assertEqual(duration_similarity(base, base), 1.0)
        self.assertEqual(duration_similarity(base, base + 3000), 0.92)
        self.assertEqual(duration_similarity(base, base + 8000), 0.78)
        self.assertEqual(duration_similarity(base, base + 15000), 0.45)
        self.assertEqual(duration_similarity(base, base + 25000), 0.2)
        self.assertEqual(duration_similarity(base, base + 60000), 0.0)


class ScoreCandidateTest(unittest.TestCase):
    def test_perfect_match(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        candidate = track("Неоновый дождь", ["Mira Vale"], 222000, "c1")
        self.assertGreaterEqual(score_candidate(source, candidate), 0.99)

    def test_soft_remaster_penalty_keeps_auto(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        remaster = track("Неоновый дождь (Remastered)", ["Mira Vale"], 222000, "c1")
        score = score_candidate(source, remaster)
        self.assertGreaterEqual(score, AUTO_THRESHOLD)
        self.assertLess(score, 1.0)

    def test_live_version_drops_below_auto(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        live = track("Неоновый дождь (Live)", ["Mira Vale"], 222000, "c1")
        score = score_candidate(source, live)
        self.assertLess(score, AUTO_THRESHOLD)
        self.assertGreaterEqual(score, REVIEW_THRESHOLD)

    def test_wrong_artist_prevents_auto(self) -> None:
        source = track("Midnight Drive", ["Neon Harbour"], 245000)
        cover = track("Midnight Drive", ["Somebody Else"], 245000, "c1")
        self.assertLess(score_candidate(source, cover), AUTO_THRESHOLD)

    def test_different_song_scores_low(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        other = track("Северный ветер", ["Полярный круг"], 198000, "c1")
        self.assertLess(score_candidate(source, other), REVIEW_THRESHOLD)

    def test_score_is_clamped(self) -> None:
        source = track("Song", ["Artist"], 100000)
        same = track("Song", ["Artist"], 100000, "c1")
        self.assertLessEqual(score_candidate(source, same), 1.0)
        self.assertGreaterEqual(score_candidate(source, same), 0.0)


class MakeMatchTest(unittest.TestCase):
    def test_no_candidates_is_missing(self) -> None:
        match = make_match(track("Song", ["Artist"]), [])
        self.assertEqual(match.status, "missing")
        self.assertIsNone(match.target)

    def test_confident_candidate_is_auto(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        match = make_match(source, [track("Неоновый дождь", ["Mira Vale"], 222000, "c1")])
        self.assertEqual(match.status, "auto")
        self.assertIsNotNone(match.target)
        self.assertEqual(match.target.id, "c1")

    def test_partial_candidate_goes_to_review(self) -> None:
        source = track("Midnight Drive", ["Neon Harbour"], 245000)
        match = make_match(source, [track("Midnight Drive", ["Somebody Else"], 245000, "c1")])
        self.assertEqual(match.status, "review")
        self.assertIsNotNone(match.target)

    def test_low_score_has_no_target(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222000)
        match = make_match(source, [track("Северный ветер", ["Полярный круг"], 198000, "c1")])
        self.assertEqual(match.status, "missing")
        self.assertIsNone(match.target)
        self.assertEqual(len(match.candidates), 1)

    def test_candidates_sorted_and_deduplicated(self) -> None:
        source = track("Midnight Drive", ["Neon Harbour"], 245000)
        exact = track("Midnight Drive", ["Neon Harbour"], 245000, "exact")
        close = track("Midnight Drive", ["Neon Harbour"], 270000, "close")
        match = make_match(source, [close, exact, exact])
        self.assertEqual([item.track.id for item in match.candidates], ["exact", "close"])


class BuildQueriesTest(unittest.TestCase):
    def test_query_orders_and_title_fallback(self) -> None:
        queries = build_queries(track("Неоновый дождь (feat. Кто-то)", ["Mira Vale"], 222000))
        self.assertEqual(
            queries,
            ["Mira Vale Неоновый дождь", "Неоновый дождь Mira Vale", "Неоновый дождь"],
        )

    def test_title_only(self) -> None:
        self.assertEqual(build_queries(track("Midnight Drive")), ["Midnight Drive"])

    def test_artist_only(self) -> None:
        self.assertEqual(build_queries(track("", ["Neon Harbour"])), ["Neon Harbour"])

    def test_duplicate_queries_collapsed(self) -> None:
        self.assertEqual(build_queries(track("Echo", ["Echo"])), ["Echo Echo", "Echo"])

    def test_artists_limited_to_two(self) -> None:
        queries = build_queries(track("Song", ["One", "Two", "Three"]))
        self.assertEqual(queries[0], "One Two Song")

    def test_empty_track(self) -> None:
        self.assertEqual(build_queries(track("")), [])


class SearchTitleTest(unittest.TestCase):
    def test_strips_brackets_and_features(self) -> None:
        self.assertEqual(search_title("Song (Remastered) [Live] feat. Someone"), "Song")

    def test_trims_dashes(self) -> None:
        self.assertEqual(search_title(" — Song - "), "Song")


class MatchCacheKeyTest(unittest.TestCase):
    def test_deterministic_and_target_scoped(self) -> None:
        source = track("Неоновый дождь", ["Mira Vale"], 222900)
        first = match_cache_key(source, "spotify")
        self.assertEqual(first, match_cache_key(source, "spotify"))
        self.assertNotEqual(first, match_cache_key(source, "youtube"))

    def test_uses_seconds_and_normalized_names(self) -> None:
        source = track("Неоновый Дождь", ["MIRA VALE"], 222900)
        self.assertEqual(
            match_cache_key(source, "spotify"),
            "spotify::неоновый дождь::mira vale::222",
        )

    def test_unknown_duration(self) -> None:
        self.assertTrue(match_cache_key(track("Song", ["Artist"]), "youtube").endswith("::0"))


class StatsTest(unittest.TestCase):
    def test_counts_and_coverage(self) -> None:
        matches = [
            Match(source=track("a"), status="auto"),
            Match(source=track("b"), status="review"),
            Match(source=track("c"), status="missing"),
            Match(source=track("d"), status="auto"),
        ]
        stats = stats_for(matches)
        self.assertEqual((stats.total, stats.auto, stats.review, stats.missing), (4, 2, 1, 1))
        self.assertEqual(stats.found, 3)
        self.assertAlmostEqual(stats.coverage, 0.75)

    def test_empty(self) -> None:
        stats = stats_for([])
        self.assertEqual((stats.total, stats.found, stats.coverage), (0, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
