"""FastAPI wiring (``pip install "leadbell[fastapi]"``).

    from leadbell import LeadForm, Notifier
    from leadbell.fastapi import lead_router

    app.include_router(lead_router(LeadForm(consent_version="2026-01"), save=my_save, notifier=Notifier()))

Adds ``POST /leads`` (JSON or form) and ``GET /leadbell/source.js`` (the first-touch script).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .capture import Lead, LeadError, LeadForm
from .events import Notifier
from .static import source_js

__all__ = ["client_key", "lead_router"]


def client_key(request: Request) -> str:
    """The visitor's address: first ``X-Forwarded-For`` hop behind a proxy, else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def lead_router(
    form: LeadForm,
    *,
    save: Callable[[Lead], Any] | None = None,
    notifier: Notifier | None = None,
    path: str = "/leads",
    script_path: str | None = "/leadbell/source.js",
    key: Callable[[Request], str] = client_key,
) -> APIRouter:
    router = APIRouter()

    @router.post(path)
    async def create_lead(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        try:
            if content_type.startswith("application/json"):
                data = await request.json()
            else:
                data = dict(await request.form())
            if not isinstance(data, dict):
                raise LeadError("Please send the form fields.")
            lead = form.check(data, key(request))
        except LeadError as err:
            return JSONResponse({"detail": str(err), "field": err.field}, status_code=err.status)
        except ValueError:
            return JSONResponse({"detail": "Please send the form fields."}, status_code=422)
        if not lead.spam:
            if save is not None:
                save(lead)
            if notifier is not None:
                notifier.event("lead", lead.as_fields())
        return JSONResponse({"ok": True, "ref": lead.ref})

    if script_path:

        @router.get(script_path)
        def script() -> Response:
            return Response(
                source_js(),
                media_type="application/javascript",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    return router
