"""The example site and every Python block in the README, run for real against a local webhook."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from conftest import FakeWebhook

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```\n", (ROOT / "README.md").read_text(encoding="utf-8"), flags=re.S)


def block_with(text: str) -> str:
    [block] = [b for b in blocks() if text in b]
    return block


def test_every_readme_block_is_covered() -> None:
    markers = ['"Owner": "Asha"', "lead_router(form", "phone=india_mobile"]
    assert len(blocks()) == len(markers)
    for m in markers:
        block_with(m)


def test_readme_events_block(webhook: FakeWebhook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADBELL_WEBHOOK_URL", webhook.url)
    monkeypatch.setenv("LEADBELL_ENV", "production")
    exec(compile(block_with('"Owner": "Asha"'), "README.md", "exec"), {})
    titles = [c["embeds"][0]["title"] for c in webhook.wait_for(3)]
    assert titles == ["New sign-up", "First real use", "Plan upgraded"]
    source = {f["name"]: f["value"] for f in webhook.received[0]["embeds"][0]["fields"]}["Source"]
    assert source == "utm_source=newsletter, from example.com"


def test_readme_fastapi_block(webhook: FakeWebhook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADBELL_WEBHOOK_URL", webhook.url)
    monkeypatch.setenv("LEADBELL_ENV", "production")
    ns: dict[str, object] = {}
    exec(compile(block_with("lead_router(form"), "README.md", "exec"), ns)
    client = TestClient(ns["app"])  # type: ignore[arg-type]
    r = client.post(
        "/leads", json={"name": "Sam", "company": "Sample Store", "phone": "+1 555 0101", "consent": True}
    )
    assert r.status_code == 200 and len(ns["leads"]) == 1  # type: ignore[arg-type]
    assert webhook.wait_for(1)[0]["embeds"][0]["title"] == "New demo request"


def test_readme_plain_block(capsys: pytest.CaptureFixture[str]) -> None:
    exec(compile(block_with("phone=india_mobile"), "README.md", "exec"), {})
    assert capsys.readouterr().out.strip() == "919999900001 {'utm_source': 'expo'}"


def test_example_site(webhook: FakeWebhook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADBELL_WEBHOOK_URL", webhook.url)
    monkeypatch.setenv("LEADBELL_SEND_LOCAL", "1")
    site = load(ROOT / "examples" / "site.py")
    client = TestClient(site.app)
    page = client.get("/")
    assert page.status_code == 200 and "/leadbell/source.js" in page.text and 'name="website"' in page.text
    assert "leadbellSource" in client.get("/leadbell/source.js").text
    r = client.post(
        "/leads",
        json={
            "name": "Asha",
            "company": "Sample Store",
            "phone": "+1 555 0102",
            "consent": True,
            "source": {"utm_source": "newsletter"},
        },
    )
    assert r.status_code == 200 and site.LEADS[0].source == {"utm_source": "newsletter"}
    card = webhook.wait_for(1)[0]["embeds"][0]
    assert card["title"] == "New demo request (local)"


def test_example_local_webhook_prints(capsys: pytest.CaptureFixture[str]) -> None:
    import json
    import urllib.request

    hook = load(ROOT / "examples" / "local_webhook.py")
    server = hook.serve(port=0)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/",
            data=json.dumps({"a": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5).read()
    finally:
        server.shutdown()
        server.server_close()
    assert hook.received == [{"a": 1}] and '"a": 1' in capsys.readouterr().out
