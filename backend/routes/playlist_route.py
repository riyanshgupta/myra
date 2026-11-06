"""HTTP routes for playlist resources."""
from fastapi import APIRouter, Depends, Query, Response, status

from models.user import User
from routes.deps import get_current_user, get_playlist_service
from schemas.req import PlaylistCreateReq, PlaylistTrackReq, PlaylistUpdateReq
import schemas.music as music_resp
from services.playlist_service import PlaylistService

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.post("", response_model=music_resp.PlaylistResponse, status_code=status.HTTP_201_CREATED)
async def create_playlist(
    body: PlaylistCreateReq,
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    return await service.create(current_user.id, body.name, body.description)


@router.get("", response_model=music_resp.PlaylistPageResponse)
async def list_playlists(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=5, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    return await service.list(current_user.id, offset, limit)


@router.get("/{playlist_id}", response_model=music_resp.PlaylistDetailResponse)
async def get_playlist(
    playlist_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    return await service.get(current_user.id, playlist_id, offset, limit)


@router.post("/{playlist_id}/tracks", response_model=music_resp.PlaylistTrackAddedResponse, status_code=status.HTTP_201_CREATED)
async def add_playlist_track(
    playlist_id: int,
    body: PlaylistTrackReq,
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    return await service.add_track(current_user.id, playlist_id, body.jiosaavn_id)


@router.delete("/{playlist_id}/tracks/{track_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def remove_playlist_track(
    playlist_id: int,
    track_id: int,
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    await service.remove_track(current_user.id, playlist_id, track_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{playlist_id}", response_model=music_resp.PlaylistResponse)
async def update_playlist(
    playlist_id: int,
    body: PlaylistUpdateReq,
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    return await service.update(current_user.id, playlist_id, body.model_dump(exclude_unset=True))


@router.delete("/{playlist_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    service: PlaylistService = Depends(get_playlist_service),
):
    await service.delete(current_user.id, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
