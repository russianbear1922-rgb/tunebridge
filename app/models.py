from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MatchStatus = Literal["auto", "review", "missing", "manual"]


class Track(BaseModel):
    id: str
    title: str = ""
    artists: list[str] = Field(default_factory=list)
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    cover_url: str | None = None
    url: str | None = None
    source: str | None = None
    explicit: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, value: Any) -> str:
        return str(value) if value is not None else ""

    @field_validator("duration_ms", mode="before")
    @classmethod
    def _duration_int(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class Playlist(BaseModel):
    id: str
    service: str
    title: str
    description: str | None = None
    owner: str | None = None
    cover_url: str | None = None
    url: str | None = None
    track_count: int = 0
    tracks: list[Track] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    track: Track
    score: float = 0.0


class Match(BaseModel):
    source: Track
    target: Track | None = None
    score: float = 0.0
    status: MatchStatus = "missing"
    candidates: list[Candidate] = Field(default_factory=list)


class MatchStats(BaseModel):
    total: int = 0
    auto: int = 0
    review: int = 0
    missing: int = 0
    found: int = 0
    coverage: float = 0.0


class ResolveRequest(BaseModel):
    service: str
    url: str


class ImportRequest(BaseModel):
    filename: str = "playlist.m3u"
    content: str


class TokenRequest(BaseModel):
    token: str


class SpotifyClientRequest(BaseModel):
    client_id: str


class YoutubeHeadersRequest(BaseModel):
    headers: str
    authuser: int | None = None


class YoutubeBrowserRequest(BaseModel):
    label: str | None = None
    authuser: int | None = None


class MatchRequest(BaseModel):
    playlist: Playlist
    target: str


class TransferRequest(BaseModel):
    playlist: Playlist
    target: str
    matches: list[Match]
    title: str | None = None
    description: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    source: Track | None = None


class ExportRequest(BaseModel):
    playlist: Playlist
    formats: list[str] = Field(default_factory=lambda: ["m3u", "csv", "json"])


class TelegramTokenRequest(BaseModel):
    token: str


class TelegramSendRequest(BaseModel):
    playlist: Playlist
    chat: str = ""
    formats: list[str] = Field(default_factory=lambda: ["m3u", "csv", "json"])


class TelegramAuthRequest(BaseModel):
    init_data: str = ""


class TopupRequest(BaseModel):
    package_id: str


class PromoRedeemRequest(BaseModel):
    code: str


class AdEventRequest(BaseModel):
    kind: str


class AdminCreditRequest(BaseModel):
    telegram_id: int | None = None
    user_id: int | None = None
    tokens: int
    reason: str = ""


class AdminPromoRequest(BaseModel):
    count: int = 1
    tokens: int
    max_uses: int = 1
    days: int = 30
    note: str = ""


class AdminRefundRequest(BaseModel):
    order_id: str
    revoke: bool = True
