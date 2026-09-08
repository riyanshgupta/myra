"""
service/jiosaavn.py
--------------------
Singleton service wrapping the (undocumented) JioSaavn web API.

Uses curl_cffi's Session — which impersonates a real browser's TLS/JA3
fingerprint — instead of `requests`, since JioSaavn's edge blocks the
plain fingerprint that `requests`/urllib3 present.

The session is created once per warm serverless instance and reused
across invocations for connection pooling.
"""

from __future__ import annotations

from curl_cffi.requests import Session as SyncSession

JIOSAAVN_API_URL = "https://www.jiosaavn.com/api.php"
REQUEST_TIMEOUT = 10  # seconds

# The CDN behind `auth_url` (Akamai) 403s without this — it's not
# validated as part of the signed URL itself, just required on the
# actual media request.
STREAM_HEADERS = {"Referer": "https://www.jiosaavn.com/"}

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    ),
}


class JioSaavnService:
    _instance: "JioSaavnService | None" = None

    def __new__(cls) -> "JioSaavnService":
        if cls._instance is None:
            self = super().__new__(cls)
            self._session = SyncSession(
                headers=_HEADERS, impersonate="chrome", timeout=REQUEST_TIMEOUT
            )
            cls._instance = self
        return cls._instance

    def _get(self, payload: dict) -> dict:
        response = self._session.get(JIOSAAVN_API_URL, params=payload)
        return response.json()

    @staticmethod
    def _format_song_data(results: list[dict]) -> list[dict]:
        data = []
        for item in results:
            item = dict(item)
            info = dict(item.get("more_info") or {})
            data.append({
                "encrypted_media_url": info.get("encrypted_media_url"),
                "key": item.get("id"),
                "title": item.get("title"),
                "subtitle": item.get("subtitle"),
                "perma_url": item.get("perma_url"),
                "image": item.get("image"),
                "language": item.get("language"),
                "year": item.get("year"),
                "play_count": item.get("play_count"),
                "more_info": {
                    "album": info.get("album"),
                    "label": info.get("label"),
                    "album_url": info.get("album_url"),
                    "duration": info.get("duration"),
                },
            })
        return data

    def search(self, query: str) -> list[dict]:
        payload = {
            "type": "song",
            "p": 1,
            "api_version": 4,
            "n": 10,
            "q": query,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "search.getResults",
        }
        return self._format_song_data(self._get(payload).get("results", []))

    def autocomplete(self, query: str) -> list[dict]:
        payload = {
            "type": "song",
            "api_version": 4,
            "query": query,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "autocomplete.get",
        }
        return self._get(payload).get("songs", {}).get("data", [])

    def get_song(self, song_id: str) -> list[dict]:
        payload = {
            "type": "song",
            "includeMetaTags": 0,
            "api_version": 4,
            "token": song_id,
            "_format": "json",
            "_marker": 0,
            "ctx": "wap6dot0",
            "__call": "webapi.get",
        }
        return self._format_song_data(self._get(payload).get("songs", []))

    def get_audio(self, encrypted_media_url: str) -> dict:
        payload = {
            "__call": "song.generateAuthToken",
            "url": encrypted_media_url,
            "bitrate": 64,
            "api_version": 4,
            "_format": "json",
            "ctx": "wap6dot0",
            "_marker": 0,
        }
        return self._get(payload)
