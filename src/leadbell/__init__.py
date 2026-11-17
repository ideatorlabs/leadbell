"""Leadbell: website lead capture and business-event alerts for small SaaS teams.

from leadbell import LeadForm, Notifier

bell = Notifier()                                         # LEADBELL_WEBHOOK_URL
form = LeadForm(consent_version="2026-01")
lead = form.check({"name": "Asha", "company": "Sample Store", "phone": "+1 555 0100",
                   "consent": True})
bell.event("lead", lead.as_fields())
"""

from __future__ import annotations

from .capture import (
    DEFAULT_CONSENT,
    SOURCE_KEYS,
    Lead,
    LeadError,
    LeadForm,
    RateLimiter,
    any_phone,
    clean_source,
    india_mobile,
)
from .events import DEFAULT_KINDS, Kind, Notifier, clean, source_text
from .static import source_js

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_CONSENT",
    "DEFAULT_KINDS",
    "SOURCE_KEYS",
    "Kind",
    "Lead",
    "LeadError",
    "LeadForm",
    "Notifier",
    "RateLimiter",
    "__version__",
    "any_phone",
    "clean",
    "clean_source",
    "india_mobile",
    "source_js",
    "source_text",
]
