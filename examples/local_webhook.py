"""A tiny webhook that prints every card it receives. For trying Leadbell locally.

python examples/local_webhook.py          # listens on http://127.0.0.1:8766/
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

received: list[dict[str, Any]] = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        payload = json.loads(body or b"{}")
        received.append(payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


def serve(port: int = 8766) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    srv = serve()
    print(f"listening on http://127.0.0.1:{srv.server_port}/")
    threading.Event().wait()
