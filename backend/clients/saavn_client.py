from __future__ import annotations

import re
from typing import Any

from curl_cffi.requests import AsyncSession

from clients.base_client import BaseClient
from config import settings
from core.session import base_session

logger = settings.get_logger("saavn_client")

JIOSAAVN_API_URL = "https://www.jiosaavn.com/api.php"
REQUEST_TIMEOUT = 10  # seconds

# Required by the CDN for media requests using the generated auth URL.
STREAM_HEADERS = {"Referer": "https://www.jiosaavn.com/"}

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 "
        "Mobile Safari/537.36"
    ),
}


class JioSaavnClient(BaseClient):
    """Client for JioSaavn APIs.

    The HTTP session is inje4cted by the application and is owned by the
    session/lifespan manager, not by this client.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def _get(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.session.get(
            JIOSAAVN_API_URL,
            params=payload,
            headers=_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _format_song_data(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = []
        for item in results:
            info = dict(item.get("more_info") or {})
            data.append(
                {
                    "encrypted_media_url": info.get("encrypted_media_url"),
                    "jiosaavn_id": item.get("id"),
                    "title": item.get("title"),
                    "subtitle": item.get("subtitle"),
                    "cover_image": item.get("image"),
                    "language": item.get("language"),
                    "year": item.get("year"),
                    "play_count": item.get("play_count"),
                    "album": info.get("album"),
                    "label": info.get("label"),
                    "duration_seconds": info.get("duration"),
                    "artists": [
                        {
                            "name": artist.get("name"),
                            "id": artist.get("id") # will be used to get top tracks by artist
                        }
                        for artist in info.get("artistMap", {}).get("primary_artists", [])
                    ]
                }
            )
        return data


    async def search(self, query: str, limit: int = 10, page: int = 1) -> dict[str, list[dict[str, Any]]]:
        payload = {
            "type": "song",
            "p": page,
            "api_version": 4,
            "n": limit,
            "q": query,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "search.getResults",
        }
        data = await self._get(payload)
        songs = self._format_song_data(data.get("results", []))

        artist_payload = {**payload, "type": "artist", "__call": "search.getResults"}
        artist_data = await self._get(artist_payload)
        artists = [
            {
                "artist_id": item.get("id"),
                "title": item.get("name") or item.get("title"),
                "cover_image": item.get("image"),
                "url": item.get("perma_url"),
            }
            for item in artist_data.get("results", [])
        ]
        return {"songs": songs, "artists": artists}

    async def autocomplete(self, query: str) -> dict[str, list[dict[str, Any]]]:
        """Return autocomplete matches for songs and artists."""
        payload = {
            "query": query,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "autocomplete.get",
        }
        data = await self._get(payload)
        return {
            "songs": [{
                "jiosaavn_id": (song.get("url") or "").rstrip("/").split("/")[-1],
                "title": song.get("title"),
                "cover_image": song.get("image"),
                "album": song.get("album")
            } for song in data.get("songs", {}).get("data", [])],
            
            "artists": [{
                "artist_id": (artist.get("url") or "").rstrip("/").split("/")[-1],
                "title": artist.get("title"),
                "cover_image": artist.get("image")
            } for artist in data.get("artists", {}).get("data", [])]
        }

    async def _get_artist(self, artist_id: str, page: int = 0) -> dict[str, Any]:
        payload = {
            "type": "artist",
            "includeMetaTags": 0,
            "api_version": 4,
            "token": artist_id,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "p": page,
            "n_song": 50,
            "n_album": 50,
            "__call": "webapi.get",
        }
        return await self._get(payload)

    async def get_artist_other_top_songs(
        self, artist_ids: list[str], song_id: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        """Return recommendations related to the current song and its artists."""
        if not artist_ids:
            return []
        payload = {
            "__call": "search.artistOtherTopSongs",
            "api_version": 4,
            "_format": "json",
            "_marker": 0,
            "ctx": "web6dot0",
            "artist_ids": ",".join(artist_ids),
            "song_id": song_id,
        }
        if language:
            payload["language"] = language
        data = await self._get(payload)
        if isinstance(data, list):
            return self._format_song_data(data)
        songs = data.get("songs") or data.get("results") or data.get("list") or []
        return self._format_song_data(songs)

    async def get_top_tracks_by_artist(
        self, query: str, page: int = 0
    ) -> list[dict[str, Any]]:
        autocomplete_result = await self.autocomplete(query)
        artists = autocomplete_result.get("artists", [])
        if not artists:
            logger.warning(f"No artists found for query: {query}")
            return []

        artist_id = artists[0].get("artist_id", "")
        if not artist_id:
            logger.warning(f"No artist ID found for query: {query}")
            return []

        artist_data = await self._get_artist(artist_id, page)
        songs = artist_data.get("topSongs", [])
        return self._format_song_data(songs)

    async def get_top_tracks_by_artist_id(
        self, artist_id: str, page: int = 0
    ) -> list[dict[str, Any]]:
        artist_data = await self._get_artist(artist_id, page)
        return self._format_song_data(artist_data.get("topSongs", []))

    async def get_song(self, jiosaavn_id: str) -> list[dict[str, Any]]:
        payload = {
            "type": "song",
            "includeMetaTags": 0,
            "api_version": 4,
            "token": jiosaavn_id,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "webapi.get",
        }
        data = await self._get(payload)
        return self._format_song_data(data.get("songs", []))

    async def get_audio(self, encrypted_media_url: str) -> dict[str, Any]:
        payload = {
            "__call": "song.generateAuthToken",
            "url": encrypted_media_url,
            "bitrate": 64,
            "api_version": 4,
            "_format": "json",
            "ctx": "wap6dot0",
            "_marker": 0,
        }
        return await self._get(payload)

    async def get_html_page(self, url: str) -> str:
        response = await self.session.get(
            url,
            headers={**_HEADERS, **STREAM_HEADERS},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text

    async def get_top_trending_hindi(self) -> list[dict[str, Any]]:
        html_txt = await self.get_html_page("https://www.jiosaavn.com/")
        match = re.search(
            r'href="(/featured/hindi-india-superhits-top-50/[^"]+)"', html_txt
        )
        if match is None:
            raise RuntimeError("Trending playlist link not found on JioSaavn homepage")

        payload = {
            "__call": "webapi.get",
            "token": match.group(1).split("/")[-1],
            "type": "playlist",
            "p": 0,
            "n": 50,
            "includeMetaTags": 0,
            "ctx": "wap6dot0",
            "api_version": 4,
            "_format": "json",
            "_marker": 0,
        }
        data = await self._get(payload)
        return data.get("list") or []

saavn_client = JioSaavnClient(session=base_session.get_session())
