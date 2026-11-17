"""Business-event cards: one tidy message per new sign-up, lead, first real use or payment.

    from leadbell import Notifier

    bell = Notifier()                                     # LEADBELL_WEBHOOK_URL, LEADBELL_ENV
    bell.event("signup", {"Business": "Sample Store", "City": "Pune", "Source": "utm_source=newsletter"})

Sends from a background thread; never raises into your code and never blocks a request. Off outside the
environments you list (default: production, staging, demo) unless ``LEADBELL_SEND_LOCAL=1``.
Values typed by visitors are cleaned: chat markdown, mentions and links can't format or ping your channel.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["DEFAULT_KINDS", "Kind", "Notifier", "clean", "source_text"]

log = logging.getLogger("leadbell")


@dataclass(frozen=True)
class Kind:
    title: str
    colour: int


DEFAULT_KINDS: dict[str, Kind] = {
    "signup": Kind("New sign-up", 0x1E4D3B),
    "lead": Kind("New demo request", 0xE5782C),
    "activated": Kind("First real use", 0x2F6B4A),
    "paid": Kind("Payment recorded", 0x1E4D3B),
    "churned": Kind("Customer left", 0xB2453A),
}

_MARKDOWN = re.compile(r"[*`~|>\[\]]")
_LINK = re.compile(r"https?://\S+", re.I)
_MENTION = re.compile(r"[@#<]")


def clean(value: object, limit: int = 300) -> str:
    """Make visitor-typed text safe for a chat card: no markdown, links or mentions; one line; capped."""
    text = _MARKDOWN.sub("", str(value if value is not None else ""))
    text = _LINK.sub("(link)", text)
    text = _MENTION.sub("", text)
    text = " ".join(text.split())
    return text[:limit]


def source_text(source: Mapping[str, Any] | None) -> str:
    """One line on where a visitor came from, e.g. ``utm_source=newsletter, from example.com``."""
    if not source:
        return "direct"
    keys = ("utm_source", "utm_medium", "utm_campaign", "ref")
    parts = [f"{k}={clean(source[k], 60)}" for k in keys if source.get(k)]
    if source.get("referrer"):
        parts.append(f"from {clean(source['referrer'], 60)}")
    return ", ".join(parts) or "direct"


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class _Card:
    kind: str
    title: str
    colour: int
    fields: list[tuple[str, str]] = field(default_factory=list)


def _discord(card: _Card) -> dict[str, Any]:
    return {
        "embeds": [
            {
                "title": card.title,
                "color": card.colour,
                "fields": [{"name": k, "value": v or "–", "inline": len(v) < 30} for k, v in card.fields],
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def _slack(card: _Card) -> dict[str, Any]:
    lines = "\n".join(f"*{k}:* {v or '–'}" for k, v in card.fields)
    return {
        "text": card.title,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": card.title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": lines}},
        ],
    }


def _json(card: _Card) -> dict[str, Any]:
    return {"kind": card.kind, "title": card.title, "fields": dict(card.fields)}


FORMATS: dict[str, Callable[[_Card], dict[str, Any]]] = {"discord": _discord, "slack": _slack, "json": _json}


class Notifier:
    """Posts business-event cards to one webhook (Discord, Slack or plain JSON)."""

    def __init__(
        self,
        webhook_url: str | None = None,
        *,
        env: str | None = None,
        send_envs: Iterable[str] = ("production", "staging", "demo"),
        send_local: bool | None = None,
        format: str | None = None,
        kinds: Mapping[str, Kind] | None = None,
        timeout: float = 5.0,
        queue_size: int = 200,
        post: Callable[[str, bytes, float], None] | None = None,
    ) -> None:
        self.webhook_url = webhook_url or os.environ.get("LEADBELL_WEBHOOK_URL") or None
        self.env = env or os.environ.get("LEADBELL_ENV") or "local"
        self.send_envs = set(send_envs)
        self.send_local = _truthy(os.environ.get("LEADBELL_SEND_LOCAL")) if send_local is None else send_local
        fmt = (format or os.environ.get("LEADBELL_FORMAT") or "discord").lower()
        if fmt not in FORMATS:
            raise ValueError(f"format must be one of {sorted(FORMATS)}")
        self.format = fmt
        self.kinds = {**DEFAULT_KINDS, **(kinds or {})}
        self.timeout = timeout
        self._post = post or _http_post
        self._queue: queue.Queue[tuple[str, bytes] | None] = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.sent = 0
        self.dropped = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url) and (self.env in self.send_envs or self.send_local)

    def card(self, kind: str, fields: Mapping[str, object], title: str | None = None) -> _Card:
        k = self.kinds.get(kind, Kind(kind.replace("_", " ").capitalize(), 0x5A6270))
        text = title or k.title
        if self.env not in ("production", "prod"):
            text = f"{text} ({self.env})"
        return _Card(kind, clean(text, 120), k.colour, [(clean(n, 60), clean(v)) for n, v in fields.items()])

    def payload(self, kind: str, fields: Mapping[str, object], title: str | None = None) -> dict[str, Any]:
        return FORMATS[self.format](self.card(kind, fields, title))

    def event(self, kind: str, fields: Mapping[str, object], *, title: str | None = None) -> bool:
        """Queue one card. Returns False when it was not queued (disabled, or the queue is full)."""
        try:
            if not self.enabled:
                return False
            body = json.dumps(self.payload(kind, fields, title)).encode()
            self._ensure_thread()
            self._queue.put_nowait((self.webhook_url or "", body))
            return True
        except queue.Full:
            self.dropped += 1
            log.warning("leadbell queue full; card dropped")
            return False
        except Exception as exc:  # noqa: BLE001 - never raise into the host application
            log.warning("leadbell could not queue a card: %s", exc)
            return False

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until queued cards are sent (or the timeout passes). Returns True when the queue is empty."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="leadbell")
                self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                url, body = item
                self._post(url, body, self.timeout)
                self.sent += 1
            except Exception as exc:  # noqa: BLE001 - a lost card must never break the app
                self.failed += 1
                log.warning("leadbell webhook failed: %s", exc)
            finally:
                self._queue.task_done()


def _http_post(url: str, body: bytes, timeout: float) -> None:
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "User-Agent": "leadbell"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured webhook URL
        resp.read()
