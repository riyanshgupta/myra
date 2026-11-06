from enum import Enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from typing import Any



class TestChatSession(BaseModel):
    """Continuation state returned from an earlier ``POST /test`` call."""

    chat_id: str
    bx_umidtoken: str
    model: str = "qwen3.7-plus"
    parent_id: str | None = None

class ChatSession(BaseModel):
    """Continuation state returned from an earlier ``POST /test`` call."""

    chat_id: str
    bx_umidtoken: str
    model: str = "qwen3.7-plus"
    parent_id: str | None = None




class ChatResponseMessageType(str, Enum):
    TEXT = "text"
    SONG = "song"
    FUNCTION_CALL = "function_call"


class SongMetadata(BaseModel):
    """Metadata for a song response (message_type == "song")."""

    jiosaavn_id: str
    title: str
    cover_image: str | None = None
    album: str | None = None
    language: str | None = None
    year: int | None = None
    play_count: int | None = None
    label: str | None = None
    duration_seconds: int | None = None
    encrypted_media_url: str | None = None  # not filled; the app gets playback_url
    artists: list[dict[str, str]] | None = None  # list of {"name": ..., "id": ...}
    subtitle: str | None = None  # artists, if your client returns it
    playback_url: str | None = None  # signed stream URL the app plays
    playback_headers: dict[str, str] | None = None  # headers the CDN requires


class FunctionCallMetadata(BaseModel):
    """Metadata for a function call response (message_type == "function_call")."""

    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Response from the assistant chat endpoint."""

    message: str
    message_type: ChatResponseMessageType = ChatResponseMessageType.TEXT
    metadata: SongMetadata | FunctionCallMetadata | None = None
    session: ChatSession | None = None


class ChatRequest(BaseModel):
    """Input for the assistant chat route; omit session to start a new chat."""

    message: str = Field(min_length=1, max_length=2000)
    metaData: dict[str, Any] | None = None  # info about the current song playing, etc.
    session: ChatSession | None = None  # None starts a new chat
    
class UserResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    created_at: datetime

class AuthResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResp
    

class AutoCompleteSongResp(BaseModel):
    jiosaavn_id: str
    title: str
    cover_image: str | None = None
    album: str | None = None
class AutoCompleteArtistResp(BaseModel):
    artist_id: str
    title: str
    cover_image: str | None = None
class TrackAutoCompleteResp(BaseModel):
    songs: list[AutoCompleteSongResp] = Field(default_factory=list)
    artists: list[AutoCompleteArtistResp] = Field(default_factory=list)
    
