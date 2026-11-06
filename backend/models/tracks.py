import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text, Index
from sqlmodel import Field

from db.base_model import IntBaseModel, utcnow


# id, created_at and updated_at come from BaseModel (with server-side defaults),
# so they are not redefined here.


class Playlist(IntBaseModel, table=True):
    """ Represents a playlist created by a user"""
    __tablename__ = "playlists"

    name: str = Field(index=True, max_length=100, description="playlist name in lowercase")
    description: str | None = Field(default=None, max_length=500, description="playlist description")

    # user id of the playlist owner
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, description="ID of the user who owns the playlist")


class Track(IntBaseModel, table=True):
    """ Represents a music track """
    __tablename__ = "tracks"

    title: str = Field(index=True, max_length=200, description="track title in lowercase")
    artist: str = Field(index=True, max_length=100, description="artist name in lowercase")
    album: str | None = Field(default=None, max_length=100, description="album name in lowercase")
    cover_image: str | None = Field(default=None, max_length=500, description="URL of the cover image")
    language: str | None = Field(default=None, max_length=50, description="language of the track")
    year: int | None = Field(default=None, description="release year of the track")
    label: str | None = Field(default=None, max_length=100, description="label of the track")
    play_count: int = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
        description="number of times the track has been played all over the internet",
    )
    jiosaavn_id: str = Field(index=True, unique=True, max_length=50, description="JioSaavn track ID")
    duration_seconds: int = Field(gt=0, description="Duration in seconds")


class PlaylistTrack(IntBaseModel, table=True):
    """ Represents the relationship between a playlist and a track """
    __tablename__ = "playlist_tracks"

    playlist_id: int = Field(foreign_key="playlists.id", index=True, description="ID of the playlist")
    track_id: int = Field(foreign_key="tracks.id", index=True, description="ID of the track")
    added_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    # Rank of the track in the playlist, lower is higher priority
    position: float = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
        description="Position of the track in the playlist",
    )


class FavoriteTrack(IntBaseModel, table=True):
    """A user's saved tracks."""
    __tablename__ = "favorite_tracks"
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    track_id: int = Field(foreign_key="tracks.id", index=True)
    __table_args__ = (Index("uq_favorite_user_track", "user_id", "track_id", unique=True),)


class QueueTrack(IntBaseModel, table=True):
    """An ordered, per-user playback queue."""
    __tablename__ = "queue_tracks"
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    track_id: int = Field(foreign_key="tracks.id", index=True)
    position: int = Field(ge=0)
    added_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    __table_args__ = (Index("uq_queue_user_position", "user_id", "position", unique=True),)


class PlaybackState(IntBaseModel, table=True):
    """Current player state for a user."""
    __tablename__ = "playback_states"
    user_id: uuid.UUID = Field(foreign_key="users.id", unique=True, index=True)
    current_track_id: int | None = Field(default=None, foreign_key="tracks.id")
    is_playing: bool = Field(default=False)
    shuffle: bool = Field(default=False)
    repeat_mode: str = Field(default="off", max_length=10)
    position_seconds: int = Field(default=0, ge=0)
