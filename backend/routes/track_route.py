"""HTTP routes for music-provider catalog and track metadata."""
from fastapi import APIRouter, Depends, Query

from exceptions import ResourceNotFoundError
from routes.deps import get_track_service
import schemas.resp as resp
import schemas.music as music_resp
from services.track_service import TrackService

router = APIRouter(tags=["music"])


@router.get("/search/autocomplete", response_model=resp.TrackAutoCompleteResp)
async def autocomplete(q: str, service: TrackService = Depends(get_track_service)):
    return await service.autocomplete(q)


@router.get("/search", response_model=music_resp.SearchResponse)
async def search(
    q: str = Query(min_length=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    service: TrackService = Depends(get_track_service),
):
    return await service.search(q, page, limit)


@router.get("/music/trending", response_model=music_resp.SongPageResponse)
async def trending_hindi(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    service: TrackService = Depends(get_track_service),
):
    return await service.trending(offset, limit)


@router.get("/music/recommended", response_model=music_resp.SongPageResponse)
async def recommended_tracks(
    track_id: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    service: TrackService = Depends(get_track_service),
):
    result = await service.recommended(track_id, limit)
    if result is None:
        raise ResourceNotFoundError("Track not found")
    return result


@router.get("/track/{track_id}", response_model=music_resp.SongResponse)
async def get_track(track_id: str, service: TrackService = Depends(get_track_service)):
    song = await service.get_song(track_id)
    if song is None:
        raise ResourceNotFoundError("Track not found")
    return song


@router.get("/artists/{artist_id}/top-tracks", response_model=music_resp.ArtistTrackPageResponse)
async def artist_top_tracks(
    artist_id: str,
    page: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    service: TrackService = Depends(get_track_service),
):
    return await service.artist_top_tracks(artist_id, page, limit)


@router.get("/track/stream/{encrypted_media_url:path}", response_model=music_resp.StreamResponse)
async def get_track_stream(
    encrypted_media_url: str, service: TrackService = Depends(get_track_service)
):
    result = await service.stream_url(encrypted_media_url)
    if result is None:
        raise ResourceNotFoundError("Stream URL unavailable")
    return result
