"""Synchronous JioSaavn provider used by the Vercel HTTP adapter."""
from __future__ import annotations

import re
from curl_cffi.requests import Session as SyncSession

JIOSAAVN_API_URL = "https://www.jiosaavn.com/api.php"
REQUEST_TIMEOUT = 10
STREAM_HEADERS = {"Referer": "https://www.jiosaavn.com/"}
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": ("Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"),
}


def _optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class JioSaavnService:
    """Provider operations mirrored by backend.clients.saavn_client."""
    _instance: "JioSaavnService | None" = None

    def __new__(cls) -> "JioSaavnService":
        if cls._instance is None:
            self = super().__new__(cls)
            self._session = SyncSession(headers=_HEADERS, impersonate="chrome", timeout=REQUEST_TIMEOUT)
            cls._instance = self
        return cls._instance

    def _get(self, payload: dict) -> dict:
        response = self._session.get(JIOSAAVN_API_URL, params=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _format_song_data(results: list[dict]) -> list[dict]:
        data = []
        for item in results:
            info = dict(item.get("more_info") or {})
            data.append({
                "encrypted_media_url": info.get("encrypted_media_url"),
                "jiosaavn_id": item.get("id") or item.get("key"),
                "title": item.get("title"), "subtitle": item.get("subtitle"),
                "cover_image": item.get("image") or item.get("cover_image"),
                "language": item.get("language"), "year": _optional_int(item.get("year")),
                "play_count": _optional_int(item.get("play_count")),
                "album": info.get("album") or (item.get("more_info") or {}).get("album"),
                "label": info.get("label"),
                "duration_seconds": _optional_int(info.get("duration")),
                "artists": [{"name": a.get("name"), "id": a.get("id")}
                            for a in info.get("artistMap", {}).get("primary_artists", [])],
            })
        return data

    @staticmethod
    def _payload(call: str, **kwargs) -> dict:
        return {"__call": call, "api_version": 4, "_format": "json", "_marker": 0,
                "ctx": "wap6dot0", **kwargs}

    def search(self, query: str, limit: int = 10, page: int = 1) -> dict:
        base = self._payload("search.getResults", type="song", p=page, n=limit, q=query)
        songs = self._format_song_data(self._get(base).get("results", []))
        artist_data = self._get({**base, "type": "artist"}).get("results", [])
        artists = [{"artist_id": a.get("id"), "title": a.get("name") or a.get("title"),
                    "cover_image": a.get("image"), "url": a.get("perma_url")} for a in artist_data]
        return {"songs": songs, "artists": artists}

    def autocomplete(self, query: str) -> dict:
        data = self._get(self._payload("autocomplete.get", query=query))
        return {
            "songs": [{"jiosaavn_id": (s.get("url") or "").rstrip("/").split("/")[-1],
                       "title": s.get("title"), "cover_image": s.get("image"), "album": s.get("album")}
                      for s in data.get("songs", {}).get("data", [])],
            "artists": [{"artist_id": (a.get("url") or "").rstrip("/").split("/")[-1],
                         "title": a.get("title"), "cover_image": a.get("image")}
                        for a in data.get("artists", {}).get("data", [])],
        }

    def _get_artist(self, artist_id: str, page: int = 0) -> dict:
        return self._get(self._payload("webapi.get", type="artist", includeMetaTags=0,
            token=artist_id, p=page, n_song=50, n_album=50))

    def get_top_tracks_by_artist(self, query: str, page: int = 0) -> list[dict]:
        artists = self.autocomplete(query).get("artists", [])
        return self.get_top_tracks_by_artist_id(artists[0]["artist_id"], page) if artists and artists[0].get("artist_id") else []

    def get_top_tracks_by_artist_id(self, artist_id: str, page: int = 0) -> list[dict]:
        return self._format_song_data(self._get_artist(artist_id, page).get("topSongs", []))

    def get_song(self, jiosaavn_id: str) -> list[dict]:
        data = self._get(self._payload("song.getDetails", pids=jiosaavn_id))
        return self._format_song_data(data.get("songs", []))

    def get_audio(self, encrypted_media_url: str) -> dict:
        return self._get(self._payload("song.generateAuthToken", url=encrypted_media_url, bitrate=64))

    def get_artist_other_top_songs(self, artist_ids: list[str], song_id: str, language: str | None = None) -> list[dict]:
        if not artist_ids:
            return []
        args = {"ctx": "web6dot0", "artist_ids": ",".join(artist_ids), "song_id": song_id}
        if language:
            args["language"] = language
        data = self._get(self._payload("search.artistOtherTopSongs", **args))
        songs = data if isinstance(data, list) else (data.get("songs") or data.get("results") or data.get("list") or [])
        return self._format_song_data(songs)

    def get_html_page(self, url: str) -> str:
        response = self._session.get(url, headers={**_HEADERS, **STREAM_HEADERS}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text

    def get_top_trending_hindi(self) -> list[dict]:
        html = self.get_html_page("https://www.jiosaavn.com/")
        match = re.search(r'href="(/featured/hindi-india-superhits-top-50/[^"]+)"', html)
        if not match:
            raise RuntimeError("Trending playlist link not found on JioSaavn homepage")
        data = self._get(self._payload("webapi.get", type="playlist", token=match.group(1).split("/")[-1],
            p=0, n=50, includeMetaTags=0))
        return data.get("list") or []
