"""
api/jiosaavn.py
----------------
Reverse-proxy endpoint for the JioSaavn service.

    GET  /api/jiosaavn?type=search&query=Let%20me%20love%20you
    GET  /api/jiosaavn?type=autocomplete&query=Let%20me%20love%20you
    GET  /api/jiosaavn?type=song&query=<song_id>
    POST /api/jiosaavn  {"query": "<encrypted_media_url>"}

`audio` is POST-only: encrypted_media_url contains characters (e.g. `+`)
that get corrupted when passed unescaped in a query string, so it's sent
in the JSON body instead.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import msgspec

from service.jiosaavn import JioSaavnService, STREAM_HEADERS

class ErrorResponse(msgspec.Struct):
    error: str

class AudioRequest(msgspec.Struct):
    query: str

_GET_HANDLERS = {
    "search": lambda service, query: service.search(query),
    "autocomplete": lambda service, query: service.autocomplete(query),
    "song": lambda service, query: service.get_song(query),
}

class handler(BaseHTTPRequestHandler):

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        query_type = (params.get("type") or [None])[0]
        query = (params.get("query") or [None])[0]

        if query_type == "audio":
            self._send(400, ErrorResponse(
                error="type=audio requires POST with a JSON body: {\"query\": \"<encrypted_media_url>\"}"
            ))
            return

        handler_fn = _GET_HANDLERS.get(query_type)
        if handler_fn is None:
            self._send(400, ErrorResponse(
                error=f"Invalid or missing 'type'. Must be one of: {', '.join(sorted(_GET_HANDLERS))}"
            ))
            return

        if not query:
            self._send(400, ErrorResponse(error="Missing required 'query' parameter"))
            return

        try:
            data = handler_fn(JioSaavnService(), query)
        except Exception as error:
            self._send(502, ErrorResponse(error=f"Failed to fetch from JioSaavn: {error}"))
            return

        self._send(200, {"type": query_type, "query": query, "data": data})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(content_length) if content_length else b""

        try:
            payload = msgspec.json.decode(body, type=AudioRequest)
        except msgspec.DecodeError as error:
            self._send(400, ErrorResponse(error=f"Invalid request body: {error}"))
            return

        try:
            data = JioSaavnService().get_audio(payload.query)
        except Exception as error:
            self._send(502, ErrorResponse(error=f"Failed to fetch from JioSaavn: {error}"))
            return

        self._send(200, {
            "type": "audio",
            "query": payload.query,
            "data": data,
            "stream_headers": STREAM_HEADERS,
        })

    def _send(self, status: int, payload) -> None:
        body = msgspec.json.encode(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
