"""Async adapter for the deployed JioSaavn reverse proxy.

It deliberately mirrors JioSaavnClient's public methods, allowing services and
tools to depend on either provider through constructor injection.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin

from curl_cffi.requests import AsyncSession

from clients.base_client import BaseClient

STREAM_HEADERS = {"Referer": "https://www.jiosaavn.com/"}
REQUEST_TIMEOUT = 15


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ReverseProxyClient(BaseClient):
    def __init__(self, session: AsyncSession, base_url: str | None = None) -> None:
        super().__init__(session)
        self.base_url = (base_url or os.getenv("JIOSAAVN_PROXY_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError("JIOSAAVN_PROXY_URL must be configured")
        self.endpoint = urljoin(self.base_url + "/", "api/jiosaavn_route")

    async def _request(self, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> Any:
        response = await self.session.post(self.endpoint, json=json, timeout=REQUEST_TIMEOUT) if json is not None else await self.session.get(self.endpoint, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if "data" not in payload:
            raise ValueError("Reverse proxy returned an invalid response")
        return payload["data"]

    @staticmethod
    def _format_song_data(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted = []
        for item in results:
            # Proxy song endpoints already return the backend schema; trending
            # still returns the provider's raw playlist records.
            if "jiosaavn_id" in item:
                formatted.append(dict(item))
                continue
            info = dict(item.get("more_info") or {})
            formatted.append({
                "encrypted_media_url": info.get("encrypted_media_url"), "jiosaavn_id": item.get("id"),
                "title": item.get("title"), "subtitle": item.get("subtitle"), "cover_image": item.get("image"),
                "language": item.get("language"), "year": _optional_int(item.get("year")),
                "play_count": _optional_int(item.get("play_count")),
                "album": info.get("album"), "label": info.get("label"),
                "duration_seconds": _optional_int(info.get("duration")),
                "artists": [{"name": a.get("name"), "id": a.get("id")} for a in info.get("artistMap", {}).get("primary_artists", [])],
            })
        return formatted

    async def search(self, query: str, limit: int = 10, page: int = 1) -> dict[str, list[dict[str, Any]]]:
        return await self._request(params={"type": "search", "query": query, "limit": limit, "page": page})

    async def autocomplete(self, query: str) -> dict[str, list[dict[str, Any]]]:
        return await self._request(params={"type": "autocomplete", "query": query})

    async def _get_artist(self, artist_id: str, page: int = 0) -> dict[str, Any]:
        return await self._request(params={"type": "artist", "query": artist_id, "page": page})

    async def get_top_tracks_by_artist(self, query: str, page: int = 0) -> list[dict[str, Any]]:
        artists = (await self.autocomplete(query)).get("artists", [])
        if not artists or not artists[0].get("artist_id"):
            return []
        return await self.get_top_tracks_by_artist_id(artists[0]["artist_id"], page)

    async def get_top_tracks_by_artist_id(self, artist_id: str, page: int = 0) -> list[dict[str, Any]]:
        return await self._request(params={"type": "artist_top_tracks", "query": artist_id, "page": page})

    async def get_song(self, jiosaavn_id: str) -> list[dict[str, Any]]:
        return await self._request(params={"type": "song", "query": jiosaavn_id})

    async def get_audio(self, encrypted_media_url: str) -> dict[str, Any]:
        return await self._request(json={"query": encrypted_media_url})

    async def get_artist_other_top_songs(self, artist_ids: list[str], song_id: str, language: str | None = None) -> list[dict[str, Any]]:
        if not artist_ids:
            return []
        params: dict[str, Any] = {"type": "artist_recommendations", "query": song_id, "artist_ids": ",".join(artist_ids)}
        if language:
            params["language"] = language
        return await self._request(params=params)

    async def get_html_page(self, url: str) -> str:
        return await self._request(params={"type": "homepage", "query": url})

    async def get_top_trending_hindi(self) -> list[dict[str, Any]]:
        return await self._request(params={"type": "trending", "query": "hindi"})
