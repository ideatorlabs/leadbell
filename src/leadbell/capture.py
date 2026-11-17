"""Lead capture from a website form: validation, consent, honeypot, rate limit and first-touch source.

Framework-free. ``leadbell.fastapi.lead_router`` wires it into FastAPI; any other framework can call
``LeadForm.check()`` directly.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "DEFAULT_CONSENT",
    "Lead",
    "LeadError",
    "LeadForm",
    "RateLimiter",
    "SOURCE_KEYS",
    "any_phone",
    "clean_source",
    "india_mobile",
]

DEFAULT_CONSENT = (
    "I agree to be contacted about this request. This does not sign me up for marketing messages."
)
SOURCE_KEYS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "landing",
    "referrer",
)


class LeadError(ValueError):
    """A form problem to show the visitor. ``field`` names the input, when there is one."""

    def __init__(self, message: str, field: str | None = None, status: int = 422) -> None:
        super().__init__(message)
        self.field = field
        self.status = status


def any_phone(raw: str) -> str | None:
    """Digits only, 7–15 long (E.164 length), with an optional leading ``+``. Returns digits or None."""
    digits = re.sub(r"\D", "", raw or "")
    return digits if 7 <= len(digits) <= 15 else None


def india_mobile(raw: str) -> str | None:
    """Indian mobile numbers, returned as ``91`` + 10 digits. Accepts +91, 0 and spacing; else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return "91" + digits if re.fullmatch(r"[6-9]\d{9}", digits) else None


def clean_source(raw: object, max_len: int = 80) -> dict[str, str] | None:
    """Keep only the known first-touch keys, as short strings. Anything else is dropped."""
    if not isinstance(raw, Mapping):
        return None
    out = {k: str(raw[k]).strip()[:max_len] for k in SOURCE_KEYS if raw.get(k)}
    return out or None


class RateLimiter:
    """At most ``limit`` hits per ``window`` seconds per key, in this process."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            allowed = len(hits) < self.limit
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            return allowed

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


@dataclass
class Lead:
    ref: str
    name: str
    company: str
    phone: str
    email: str = ""
    city: str = ""
    message: str = ""
    source: dict[str, str] | None = None
    consent_text: str = DEFAULT_CONSENT
    consent_version: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    spam: bool = False

    def as_fields(self) -> dict[str, str]:
        """Fields for a Notifier card (``leadbell.source_text`` is applied to the source)."""
        from .events import source_text

        out = {"Ref": self.ref, "Name": self.name, "Company": self.company, "Phone": self.phone}
        if self.email:
            out["Email"] = self.email
        if self.city:
            out["City"] = self.city
        out["Message"] = self.message or "–"
        out["Source"] = source_text(self.source)
        return out


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadForm:
    """Checks one submission. ``check()`` returns a Lead or raises LeadError.

    A filled honeypot field returns a Lead with ``spam=True``: answer the visitor as if it worked, but
    don't store or announce it. The rate limit counts every submission, spam included.
    """

    def __init__(
        self,
        *,
        consent_version: str,
        consent_text: str = DEFAULT_CONSENT,
        phone: Callable[[str], str | None] = any_phone,
        require_phone: bool = True,
        require_email: bool = False,
        honeypot_field: str = "website",
        limiter: RateLimiter | None = None,
        ref_prefix: str = "L-",
    ) -> None:
        if not consent_version:
            raise ValueError("consent_version is required: store which wording the visitor agreed to")
        self.consent_version = consent_version
        self.consent_text = consent_text
        self.phone = phone
        self.require_phone, self.require_email = require_phone, require_email
        self.honeypot_field = honeypot_field
        self.limiter = limiter or RateLimiter(limit=5, window=3600)
        self.ref_prefix = ref_prefix

    def new_ref(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
        return self.ref_prefix + "".join(secrets.choice(alphabet) for _ in range(6))

    def check(self, data: Mapping[str, Any], client_key: str = "") -> Lead:
        if not self.limiter.hit(client_key or "?"):
            raise LeadError("Too many requests from here. Please try again later.", status=429)
        ref = self.new_ref()
        if str(data.get(self.honeypot_field) or "").strip():
            return Lead(ref=ref, name="", company="", phone="", spam=True)

        def text(key: str, limit: int) -> str:
            return " ".join(str(data.get(key) or "").split())[:limit]

        name, company = text("name", 80), text("company", 120)
        if not name:
            raise LeadError("Please add your name.", "name")
        if not company:
            raise LeadError("Please add your business name.", "company")
        raw_phone = text("phone", 30)
        phone = self.phone(raw_phone) if raw_phone else None
        if raw_phone and not phone:
            raise LeadError("Please check the phone number.", "phone")
        if self.require_phone and not phone:
            raise LeadError("Please add a phone number.", "phone")
        email = text("email", 120).lower()
        if email and not _EMAIL.match(email):
            raise LeadError("Please check the email address.", "email")
        if self.require_email and not email:
            raise LeadError("Please add an email address.", "email")
        if data.get("consent") is not True and str(data.get("consent")).lower() not in {
            "1",
            "true",
            "on",
            "yes",
        }:
            raise LeadError("Please tick the box so we can contact you.", "consent")
        return Lead(
            ref=ref,
            name=name,
            company=company,
            phone=phone or "",
            email=email,
            city=text("city", 80),
            message=text("message", 500),
            source=clean_source(data.get("source")),
            consent_text=self.consent_text,
            consent_version=self.consent_version,
        )
