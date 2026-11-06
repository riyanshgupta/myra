"""HTTP routes for the user's queue and playback state."""
from fastapi import APIRouter, Depends, HTTPException, Response, status

from models.user import User
from routes.deps import get_current_user, get_playback_service
from schemas.req import PlaybackStateReq, QueueReorderReq, QueueTrackReq
import schemas.music as music_resp
from services.playback_service import PlaybackService

router = APIRouter(tags=["playback"])


@router.get("/queue", response_model=music_resp.QueueResponse)
async def get_queue(
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.queue(current_user.id)


@router.post("/queue/tracks", response_model=music_resp.QueueTrackAddedResponse, status_code=status.HTTP_201_CREATED)
async def enqueue_track(
    body: QueueTrackReq,
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.enqueue(current_user.id, body.jiosaavn_id)


@router.delete("/queue/tracks/{queue_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def remove_queued_track(
    queue_id: int,
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    await service.remove_queue_item(current_user.id, queue_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/queue", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def clear_queue(
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    await service.clear_queue(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/queue/reorder", response_model=music_resp.QueueResponse)
async def reorder_queue(
    body: QueueReorderReq,
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    try:
        return await service.reorder_queue(current_user.id, body.positions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/player/state", response_model=music_resp.PlayerStateResponse)
async def get_player_state(
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.get_state(current_user.id)


@router.patch("/player/state", response_model=music_resp.PlayerStateResponse)
async def update_player_state(
    body: PlaybackStateReq,
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.update_state(current_user.id, body.model_dump(exclude_unset=True))


@router.post("/player/next", response_model=music_resp.PlayerStateResponse)
async def next_track(
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.next(current_user.id)


@router.post("/player/previous", response_model=music_resp.PlayerStateResponse)
async def previous_track(
    current_user: User = Depends(get_current_user),
    service: PlaybackService = Depends(get_playback_service),
):
    return await service.previous(current_user.id)
