"""Persistence operations for playlists and playlist-track membership."""
from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlmodel import select

from models.tracks import Playlist, PlaylistTrack, Track
from repositories.base import BaseRepository


class PlaylistRepository(BaseRepository[Playlist]):
    model = Playlist

    async def create_playlist(self, playlist: Playlist) -> Playlist:
        return await self.create(playlist)

    async def get_owned(self, playlist_id: int, user_id: uuid.UUID) -> Playlist | None:
        result = await self.session.exec(select(Playlist).where(
            Playlist.id == playlist_id, Playlist.user_id == user_id
        ))
        return result.first()

    async def list_owned(self, user_id: uuid.UUID, offset: int, limit: int) -> tuple[list[Playlist], int]:
        rows = await self.session.exec(
            select(Playlist).where(Playlist.user_id == user_id)
            .order_by(Playlist.updated_at.desc()).offset(offset).limit(limit)
        )
        total = (await self.session.exec(
            select(func.count()).select_from(Playlist).where(Playlist.user_id == user_id)
        )).one()
        return list(rows.all()), total

    async def list_tracks(
        self, playlist_id: int, offset: int = 0, limit: int | None = None
    ) -> list[Track]:
        query = (select(Track).join(PlaylistTrack, PlaylistTrack.track_id == Track.id)
                 .where(PlaylistTrack.playlist_id == playlist_id)
                 .order_by(PlaylistTrack.position, PlaylistTrack.added_at))
        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.exec(query)
        return list(result.all())

    async def count_tracks(self, playlist_id: int) -> int:
        return (await self.session.exec(
            select(func.count()).select_from(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == playlist_id)
        )).one()

    async def get_membership(self, playlist_id: int, track_id: int) -> PlaylistTrack | None:
        result = await self.session.exec(select(PlaylistTrack).where(
            PlaylistTrack.playlist_id == playlist_id, PlaylistTrack.track_id == track_id
        ))
        return result.first()

    async def get_last_position(self, playlist_id: int) -> float | None:
        return (await self.session.exec(
            select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id)
        )).one()

    async def list_memberships(self, playlist_id: int) -> list[PlaylistTrack]:
        result = await self.session.exec(select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id))
        return list(result.all())

    async def add_membership(self, membership: PlaylistTrack) -> PlaylistTrack:
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)
        return membership

    async def remove_membership(self, membership: PlaylistTrack) -> None:
        await self.session.delete(membership)
        await self.session.commit()

    async def save_playlist(self, playlist: Playlist, changes: dict) -> Playlist:
        return await self.update(playlist, changes)

    async def delete_playlist(self, playlist: Playlist, memberships: list[PlaylistTrack]) -> None:
        for membership in memberships:
            await self.session.delete(membership)
        await self.session.delete(playlist)
        await self.session.commit()
