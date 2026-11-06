"""HTTP routes for the user's personal music library and listening history."""
from fastapi import APIRouter, Depends, Query, Response, status

from exceptions import ResourceNotFoundError
from models.user import User
from routes.deps import get_current_user, get_track_service
import schemas.music as music_resp
from services.track_service import TrackService

router = APIRouter(tags=["library"])


@router.get("/library/most-played", response_model=music_resp.TrackPageResponse)
async def most_played(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    service: TrackService = Depends(get_track_service),
):
    return await service.most_played(offset, limit)


@router.get("/history/recently-played", response_model=music_resp.HistoryPageResponse)
async def recently_played(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: TrackService = Depends(get_track_service),
):
    return await service.recently_played(current_user.id, offset, limit)


@router.post("/history/recently-played/{jiosaavn_id}", response_model=music_resp.RecordPlayResponse)
async def record_play(
    jiosaavn_id: str,
    current_user: User = Depends(get_current_user),
    service: TrackService = Depends(get_track_service),
):
    result = await service.record_play(current_user.id, jiosaavn_id)
    if result is None:
        raise ResourceNotFoundError("Track not found")
    return result


@router.get("/library/favorites", response_model=music_resp.FavoritePageResponse)
async def list_favorites(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: TrackService = Depends(get_track_service),
):
    return await service.favorites(current_user.id, offset, limit)


@router.put("/library/favorites/{jiosaavn_id}", response_model=music_resp.FavoriteAddedResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    jiosaavn_id: str,
    current_user: User = Depends(get_current_user),
    service: TrackService = Depends(get_track_service),
):
    result = await service.add_favorite(current_user.id, jiosaavn_id)
    if result is None:
        raise ResourceNotFoundError("Track not found")
    return result


@router.delete("/library/favorites/{jiosaavn_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    jiosaavn_id: str,
    current_user: User = Depends(get_current_user),
    service: TrackService = Depends(get_track_service),
):
    await service.remove_favorite(current_user.id, jiosaavn_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
