"""Persistence operations for tracks, listening history, and favorites."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlmodel import select

from models.tracks import FavoriteTrack, Track
from models.user import UserMetadata
from repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    model = Track

    async def get_by_jiosaavn_id(self, jiosaavn_id: str) -> Track | None:
        result = await self.session.exec(select(Track).where(Track.jiosaavn_id == jiosaavn_id))
        return result.first()

    async def insert_track(self, track: Track) -> Track:
        self.session.add(track)
        await self.session.flush()
        return track

    async def apply_play(
        self, user_id: uuid.UUID, track: Track, metadata: UserMetadata | None, now: datetime
    ) -> UserMetadata:
        track.play_count += 1
        if metadata is None:
            metadata = UserMetadata(
                user_id=user_id, track_id=track.id, cnt=1, last_played=now, updated_at=now
            )
            self.session.add(metadata)
        else:
            metadata.cnt += 1
            metadata.last_played = now
            metadata.updated_at = now
        return metadata

    async def add_favorite(self, favorite: FavoriteTrack) -> FavoriteTrack:
        self.session.add(favorite)
        await self.session.commit()
        await self.session.refresh(favorite)
        return favorite

    async def remove_favorite(self, favorite: FavoriteTrack) -> None:
        await self.session.delete(favorite)
        await self.session.commit()

    async def list_most_played(self, offset: int, limit: int) -> tuple[list[Track], int]:
        rows = await self.session.exec(
            select(Track).order_by(Track.play_count.desc(), Track.id).offset(offset).limit(limit)
        )
        total = (await self.session.exec(select(func.count()).select_from(Track))).one()
        return list(rows.all()), total

    async def list_recently_played(
        self, user_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[tuple[Track, int, datetime]], int]:
        rows = await self.session.exec(
            select(Track, UserMetadata.cnt, UserMetadata.updated_at)
            .join(UserMetadata, UserMetadata.track_id == Track.id)
            .where(UserMetadata.user_id == user_id)
            .order_by(UserMetadata.updated_at.desc())
            .offset(offset).limit(limit)
        )
        total = (await self.session.exec(
            select(func.count()).select_from(UserMetadata).where(UserMetadata.user_id == user_id)
        )).one()
        return list(rows.all()), total

    async def get_user_metadata(self, user_id: uuid.UUID, track_id: int) -> UserMetadata | None:
        result = await self.session.exec(select(UserMetadata).where(
            UserMetadata.user_id == user_id, UserMetadata.track_id == track_id
        ))
        return result.first()

    async def list_favorites(
        self, user_id: uuid.UUID, offset: int, limit: int
    ) -> tuple[list[tuple[FavoriteTrack, Track]], int]:
        rows = await self.session.exec(
            select(FavoriteTrack, Track)
            .join(Track, FavoriteTrack.track_id == Track.id)
            .where(FavoriteTrack.user_id == user_id)
            .order_by(FavoriteTrack.created_at.desc()).offset(offset).limit(limit)
        )
        total = (await self.session.exec(
            select(func.count()).select_from(FavoriteTrack).where(FavoriteTrack.user_id == user_id)
        )).one()
        return list(rows.all()), total

    async def get_favorite(self, user_id: uuid.UUID, track_id: int) -> FavoriteTrack | None:
        result = await self.session.exec(select(FavoriteTrack).where(
            FavoriteTrack.user_id == user_id, FavoriteTrack.track_id == track_id
        ))
        return result.first()
