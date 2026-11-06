"""Business rules for per-user queues, player state, and direct playback."""
from __future__ import annotations

import random
import uuid

from db.base_model import utcnow
from exceptions import ResourceNotFoundError
from models.tracks import PlaybackState, QueueTrack, Track
from repositories.playback_repo import PlaybackRepository
from services.track_service import TrackService


class PlaybackService:
    def __init__(self, repo: PlaybackRepository, tracks: TrackService, saavn_client) -> None:
        self.repo = repo
        self.tracks = tracks
        self.saavn_client = saavn_client

    async def select_track_and_replace_queue(
        self, user_id: uuid.UUID, song: dict, is_playing: bool
    ) -> Track:
        track = await self._get_or_create_song(song)
        state = await self.repo.get_state(user_id)
        if state is None:
            state = PlaybackState(user_id=user_id)
            self.repo.add(state)
            await self.repo.flush()

        changed_track = state.current_track_id != track.id
        began_playing = is_playing and (not state.is_playing or changed_track)
        if changed_track:
            for item in await self.repo.list_queue_items(user_id):
                await self.repo.stage_delete(item)
            state.current_track_id = track.id
            state.position_seconds = 0
        state.is_playing = is_playing
        if began_playing:
            await self._record_play(user_id, track)
        if changed_track:
            await self._append_artist_recommendations(user_id, track, song)
        await self.repo.commit()
        return track

    async def queue(self, user_id: uuid.UUID) -> dict:
        state = await self.repo.get_state(user_id)
        rows = await self.repo.get_queue(user_id)
        return {
            "items": [{
                "queue_id": item.id,
                "position": item.position,
                "is_current": bool(state and state.current_track_id == track.id),
                "track": self.tracks.track_payload(track),
            } for item, track in rows],
            "total": len(rows),
        }

    async def enqueue(self, user_id: uuid.UUID, jiosaavn_id: str) -> dict:
        track = await self.tracks.get_or_create(jiosaavn_id)
        if track is None:
            raise ResourceNotFoundError("Track not found")
        last_position = await self.repo.last_queue_position(user_id)
        item = QueueTrack(
            user_id=user_id, track_id=track.id,
            position=(last_position if last_position is not None else -1) + 1,
        )
        self.repo.add(item)
        state = await self.repo.get_state(user_id)
        if state is None:
            self.repo.add(PlaybackState(user_id=user_id, current_track_id=track.id))
        elif state.current_track_id is None:
            state.current_track_id = track.id
        await self.repo.commit()
        await self.repo.refresh(item)
        return {"queue_id": item.id, "position": item.position, "track": self.tracks.track_payload(track)}

    async def remove_queue_item(self, user_id: uuid.UUID, queue_id: int) -> None:
        item = await self.repo.get_queue_item(user_id, queue_id)
        if item:
            await self.repo.stage_delete(item)
            await self.repo.commit()

    async def clear_queue(self, user_id: uuid.UUID) -> None:
        for item in await self.repo.list_queue_items(user_id):
            await self.repo.stage_delete(item)
        state = await self.repo.get_state(user_id)
        if state:
            state.current_track_id = None
            state.is_playing = False
        await self.repo.commit()

    async def reorder_queue(self, user_id: uuid.UUID, ordered_ids: list[int]) -> dict:
        items = {item.id: item for item in await self.repo.list_queue_items(user_id)}
        if len(set(ordered_ids)) != len(ordered_ids) or set(items) != set(ordered_ids):
            raise ValueError("positions must contain every queue item exactly once")
        for index, item_id in enumerate(ordered_ids):
            items[item_id].position = 1_000_000 + index
        await self.repo.flush()
        for index, item_id in enumerate(ordered_ids):
            items[item_id].position = index
        await self.repo.commit()
        return await self.queue(user_id)

    async def get_state(self, user_id: uuid.UUID) -> dict:
        state = await self.repo.get_state(user_id)
        current = await self.repo.get_track(state.current_track_id) if state and state.current_track_id else None
        return {
            "current_track": self.tracks.track_payload(current) if current else None,
            "is_playing": state.is_playing if state else False,
            "shuffle": state.shuffle if state else False,
            "repeat_mode": state.repeat_mode if state else "off",
            "position_seconds": state.position_seconds if state else 0,
        }

    async def update_state(self, user_id: uuid.UUID, changes: dict) -> dict:
        state = await self.repo.get_state(user_id)
        selected_id = changes.pop("jiosaavn_id", None)
        if selected_id:
            song = await self.tracks.get_song(selected_id)
            if song is None:
                raise ResourceNotFoundError("Track not found")
            is_playing = changes.pop("is_playing", state.is_playing if state else False)
            await self.select_track_and_replace_queue(user_id, song, is_playing)
            state = await self.repo.get_state(user_id)
        elif state is None:
            state = PlaybackState(user_id=user_id)
            self.repo.add(state)
            await self.repo.flush()

        was_playing = state.is_playing
        for key, value in changes.items():
            setattr(state, key, value)
        if not selected_id and state.is_playing and not was_playing and state.current_track_id:
            track = await self.repo.get_track(state.current_track_id)
            if track:
                await self._record_play(user_id, track)
                if await self.repo.queue_count(user_id) == 0:
                    await self._append_artist_recommendations(user_id, track)
        await self.repo.commit()
        state_payload = await self.get_state(user_id)
        queue_payload = await self.queue(user_id)
        return {**state_payload, "queue": queue_payload["items"], "queue_total": queue_payload["total"]}

    async def next(self, user_id: uuid.UUID) -> dict:
        return await self._advance(user_id, 1)

    async def previous(self, user_id: uuid.UUID) -> dict:
        return await self._advance(user_id, -1)

    async def _advance(self, user_id: uuid.UUID, direction: int) -> dict:
        state = await self.repo.get_state(user_id)
        rows = await self.repo.get_queue(user_id)
        if not rows and direction < 0:
            raise ResourceNotFoundError("Queue is empty")
        indexes = [i for i, (_, track) in enumerate(rows) if state and track.id == state.current_track_id]
        current = indexes[0] if indexes else (-1 if direction > 0 else len(rows))
        if state and state.repeat_mode == "one" and indexes:
            target = current
        elif state and state.shuffle and direction > 0 and len(rows) > 1:
            target = random.choice([i for i in range(len(rows)) if i != current])
        else:
            target = current + direction

        if target < 0 or target >= len(rows):
            if state and state.repeat_mode == "all" and rows:
                target %= len(rows)
            elif direction > 0 and state and state.current_track_id:
                current_track = await self.repo.get_track(state.current_track_id)
                if current_track is None:
                    raise ResourceNotFoundError("Current track not found")
                await self._append_artist_recommendations(user_id, current_track)
                rows = await self.repo.get_queue(user_id)
                indexes = [i for i, (_, track) in enumerate(rows) if track.id == current_track.id]
                target = (indexes[0] if indexes else -1) + 1
                if target >= len(rows):
                    raise ResourceNotFoundError("No more queued or recommended tracks")
            else:
                raise ResourceNotFoundError("No track in that direction")

        if state is None:
            state = PlaybackState(user_id=user_id)
            self.repo.add(state)
        selected_track = rows[target][1]
        state.current_track_id = selected_track.id
        state.is_playing = True
        state.position_seconds = 0
        await self._record_play(user_id, selected_track)
        await self.repo.commit()
        return await self.get_state(user_id)

    async def _get_or_create_song(self, song: dict) -> Track:
        return await self.tracks.get_or_create_from_song(song)

    async def _record_play(self, user_id: uuid.UUID, track: Track) -> None:
        metadata = await self.tracks.repo.get_user_metadata(user_id, track.id)
        await self.tracks.repo.apply_play(user_id, track, metadata, utcnow())

    async def _append_artist_recommendations(
        self, user_id: uuid.UUID, current_track: Track, song: dict | None = None
    ) -> int:
        if song is None:
            song = await self.tracks.get_song(current_track.jiosaavn_id)
        if not song:
            return 0
        artist_ids = [str(a.get("id")) for a in song.get("artists", []) if a.get("id")]
        try:
            suggestions = await self.saavn_client.get_artist_other_top_songs(
                artist_ids, current_track.jiosaavn_id, song.get("language")
            )
        except Exception:
            return 0
        rows = await self.repo.get_queue(user_id)
        existing = {track.jiosaavn_id for _, track in rows} | {current_track.jiosaavn_id}
        last_position = await self.repo.last_queue_position(user_id)
        position = last_position if last_position is not None else -1
        added = 0
        for suggestion in suggestions:
            song_id = suggestion.get("jiosaavn_id")
            if not song_id or song_id in existing:
                continue
            track = await self._get_or_create_song(suggestion)
            position += 1
            self.repo.add(QueueTrack(user_id=user_id, track_id=track.id, position=position))
            existing.add(song_id)
            added += 1
        if added:
            await self.repo.flush()
        return added
