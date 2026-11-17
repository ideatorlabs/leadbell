from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import FakeWebhook
from leadbell import Lead, LeadForm, Notifier, RateLimiter
from leadbell.fastapi import lead_router


def make_app(
    webhook: FakeWebhook | None = None, limit: int = 100
) -> tuple[FastAPI, list[Lead], Notifier | None]:
    app = FastAPI()
    saved: list[Lead] = []
    bell = Notifier(webhook.url, env="production") if webhook else None
    form = LeadForm(consent_version="v1", limiter=RateLimiter(limit, 3600))
    app.include_router(lead_router(form, save=saved.append, notifier=bell))
    return app, saved, bell


def test_json_lead_is_saved_and_announced(webhook: FakeWebhook) -> None:
    app, saved, bell = make_app(webhook)
    client = TestClient(app)
    r = client.post(
        "/leads",
        json={
            "name": "Asha",
            "company": "Sample Store",
            "phone": "+1 555 0100",
            "consent": True,
            "source": {"utm_source": "expo"},
        },
    )
    assert r.status_code == 200 and r.json()["ref"].startswith("L-")
    assert saved[0].company == "Sample Store"
    assert bell is not None and bell.flush()
    [card] = webhook.wait_for(1)
    fields = {f["name"]: f["value"] for f in card["embeds"][0]["fields"]}
    assert fields["Ref"] == r.json()["ref"] and fields["Source"] == "utm_source=expo"


def test_form_post_errors_and_spam(webhook: FakeWebhook) -> None:
    app, saved, bell = make_app(webhook)
    client = TestClient(app)
    r = client.post("/leads", data={"name": "Asha", "company": "Sample Store", "phone": "+1 555 0100"})
    assert r.status_code == 422 and r.json()["field"] == "consent"
    r = client.post(
        "/leads", data={"name": "Bot", "company": "x", "phone": "1", "website": "http://x.example"}
    )
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post(
        "/leads", data={"name": "Asha", "company": "Sample Store", "phone": "+1 555 0100", "consent": "on"}
    )
    assert r.status_code == 200
    assert len(saved) == 1
    assert (
        client.post("/leads", content=b"[1, 2]", headers={"Content-Type": "application/json"}).status_code
        == 422
    )
    assert (
        client.post("/leads", content=b"{bad", headers={"Content-Type": "application/json"}).status_code
        == 422
    )


def test_rate_limit_uses_forwarded_address() -> None:
    app, _, _ = make_app(limit=1)
    client = TestClient(app)
    body = {"name": "A", "company": "B", "phone": "+1 555 0100", "consent": True}
    assert (
        client.post("/leads", json=body, headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}).status_code
        == 200
    )
    assert client.post("/leads", json=body, headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 429
    assert client.post("/leads", json=body, headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 200
    assert client.post("/leads", json=body).status_code == 200  # socket peer
    assert client.post("/leads", json=body).status_code == 429


def test_source_script_route() -> None:
    app, _, _ = make_app()
    r = TestClient(app).get("/leadbell/source.js")
    assert r.status_code == 200 and "leadbellSource" in r.text
    assert r.headers["content-type"].startswith("application/javascript")


def test_router_without_script_or_save() -> None:
    app = FastAPI()
    app.include_router(lead_router(LeadForm(consent_version="v1"), script_path=None, path="/api/demo"))
    client = TestClient(app)
    assert client.get("/leadbell/source.js").status_code == 404
    body = {"name": "A", "company": "B", "phone": "+1 555 0100", "consent": True}
    assert client.post("/api/demo", json=body).status_code == 200
