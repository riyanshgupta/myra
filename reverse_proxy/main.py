"""
main.py
-------
Local dev server that mimics Vercel's Python runtime routing, without
needing the `vercel` CLI: every `api/<name>.py` module exporting a
`handler` class (a `BaseHTTPRequestHandler` subclass, same convention
Vercel expects) gets served at `/api/<name>`.

Run (from this directory, using the venv already set up here):
    venv/bin/python main.py       # serves on :3000
    PORT=8080 venv/bin/python main.py

Then:
    curl "http://localhost:3000/api/jiosaavn_route?type=search&query=Let%20me%20love%20you"
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_DIR = Path(__file__).parent / "api"


def load_routes() -> dict[str, type[BaseHTTPRequestHandler]]:
    routes: dict[str, type[BaseHTTPRequestHandler]] = {}
    for module_info in pkgutil.iter_modules([str(API_DIR)]):
        try:
            module = importlib.import_module(f"api.{module_info.name}")
        except Exception as error:
            print(f"  ! skipping api/{module_info.name}.py: {error}")
            continue
        if hasattr(module, "handler"):
            routes[f"/api/{module_info.name}"] = module.handler
    return routes


ROUTES = load_routes()


class DevRequestHandler(BaseHTTPRequestHandler):
    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        target = ROUTES.get(path)
        if target is None:
            body = b'{"error": "Not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Swap in the target handler's class so its own methods (e.g. `_send`)
        # resolve on self, since target.do_GET(self) alone only sees methods
        # defined on DevRequestHandler.
        original_class = self.__class__
        self.__class__ = target
        try:
            getattr(self, method)()
        finally:
            self.__class__ = original_class

    def do_GET(self) -> None:
        self._dispatch("do_GET")

    def do_POST(self) -> None:
        self._dispatch("do_POST")


def main() -> None:
    port = int(os.environ.get("PORT", 3000))
    server = ThreadingHTTPServer(("0.0.0.0", port), DevRequestHandler)

    print(f"Serving api/ routes on http://localhost:{port}")
    for route in sorted(ROUTES):
        print(f"  {route}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
