"""Track catalog, provider, listening-history, and favorite business logic."""
from __future__ import annotations

import uuid

from config import settings
from clients.saavn_client import JioSaavnClient
from db.base_model import utcnow
from exceptions import MusicProviderError
from models.tracks import FavoriteTrack, Track
from repositories.track_repo import TrackRepository

logger = settings.get_logger("track_service")


class TrackService:
    def __init__(self, repo: TrackRepository, saavn_client: JioSaavnClient) -> None:
        self.repo = repo
        self.saavn_client = saavn_client

    async def autocomplete(self, query: str) -> dict:
        return await self._provider_call("autocomplete", self.saavn_client.autocomplete(query))

    async def search(self, query: str, page: int, limit: int) -> dict:
        result = await self._provider_call("search", self.saavn_client.search(query, limit=limit, page=page))
        return {**result, "page": page, "limit": limit}

    async def trending(self, offset: int, limit: int) -> dict:
        raw = await self._provider_call("trending", self.saavn_client.get_top_trending_hindi())
        songs = self.saavn_client._format_song_data(raw)
        page = songs[offset:offset + limit]
        return {"items": page, "offset": offset, "limit": limit, "total": len(songs)}

    async def recommended(self, track_id: str, limit: int) -> dict | None:
        songs = await self._provider_call("recommended song lookup", self.saavn_client.get_song(track_id))
        if not songs:
            return None
        current = songs[0]
        artist_ids = [str(a.get("id")) for a in current.get("artists", []) if a.get("id")]
        recommendations = await self._provider_call("artist recommendations", self.saavn_client.get_artist_other_top_songs(
            artist_ids, track_id, current.get("language")
        ))
        return {"items": recommendations[:limit], "source_track_id": track_id, "limit": limit}

    async def get_song(self, jiosaavn_id: str) -> dict | None:
        songs = await self._provider_call("song lookup", self.saavn_client.get_song(jiosaavn_id))
        return songs[0] if songs else None

    async def artist_top_tracks(self, artist_id: str, page: int, limit: int) -> dict:
        songs = await self._provider_call("artist top tracks", self.saavn_client.get_top_tracks_by_artist_id(artist_id, page))
        return {"data": songs[:limit], "page": page, "limit": limit}

    async def stream_url(self, encrypted_media_url: str) -> dict | None:
        result = await self._provider_call("audio URL", self.saavn_client.get_audio(encrypted_media_url))
        if not result.get("auth_url"):
            return None
        from clients.saavn_client import STREAM_HEADERS
        return {"playback_url": result["auth_url"], "playback_headers": STREAM_HEADERS}

    @staticmethod
    def song_to_model(song: dict, jiosaavn_id: str | None = None) -> Track:
        artists = song.get("artists") or []
        artist_names = ", ".join(a.get("name", "") for a in artists if a.get("name"))
        year = song.get("year")
        try:
            duration = int(song.get("duration_seconds") or 1)
        except (TypeError, ValueError):
            duration = 1
        return Track(
            title=song.get("title") or "Unknown",
            artist=artist_names or song.get("subtitle") or "Unknown",
            album=song.get("album"), cover_image=song.get("cover_image"),
            language=song.get("language"),
            year=int(year) if year and str(year).isdigit() else None,
            label=song.get("label"), jiosaavn_id=jiosaavn_id or song.get("jiosaavn_id"),
            duration_seconds=max(1, duration),
        )

    async def get_or_create(self, jiosaavn_id: str) -> Track | None:
        track = await self.repo.get_by_jiosaavn_id(jiosaavn_id)
        if track:
            return track
        song = await self.get_song(jiosaavn_id)
        if not song:
            return None
        return await self.get_or_create_from_song(song, jiosaavn_id)

    async def get_or_create_from_song(self, song: dict, jiosaavn_id: str | None = None) -> Track:
        song_id = jiosaavn_id or song.get("jiosaavn_id")
        track = await self.repo.get_by_jiosaavn_id(song_id)
        if track:
            return track
        return await self.repo.insert_track(self.song_to_model(song, song_id))

    @staticmethod
    async def _provider_call(operation: str, request):
        try:
            return await request
        except Exception as exc:
            logger.exception("Music provider request failed during %s", operation)
            raise MusicProviderError() from exc

    async def most_played(self, offset: int, limit: int) -> dict:
        items, total = await self.repo.list_most_played(offset, limit)
        return {"items": items, "offset": offset, "limit": limit, "total": total}

    async def recently_played(self, user_id: uuid.UUID, offset: int, limit: int) -> dict:
        rows, total = await self.repo.list_recently_played(user_id, offset, limit)
        items = [
            {**track.model_dump(), "user_play_count": count, "last_played_at": updated_at}
            for track, count, updated_at in rows
        ]
        return {"items": items, "offset": offset, "limit": limit, "total": total}

    async def record_play(self, user_id: uuid.UUID, jiosaavn_id: str) -> dict | None:
        track = await self.get_or_create(jiosaavn_id)
        if track is None:
            return None
        metadata = await self.repo.get_user_metadata(user_id, track.id)
        metadata = await self.repo.apply_play(user_id, track, metadata, utcnow())
        await self.repo.commit()
        return {"track_id": track.id, "play_count": track.play_count, "user_play_count": metadata.cnt}

    async def favorites(self, user_id: uuid.UUID, offset: int, limit: int) -> dict:
        rows, total = await self.repo.list_favorites(user_id, offset, limit)
        return {
            "items": [{**self.track_payload(track), "favorite_id": favorite.id} for favorite, track in rows],
            "offset": offset, "limit": limit, "total": total,
        }

    async def add_favorite(self, user_id: uuid.UUID, jiosaavn_id: str) -> dict | None:
        track = await self.get_or_create(jiosaavn_id)
        if track is None:
            return None
        favorite = await self.repo.get_favorite(user_id, track.id)
        if favorite is None:
            favorite = FavoriteTrack(user_id=user_id, track_id=track.id)
            await self.repo.add_favorite(favorite)
        return {"favorite": True, "track": self.track_payload(track)}

    async def remove_favorite(self, user_id: uuid.UUID, jiosaavn_id: str) -> None:
        track = await self.repo.get_by_jiosaavn_id(jiosaavn_id)
        if track:
            favorite = await self.repo.get_favorite(user_id, track.id)
            if favorite:
                await self.repo.remove_favorite(favorite)

    @staticmethod
    def track_payload(track: Track) -> dict:
        return {
            "id": track.id, "jiosaavn_id": track.jiosaavn_id, "title": track.title,
            "artist": track.artist, "album": track.album, "cover_image": track.cover_image,
            "language": track.language, "year": track.year, "label": track.label,
            "duration_seconds": track.duration_seconds, "play_count": track.play_count,
        }
