from schemas.resp import TestChatSession
from pydantic import BaseModel, BeforeValidator, Field
from typing import Annotated, Any

class TestChatRequest(BaseModel):
    """Input for the Qwen smoke-test route; omit session to start a new chat."""

    message: str = Field(default="Hello, how are you?", min_length=1)
    session: TestChatSession | None = None
    

def _normalize_username(v):
    return v.strip().lower() if isinstance(v, str) else v


Username = Annotated[
    str,
    BeforeValidator(_normalize_username),
    Field(pattern=r"^[a-z0-9_]{3,30}$"),
]
Pin = Annotated[str, Field(pattern=r"^\d{6}$")]


class RegisterReq(BaseModel):
    username: Username
    pin: Pin


class LoginReq(BaseModel):
    username: Username
    pin: Pin


class ChangePinReq(BaseModel):
    current_pin: Pin
    new_pin: Pin


class PlaylistCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class PlaylistTrackReq(BaseModel):
    jiosaavn_id: str = Field(min_length=1, max_length=50)


class QueueTrackReq(BaseModel):
    jiosaavn_id: str = Field(min_length=1, max_length=50)


class PlaybackStateReq(BaseModel):
    jiosaavn_id: str | None = None
    encrypted_media_url: str | None = None
    is_playing: bool | None = None
    shuffle: bool | None = None
    repeat_mode: str | None = Field(default=None, pattern="^(off|one|all)$")
    position_seconds: int | None = Field(default=None, ge=0)


class QueueReorderReq(BaseModel):
    positions: list[int] = Field(min_length=1)


class PlaylistUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    

# ---- assistant chat ----------------------------------------------------------
class ChatSession(BaseModel):
    """Qwen chat state (your TestChatSession). The app sends it back each turn.
    Lives here and is imported by resp.py, so req.py never imports resp.py."""
 
    chat_id: str
    bx_umidtoken: str
    model: str = "qwen3.7-plus"
    parent_id: str | None = None
 
 
class ChatRequest(BaseModel):
    """Input for the assistant chat route; omit session to start a new chat."""
 
    message: str = Field(min_length=1, max_length=2000)
    metaData: dict[str, Any] | None = None  # info about the current song playing, etc.
    session: ChatSession | None = None  # None starts a new chat
    
