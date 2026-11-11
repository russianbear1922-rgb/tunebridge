from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .models import Candidate, Match, MatchStats, Track

AUTO_THRESHOLD = 0.84
REVIEW_THRESHOLD = 0.58
MAX_CANDIDATES = 6

_BRACKETS_RE = re.compile(r"[\(\[]([^\)\]]*)[\)\]]", re.UNICODE)
_FEAT_RE = re.compile(r"\b(?:feat|ft|featuring|prod|prod\.|with)\b.*$", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES_RE = re.compile(r"\s+", re.UNICODE)
_APOSTROPHE_RE = re.compile(r"['`´’]")

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "of",
    "feat",
    "ft",
    "featuring",
    "prod",
    "with",
    "vs",
}

_VERSION_PATTERNS = [
    (re.compile(r"\bremaster(?:ed|ing)?\b", re.I), "remaster"),
    (re.compile(r"\brmx\b|\bremix(?:ed)?\b", re.I), "remix"),
    (re.compile(r"\bunplugged\b|\blive\b", re.I), "live"),
    (re.compile(r"\bacoustic\b", re.I), "acoustic"),
    (re.compile(r"\binstrumental\b", re.I), "instrumental"),
    (re.compile(r"\bkaraoke\b", re.I), "karaoke"),
    (re.compile(r"\bdemo\b", re.I), "demo"),
    (re.compile(r"\bradio\s+edit\b|\bedit\b", re.I), "edit"),
    (re.compile(r"\bdeluxe\b|\bbonus\b", re.I), "deluxe"),
    (re.compile(r"\bextended\b", re.I), "extended"),
    (re.compile(r"\bsped\s*up\b", re.I), "sped"),
    (re.compile(r"\bslowed\b|\breverb\b", re.I), "slowed"),
    (re.compile(r"\bnightcore\b", re.I), "nightcore"),
    (re.compile(r"\bmono\b", re.I), "mono"),
    (re.compile(r"\bstereo\b", re.I), "stereo"),
]

_SOFT_VERSIONS = {"remaster", "deluxe", "mono", "stereo"}


def _drop_marks(text: str) -> str:
    result: list[str] = []
    base = ""
    for ch in text:
        if unicodedata.combining(ch):
            if base and "\u0400" <= base <= "\u04ff":
                result.append(ch)
            continue
        result.append(ch)
        base = ch
    return unicodedata.normalize("NFC", "".join(result))


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = _drop_marks(unicodedata.normalize("NFKD", value))
    text = text.casefold().replace("ё", "е")
    text = _APOSTROPHE_RE.sub("", text)
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def _tokens(value: str) -> set[str]:
    return {word for word in normalize_text(value).split() if word and word not in _STOPWORDS}


def _markers_in_text(text: str) -> set[str]:
    markers: set[str] = set()
    for pattern, marker in _VERSION_PATTERNS:
        if pattern.search(text):
            markers.add(marker)
    return markers


def version_markers(title: str) -> set[str]:
    chunks = [match.group(1) for match in _BRACKETS_RE.finditer(title or "")]
    parts = re.split(r"\s+[-–—]\s+", title or "")
    if len(parts) > 1:
        chunks.extend(parts[1:])
    return _markers_in_text(" ".join(chunks))


def strip_version_suffix(title: str) -> str:
    text = _BRACKETS_RE.sub(" ", title or "")
    parts = re.split(r"(\s+[-–—]\s+)", text)
    if len(parts) > 1:
        kept = [parts[0]]
        for index in range(1, len(parts), 2):
            suffix = parts[index + 1] if index + 1 < len(parts) else ""
            if _markers_in_text(suffix):
                break
            kept.append(parts[index])
            kept.append(suffix)
        text = "".join(kept)
    text = _FEAT_RE.sub(" ", text)
    return normalize_text(text)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right, autojunk=False).ratio()
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if left_tokens and right_tokens:
        jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    else:
        jaccard = 0.0
    containment = 0.0
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 4 and shorter in longer:
        containment = 0.92
    return max(ratio, jaccard, containment)


def title_similarity(left: str, right: str) -> float:
    base = similarity(strip_version_suffix(left), strip_version_suffix(right))
    full = similarity(normalize_text(left), normalize_text(right))
    return max(base, full * 0.97)


def artist_similarity(source_artists: list[str], candidate_artists: list[str]) -> float:
    source = [normalize_text(name) for name in source_artists if normalize_text(name)]
    candidate = [normalize_text(name) for name in candidate_artists if normalize_text(name)]
    if not source or not candidate:
        return 0.0
    best = max(similarity(left, right) for left in source for right in candidate)
    joined = similarity(" ".join(source), " ".join(candidate))
    exact_member = any(left == right for left in source for right in candidate)
    if exact_member:
        best = 1.0
    return max(best, joined)


def duration_similarity(source_ms: int | None, candidate_ms: int | None) -> float:
    if not source_ms or not candidate_ms:
        return 0.5
    diff = abs(source_ms - candidate_ms) / 1000
    if diff <= 2:
        return 1.0
    if diff <= 5:
        return 0.92
    if diff <= 10:
        return 0.78
    if diff <= 20:
        return 0.45
    if diff <= 30:
        return 0.2
    return 0.0


def _version_penalty(source_title: str, candidate_title: str) -> float:
    source = version_markers(source_title)
    candidate = version_markers(candidate_title)
    if source == candidate:
        return 0.0
    missing_in_candidate = source - candidate
    extra_in_candidate = candidate - source
    penalty = 0.0
    if missing_in_candidate:
        penalty = max(penalty, 0.2)
    if extra_in_candidate:
        soft = extra_in_candidate.issubset(_SOFT_VERSIONS)
        penalty = max(penalty, 0.035 if soft else 0.2)
    return penalty


def score_candidate(source: Track, candidate: Track) -> float:
    title = title_similarity(source.title, candidate.title)
    artists = artist_similarity(source.artists, candidate.artists)
    duration = duration_similarity(source.duration_ms, candidate.duration_ms)
    score = 0.58 * title + 0.32 * artists + 0.10 * duration
    if title >= 0.95 and artists >= 0.6:
        score += 0.02
    if title < 0.5 and artists < 0.3:
        score *= 0.78
    score -= _version_penalty(source.title, candidate.title)
    return max(0.0, min(1.0, score))


def score_candidates(
    source: Track,
    candidates: list[Track],
    limit: int = MAX_CANDIDATES,
) -> list[Candidate]:
    seen: set[str] = set()
    scored: list[Candidate] = []
    for track in candidates:
        key = track.id or f"{normalize_text(track.title)}|{normalize_text(' '.join(track.artists))}"
        if key in seen:
            continue
        seen.add(key)
        score = score_candidate(source, track)
        scored.append(Candidate(track=track, score=round(score, 4)))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


def make_match(source: Track, candidates: list[Track]) -> Match:
    scored = score_candidates(source, candidates)
    if not scored:
        return Match(source=source, status="missing", score=0.0)
    best = scored[0]
    if best.score >= AUTO_THRESHOLD:
        status = "auto"
    elif best.score >= REVIEW_THRESHOLD:
        status = "review"
    else:
        status = "missing"
    return Match(
        source=source,
        target=best.track if status != "missing" else None,
        score=best.score,
        status=status,
        candidates=scored,
    )


def stats_for(matches: list[Match]) -> MatchStats:
    auto = sum(1 for item in matches if item.status == "auto")
    review = sum(1 for item in matches if item.status == "review")
    missing = sum(1 for item in matches if item.status == "missing")
    total = len(matches)
    found = total - missing
    return MatchStats(
        total=total,
        auto=auto,
        review=review,
        missing=missing,
        found=found,
        coverage=round(found / total, 4) if total else 0.0,
    )


def search_title(title: str) -> str:
    text = _BRACKETS_RE.sub(" ", title or "")
    text = _FEAT_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip(" -–—")
    return text or (title or "").strip()


def build_queries(track: Track) -> list[str]:
    artists = " ".join(name for name in track.artists[:2] if name).strip()
    title = search_title(track.title)
    queries: list[str] = []
    if artists and title:
        queries.append(f"{artists} {title}")
        queries.append(f"{title} {artists}")
        queries.append(title)
    elif title:
        queries.append(title)
    elif artists:
        queries.append(artists)
    unique: list[str] = []
    for query in queries:
        query = _SPACES_RE.sub(" ", query).strip()
        if query and query.casefold() not in {item.casefold() for item in unique}:
            unique.append(query)
    return unique


def match_cache_key(track: Track, target: str) -> str:
    artists = "|".join(normalize_text(name) for name in track.artists)
    duration = (track.duration_ms or 0) // 1000
    return f"{target}::{normalize_text(track.title)}::{artists}::{duration}"
