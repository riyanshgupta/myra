from http.server import BaseHTTPRequestHandler
import msgspec

class ErrorResponse(msgspec.Struct):
    error: str

class handler(BaseHTTPRequestHandler):

    def do_POST(self) -> None:
        self._send(405, ErrorResponse(error="Method not allowed - use POST"))

    def do_GET(self) -> None:
        self._send(200, {
            "status": "ok", 
            "message": "Process worker is running"
        })

    def _send(self, status: int, payload: msgspec.Struct) -> None:
        body = msgspec.json.encode(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)