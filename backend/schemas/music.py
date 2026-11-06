"""Typed response models for music, library, playlist, and playback APIs."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArtistRef(BaseModel):
    name: str = "Unknown"
    id: str | None = None


class SongResponse(BaseModel):
    encrypted_media_url: str | None = None
    jiosaavn_id: str
    title: str = "Unknown"
    subtitle: str | None = None
    cover_image: str | None = None
    language: str | None = None
    year: int | None = None
    play_count: int | None = None
    album: str | None = None
    label: str | None = None
    duration_seconds: int | None = None
    artists: list[ArtistRef] = Field(default_factory=list)


class ArtistSearchResponse(BaseModel):
    artist_id: str
    title: str
    cover_image: str | None = None
    url: str | None = None


class SearchResponse(BaseModel):
    songs: list[SongResponse]
    artists: list[ArtistSearchResponse]
    page: int
    limit: int


class SearchResultsResponse(BaseModel):
    songs: list[SongResponse]
    artists: list[ArtistSearchResponse]


class SongPageResponse(BaseModel):
    items: list[SongResponse]
    offset: int = 0
    page: int | None = None
    limit: int
    total: int | None = None
    songs: list[SongResponse] | None = None
    source_track_id: str | None = None


class ArtistTrackPageResponse(BaseModel):
    data: list[SongResponse]
    page: int
    limit: int


class StreamResponse(BaseModel):
    playback_url: str
    playback_headers: dict[str, str]


class TrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jiosaavn_id: str
    title: str
    artist: str
    album: str | None = None
    cover_image: str | None = None
    language: str | None = None
    year: int | None = None
    label: str | None = None
    play_count: int = 0
    duration_seconds: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TrackPageResponse(BaseModel):
    items: list[TrackResponse]
    offset: int
    limit: int
    total: int


class HistoryTrackResponse(TrackResponse):
    user_play_count: int
    last_played_at: datetime


class HistoryPageResponse(BaseModel):
    items: list[HistoryTrackResponse]
    offset: int
    limit: int
    total: int


class RecordPlayResponse(BaseModel):
    track_id: int
    play_count: int
    user_play_count: int


class FavoriteTrackResponse(TrackResponse):
    favorite_id: int


class FavoritePageResponse(BaseModel):
    items: list[FavoriteTrackResponse]
    offset: int
    limit: int
    total: int


class FavoriteAddedResponse(BaseModel):
    favorite: bool
    track: TrackResponse


class PlaylistResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    tracks: list[TrackResponse] = Field(default_factory=list)


class PlaylistPageResponse(BaseModel):
    items: list[PlaylistResponse]
    offset: int
    limit: int
    total: int


class PlaylistDetailResponse(PlaylistResponse):
    offset: int
    limit: int
    total: int


class PlaylistTrackAddedResponse(BaseModel):
    playlist_id: int
    track: TrackResponse
    position: float


class QueueItemResponse(BaseModel):
    queue_id: int
    position: int
    is_current: bool
    track: TrackResponse


class QueueResponse(BaseModel):
    items: list[QueueItemResponse]
    total: int


class QueueTrackAddedResponse(BaseModel):
    queue_id: int
    position: int
    track: TrackResponse


class PlayerStateResponse(BaseModel):
    current_track: TrackResponse | None = None
    is_playing: bool
    shuffle: bool
    repeat_mode: str
    position_seconds: int
    queue: list[QueueItemResponse] | None = None
    queue_total: int | None = None


class HealthResponse(BaseModel):
    status: str


class TestChatSessionResponse(BaseModel):
    chat_id: str
    bx_umidtoken: str
    model: str
    parent_id: str | None = None


class TestChatResponse(BaseModel):
    reply: str
    elapsed_seconds: float
    session: TestChatSessionResponse


class TestSaavnResponse(BaseModel):
    results: SearchResultsResponse
    elapsed_seconds: float
