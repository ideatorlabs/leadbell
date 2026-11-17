from __future__ import annotations

import pytest

from leadbell import DEFAULT_CONSENT, LeadError, LeadForm, RateLimiter, any_phone, clean_source, india_mobile


def good(**over: object) -> dict[str, object]:
    data: dict[str, object] = {
        "name": "Asha",
        "company": "Sample Store",
        "phone": "+1 555 0100",
        "consent": True,
    }
    data.update(over)
    return data


def test_phone_helpers() -> None:
    assert any_phone("+1 555 0100") == "15550100"
    assert any_phone("12345") is None and any_phone("") is None
    assert india_mobile("99999 00001") == "919999900001"
    assert india_mobile("+91-99999-00001") == "919999900001"
    assert india_mobile("099999 00001") == "919999900001"
    for bad in ("59999 00001", "12345", "", "9199999000012"):
        assert india_mobile(bad) is None


def test_clean_source_keeps_known_short_keys() -> None:
    assert clean_source(None) is None and clean_source("x") is None and clean_source({"junk": 1}) is None
    out = clean_source(
        {"utm_source": " news ", "ref": "r" * 200, "evil": "<script>", "referrer": "example.com"}
    )
    assert out == {"utm_source": "news", "ref": "r" * 80, "referrer": "example.com"}


def test_valid_lead() -> None:
    form = LeadForm(consent_version="2026-01", ref_prefix="DEMO-")
    lead = form.check(
        good(
            name="  Asha   Rao ",
            email="ASHA@EXAMPLE.COM",
            message="Two\nstores",
            source={"utm_source": "expo"},
        )
    )
    assert lead.name == "Asha Rao" and lead.email == "asha@example.com" and lead.message == "Two stores"
    assert lead.phone == "15550100" and lead.source == {"utm_source": "expo"}
    assert lead.consent_version == "2026-01" and lead.consent_text == DEFAULT_CONSENT and not lead.spam
    assert lead.ref.startswith("DEMO-") and len(lead.ref) == 11 and not set(lead.ref[5:]) & set("01IO")
    fields = lead.as_fields()
    assert (
        fields["Source"] == "utm_source=expo"
        and fields["Email"] == "asha@example.com"
        and fields["Message"] == "Two stores"
    )


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"name": " "}, "name"),
        ({"company": ""}, "company"),
        ({"phone": "12"}, "phone"),
        ({"phone": ""}, "phone"),
        ({"email": "not-an-email"}, "email"),
        ({"consent": False}, "consent"),
        ({"consent": "no"}, "consent"),
        ({"consent": None}, "consent"),
    ],
)
def test_invalid_leads(change: dict[str, object], field: str) -> None:
    form = LeadForm(consent_version="v1", limiter=RateLimiter(100, 60))
    with pytest.raises(LeadError) as err:
        form.check(good(**change))
    assert err.value.field == field and err.value.status == 422


def test_consent_accepts_form_checkbox_values() -> None:
    form = LeadForm(consent_version="v1", limiter=RateLimiter(100, 60))
    for value in (True, "on", "true", "1", "yes"):
        assert form.check(good(consent=value)).consent_version == "v1"


def test_email_only_form() -> None:
    form = LeadForm(consent_version="v1", require_phone=False, require_email=True)
    assert form.check(good(phone="", email="sam@example.org")).phone == ""
    with pytest.raises(LeadError) as err:
        form.check(good(phone="", email=""))
    assert err.value.field == "email"


def test_honeypot_returns_spam_lead() -> None:
    form = LeadForm(consent_version="v1")
    lead = form.check(good(website="http://spam.example"))
    assert lead.spam and lead.ref and lead.name == ""


def test_rate_limit_counts_every_submission() -> None:
    clock = [0.0]
    form = LeadForm(consent_version="v1", limiter=RateLimiter(2, 60, clock=lambda: clock[0]))
    form.check(good(website="bot"), "a")
    form.check(good(), "a")
    with pytest.raises(LeadError) as err:
        form.check(good(), "a")
    assert err.value.status == 429
    form.check(good(), "b")  # another client is fine
    clock[0] = 61
    form.check(good(), "a")


def test_rate_limiter_reset_and_memory_bound() -> None:
    lim = RateLimiter(1, 60)
    for i in range(10_002):
        lim.hit(str(i))
    assert not lim.hit("5")
    lim.reset()
    assert lim.hit("5")


def test_consent_version_is_required() -> None:
    with pytest.raises(ValueError):
        LeadForm(consent_version="")
