"""Playlist ownership and membership business rules."""
from __future__ import annotations

import uuid

from exceptions import (
    InvalidRequestError,
    ResourceConflictError,
    ResourceForbiddenError,
    ResourceNotFoundError,
)
from models.tracks import Playlist, PlaylistTrack
from repositories.playlist_repo import PlaylistRepository
from services.track_service import TrackService


class PlaylistService:
    PREVIEW_TRACK_LIMIT = 5

    def __init__(self, repo: PlaylistRepository, track_service: TrackService) -> None:
        self.repo = repo
        self.track_service = track_service

    async def create(self, user_id: uuid.UUID, name: str, description: str | None) -> dict:
        name = name.strip()
        if not name:
            raise InvalidRequestError("Playlist name cannot be blank")
        playlist = Playlist(name=name, description=description, user_id=user_id)
        playlist = await self.repo.create_playlist(playlist)
        return {**playlist.model_dump(), "tracks": []}

    async def list(self, user_id: uuid.UUID, offset: int, limit: int) -> dict:
        playlists, total = await self.repo.list_owned(user_id, offset, limit)
        items = []
        for playlist in playlists:
            tracks = await self.repo.list_tracks(playlist.id, limit=self.PREVIEW_TRACK_LIMIT)
            items.append({**playlist.model_dump(), "tracks": tracks})
        return {"items": items, "offset": offset, "limit": limit, "total": total}

    async def get(self, user_id: uuid.UUID, playlist_id: int, offset: int, limit: int) -> dict:
        playlist = await self._get_owned(user_id, playlist_id)
        tracks = await self.repo.list_tracks(playlist_id, offset, limit)
        total = await self.repo.count_tracks(playlist_id)
        return {**playlist.model_dump(), "tracks": tracks, "offset": offset, "limit": limit, "total": total}

    async def add_track(self, user_id: uuid.UUID, playlist_id: int, jiosaavn_id: str) -> dict:
        await self._get_owned(user_id, playlist_id)
        track = await self.track_service.get_or_create(jiosaavn_id)
        if track is None:
            raise ResourceNotFoundError("Track not found")
        if await self.repo.get_membership(playlist_id, track.id):
            raise ResourceConflictError("Track is already in this playlist")
        last_position = await self.repo.get_last_position(playlist_id)
        membership = PlaylistTrack(
            playlist_id=playlist_id, track_id=track.id,
            position=(last_position if last_position is not None else -1) + 1,
        )
        membership = await self.repo.add_membership(membership)
        return {
            "playlist_id": playlist_id,
            "track": self.track_service.track_payload(track),
            "position": membership.position,
        }

    async def remove_track(self, user_id: uuid.UUID, playlist_id: int, track_id: int) -> None:
        await self._get_owned(user_id, playlist_id)
        membership = await self.repo.get_membership(playlist_id, track_id)
        if membership is None:
            raise ResourceNotFoundError("Track is not in this playlist")
        await self.repo.remove_membership(membership)

    async def update(
        self, user_id: uuid.UUID, playlist_id: int, changes: dict
    ) -> dict:
        playlist = await self._get_owned(user_id, playlist_id)
        if "name" in changes:
            changes["name"] = changes["name"].strip()
            if not changes["name"]:
                raise InvalidRequestError("Playlist name cannot be blank")
        playlist = await self.repo.save_playlist(playlist, changes)
        return {**playlist.model_dump(), "tracks": []}

    async def delete(self, user_id: uuid.UUID, playlist_id: int) -> None:
        playlist = await self._get_owned(user_id, playlist_id)
        memberships = await self.repo.list_memberships(playlist_id)
        await self.repo.delete_playlist(playlist, memberships)

    async def _get_owned(self, user_id: uuid.UUID, playlist_id: int) -> Playlist:
        playlist = await self.repo.get_owned(playlist_id, user_id)
        if playlist is None:
            exists = await self.repo.get(playlist_id)
            if exists is None:
                raise ResourceNotFoundError("Playlist not found")
            raise ResourceForbiddenError("You do not own this playlist")
        return playlist
