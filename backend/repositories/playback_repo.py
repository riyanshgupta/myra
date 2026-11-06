"""Persistence operations for per-user playback state and queue."""
from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlmodel import select

from models.tracks import PlaybackState, QueueTrack, Track
from repositories.base import BaseRepository


class PlaybackRepository(BaseRepository[PlaybackState]):
    model = PlaybackState

    async def get_state(self, user_id: uuid.UUID) -> PlaybackState | None:
        result = await self.session.exec(select(PlaybackState).where(PlaybackState.user_id == user_id))
        return result.first()

    async def get_track(self, track_id: int) -> Track | None:
        return await self.session.get(Track, track_id)

    async def get_queue(self, user_id: uuid.UUID) -> list[tuple[QueueTrack, Track]]:
        result = await self.session.exec(
            select(QueueTrack, Track).join(Track, QueueTrack.track_id == Track.id)
            .where(QueueTrack.user_id == user_id).order_by(QueueTrack.position)
        )
        return list(result.all())

    async def get_queue_item(self, user_id: uuid.UUID, queue_id: int) -> QueueTrack | None:
        result = await self.session.exec(select(QueueTrack).where(
            QueueTrack.user_id == user_id, QueueTrack.id == queue_id
        ))
        return result.first()

    async def list_queue_items(self, user_id: uuid.UUID) -> list[QueueTrack]:
        result = await self.session.exec(select(QueueTrack).where(QueueTrack.user_id == user_id))
        return list(result.all())

    async def queue_count(self, user_id: uuid.UUID) -> int:
        return (await self.session.exec(
            select(func.count()).select_from(QueueTrack).where(QueueTrack.user_id == user_id)
        )).one()

    async def last_queue_position(self, user_id: uuid.UUID) -> int | None:
        return (await self.session.exec(
            select(func.max(QueueTrack.position)).where(QueueTrack.user_id == user_id)
        )).one()
