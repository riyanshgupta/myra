"""One tool, several actions: search, artist_top_tracks, trending_hindi, stream_url."""
from __future__ import annotations

import uuid
from collections import OrderedDict
from config import settings
from typing import TYPE_CHECKING, Any

from agent.tools.base import (
    ClientEvent,
    Tool,
    ToolArgumentError,
    ToolResult,
    get_limit,
    require_str,
)
from clients.saavn_client import STREAM_HEADERS

if TYPE_CHECKING:
    from clients.saavn_provider import SaavnProvider
    from services.playback_service import PlaybackService

# jiosaavn_id -> formatted song. Filled from search results so stream_url needs
# no extra lookup and can return full song metadata. Shared across requests.
_CACHE_SIZE = 500
_song_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

logger = settings.get_logger("jiosaavn_tool")

def _remember(songs: list[dict[str, Any]]) -> None:
    for song in songs:
        song_id = song.get("jiosaavn_id")
        if song_id and song.get("encrypted_media_url"):
            _song_cache[song_id] = song
            _song_cache.move_to_end(song_id)
    while len(_song_cache) > _CACHE_SIZE:
        _song_cache.popitem(last=False)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slim(song: dict[str, Any]) -> dict[str, Any]:
    """Only what the LLM needs. Long URLs and images stay out of its context."""
    fields = {
        "id": song.get("jiosaavn_id"),
        "title": song.get("title"),
        "subtitle": song.get("subtitle"),  # artists, if your client returns it
        "album": song.get("album"),
        "language": song.get("language"),
        "year": song.get("year"),
        "duration_seconds": song.get("duration_seconds"),
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _song_payload(song_id: str, song: dict[str, Any], playback_url: str) -> dict[str, Any]:
    """Matches SongMetadata. Numbers are coerced because JioSaavn sends strings."""
    artists = song.get("artists")
    return {
        "jiosaavn_id": song_id,
        "title": song.get("title") or "Unknown",
        "cover_image": song.get("cover_image"),
        "album": song.get("album"),
        "language": song.get("language"),
        "year": _to_int(song.get("year")),
        "play_count": _to_int(song.get("play_count")),
        "label": song.get("label"),
        "duration_seconds": _to_int(song.get("duration_seconds")),
        "subtitle": song.get("subtitle"),
        "artists": artists if isinstance(artists, list) else None,
        "playback_url": playback_url,
        "playback_headers": STREAM_HEADERS,
    }


class JioSaavnTool(Tool):
    name = "jiosaavn"
    tool_type = "backend"
    description = """Search and play music from JioSaavn. Set `action` to one of:
- search: find songs. Arguments: query (text), limit (optional, default 5).
- artist_top_tracks: popular songs by an artist. Arguments: artist (name), limit (optional, default 10).
- trending_hindi: the current top Hindi chart. Arguments: limit (optional, default 10).
- stream_url: start playing a song in the app. Arguments: song_id (an `id` from an earlier result). Starting a different song also replaces the user's queue with artist recommendations.
Songs come back with id, title, album, year, language and duration_seconds."""

    def __init__(self, client: SaavnProvider, playback_service: PlaybackService | None = None) -> None:
        self._client = client
        self._playback_service = playback_service
        self._actions = {
            "search": self._search,
            "artist_top_tracks": self._artist_top_tracks,
            "trending_hindi": self._trending_hindi,
            "stream_url": self._stream_url,
        }

    async def execute(self, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        action = args.get("action")
        handler = self._actions.get(action) if isinstance(action, str) else None
        if handler is None:
            return ToolResult.failure(f"Unknown action. Use one of: {', '.join(self._actions)}")
        try:
            if action == "stream_url":
                return await self._stream_url(args, user_id)
            return await handler(args)
        except ToolArgumentError as exc:
            return ToolResult.failure(str(exc))

    async def _search(self, args: dict[str, Any]) -> ToolResult:
        logger.info(f"[_search] args: {args}")
        songs = (await self._client.search(require_str(args, "query"))).get("songs", [])
        _remember(songs)
        limit = get_limit(args, default=5, maximum=10)
        return ToolResult.success({"songs": [_slim(s) for s in songs[:limit]]})

    async def _artist_top_tracks(self, args: dict[str, Any]) -> ToolResult:
        logger.info(f"[_artist_top_tracks] args: {args}")
        songs = await self._client.get_top_tracks_by_artist(require_str(args, "artist"))
        _remember(songs)
        limit = get_limit(args, default=10, maximum=30)
        return ToolResult.success({"songs": [_slim(s) for s in songs[:limit]]})

    async def _trending_hindi(self, args: dict[str, Any]) -> ToolResult:
        logger.info(f"[_trending_hindi] args: {args}")
        raw = await self._client.get_top_trending_hindi()
        # this client method returns raw playlist items, so format them first
        songs = self._client._format_song_data(raw)
        _remember(songs)
        limit = get_limit(args, default=10, maximum=50)
        return ToolResult.success({"songs": [_slim(s) for s in songs[:limit]]})

    async def _stream_url(self, args: dict[str, Any], user_id: uuid.UUID) -> ToolResult:
        logger.info(f"[_stream_url] args: {args}")
        song_id = require_str(args, "song_id")

        song = _song_cache.get(song_id)
        if song is None:
            songs = await self._client.get_song(song_id)
            if not songs or not songs[0].get("encrypted_media_url"):
                return ToolResult.failure("Song not found or not streamable")
            song = songs[0]

        audio = await self._client.get_audio(song["encrypted_media_url"])
        playback_url = audio.get("auth_url")
        if not playback_url:
            return ToolResult.failure("No stream URL available for this song")

        if self._playback_service is not None:
            await self._playback_service.select_track_and_replace_queue(user_id, song, True)

        return ToolResult.success(
            {"song_id": song_id, "title": song.get("title"), "status": "stream ready, the app will play it"},
            client_event=ClientEvent("song", _song_payload(song_id, song, playback_url)),
        )
