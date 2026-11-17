"""Shared fixtures: a webhook served by a local HTTP server, and a clean environment."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


@dataclass
class FakeWebhook:
    url: str
    received: list[dict[str, Any]] = field(default_factory=list)
    status: int = 204
    _cond: threading.Condition = field(default_factory=threading.Condition)

    def wait_for(self, n: int, timeout: float = 5.0) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while len(self.received) < n and time.monotonic() < deadline:
                self._cond.wait(deadline - time.monotonic())
            return list(self.received)


@pytest.fixture
def webhook() -> Iterator[FakeWebhook]:
    hook: FakeWebhook

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            with hook._cond:
                hook.received.append(json.loads(body))
                hook._cond.notify_all()
            self.send_response(hook.status)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hook = FakeWebhook(url=f"http://127.0.0.1:{server.server_port}/")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield hook
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LEADBELL_WEBHOOK_URL", "LEADBELL_ENV", "LEADBELL_SEND_LOCAL", "LEADBELL_FORMAT"):
        monkeypatch.delenv(key, raising=False)
