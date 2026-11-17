from __future__ import annotations

import pytest

from conftest import FakeWebhook
from leadbell import Kind, Notifier, clean, source_text


def test_clean_strips_markdown_links_and_mentions() -> None:
    assert (
        clean("**hi** @everyone see https://evil.example/x [x](y) <@123>")
        == "hi everyone see (link) x(y) 123"
    )
    assert clean(None) == ""
    assert clean("a\n\tb   c") == "a b c"
    assert len(clean("x" * 1000)) == 300
    assert clean("utm_source") == "utm_source"


def test_source_text() -> None:
    assert source_text(None) == "direct"
    assert source_text({}) == "direct"
    assert source_text({"landing": "/"}) == "direct"
    assert (
        source_text({"utm_source": "news*letter", "ref": "expo", "referrer": "example.com"})
        == "utm_source=newsletter, ref=expo, from example.com"
    )


def test_disabled_without_url_or_outside_send_envs(webhook: FakeWebhook) -> None:
    assert not Notifier().enabled
    assert not Notifier(webhook.url).enabled  # env "local"
    assert not Notifier(webhook.url, env="local").event("signup", {"A": "b"})
    assert Notifier(webhook.url, env="local", send_local=True).enabled
    assert Notifier(webhook.url, env="production").enabled


def test_env_variables(webhook: FakeWebhook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEADBELL_WEBHOOK_URL", webhook.url)
    monkeypatch.setenv("LEADBELL_ENV", "demo")
    monkeypatch.setenv("LEADBELL_FORMAT", "json")
    bell = Notifier()
    assert bell.enabled and bell.format == "json"
    monkeypatch.setenv("LEADBELL_ENV", "local")
    monkeypatch.setenv("LEADBELL_SEND_LOCAL", "1")
    assert Notifier().enabled


def test_discord_card_end_to_end(webhook: FakeWebhook) -> None:
    bell = Notifier(webhook.url, env="production")
    assert bell.event("signup", {"Business": "Sample Store", "Note": "**urgent** @here", "Long": "x" * 40})
    assert bell.flush()
    [card] = webhook.wait_for(1)
    embed = card["embeds"][0]
    assert embed["title"] == "New sign-up" and embed["color"] == 0x1E4D3B
    fields = {f["name"]: f for f in embed["fields"]}
    assert fields["Note"]["value"] == "urgent here"
    assert fields["Business"]["inline"] is True and fields["Long"]["inline"] is False
    assert card["allowed_mentions"] == {"parse": []}
    assert bell.sent == 1


def test_slack_and_json_formats_and_custom_kinds(webhook: FakeWebhook) -> None:
    slack = Notifier(webhook.url, env="demo", format="slack")
    slack.event("lead", {"Name": "Asha", "Empty": ""})
    custom = Notifier(
        webhook.url, env="production", format="json", kinds={"trial_ending": Kind("Trial ends soon", 1)}
    )
    custom.event("trial_ending", {"Business": "Sample Store"})
    custom.event("plan_upgrade", {"Plan": "Team"})
    custom.event("paid", {"Amount": "999"}, title="Paid **twice**")
    slack.flush()
    custom.flush()
    cards = webhook.wait_for(4)
    titles = sorted(c.get("text") or c.get("title") for c in cards)
    assert titles == ["New demo request (demo)", "Paid twice", "Plan upgrade", "Trial ends soon"]
    slack_card = next(c for c in cards if "blocks" in c)
    assert "*Empty:* –" in slack_card["blocks"][1]["text"]["text"]
    json_card = next(c for c in cards if c.get("kind") == "trial_ending")
    assert json_card["fields"] == {"Business": "Sample Store"}


def test_bad_format_is_refused() -> None:
    with pytest.raises(ValueError):
        Notifier(format="carrier-pigeon")


def test_webhook_errors_are_counted_not_raised(webhook: FakeWebhook) -> None:
    webhook.status = 500
    bell = Notifier(webhook.url, env="production")
    assert bell.event("lead", {"Name": "Asha"})
    assert bell.flush()
    assert bell.failed == 1 and bell.sent == 0


def test_full_queue_drops_and_counts() -> None:
    import threading

    gate = threading.Event()

    def slow_post(url: str, body: bytes, timeout: float) -> None:
        gate.wait(2)

    bell = Notifier("http://127.0.0.1:9/", env="production", queue_size=1, post=slow_post)
    results = [bell.event("lead", {"N": str(i)}) for i in range(5)]
    gate.set()
    assert results[0] is True and False in results and bell.dropped >= 1
    assert bell.flush()


def test_unserialisable_values_never_raise() -> None:
    bell = Notifier("http://127.0.0.1:9/", env="production", post=lambda *a: None)
    assert bell.event("lead", {"Obj": object()})  # str() of anything is fine
    bell.payload = lambda *a, **k: (_ for _ in ()).throw(TypeError("boom"))  # type: ignore[method-assign]
    assert bell.event("lead", {"A": "b"}) is False


def test_flush_times_out_when_sender_is_stuck() -> None:
    import threading

    gate = threading.Event()
    bell = Notifier("http://127.0.0.1:9/", env="production", post=lambda *a: gate.wait(2))
    bell.event("lead", {"A": "b"})
    assert bell.flush(timeout=0.05) is False
    gate.set()
    assert bell.flush()
