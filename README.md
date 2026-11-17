<p align="center"><img src="https://raw.githubusercontent.com/ideatorlabs/.github/main/assets/avatar.png" width="72" alt="Ideator Labs"></p>
<h1 align="center">Leadbell</h1>
<p align="center"><b>Website lead capture and business-event alerts for small SaaS teams: consent-checked, spam-resistant demo requests, and one tidy card per sign-up, lead or payment in Discord, Slack or any webhook.</b><br><sub>An open-source package by <a href="https://github.com/ideatorlabs">Ideator Labs</a></sub></p>
<p align="center">
  <a href="https://github.com/ideatorlabs/leadbell/actions/workflows/ci.yml"><img src="https://github.com/ideatorlabs/leadbell/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache-2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
</p>

## Why it exists

Early on, every lead matters and nobody watches a CRM. Leadbell puts the moments that matter (a demo
request, a sign-up, the first time a customer really uses the product, a payment) in the channel your team
already reads, and makes the website form behind it safe: consent recorded with the wording version,
bots turned away quietly, and the visitor's first-touch source (utm tags, referral code, referring site)
carried all the way to the card.

It pairs with [Faultbell](https://github.com/ideatorlabs/faultbell): Faultbell rings for problems,
Leadbell rings for new business.

## Features

- **Business-event cards**: `Notifier.event("signup", {...})` posts one card to Discord, Slack or any JSON
  webhook. Built-in kinds: `signup`, `lead`, `activated`, `paid`, `churned`; add your own.
- **Safe with visitor text**: chat markdown, links and mentions are stripped, so a form can't format, link
  or `@everyone` your channel. Every value is one line and length-capped.
- **Never in the way**: one background thread sends; a webhook error or full queue drops the card and
  counts it. Nothing ever raises into your code. Off outside the environments you list (default
  production, staging, demo).
- **Lead capture with consent**: `LeadForm.check()` validates name, business, phone or email, requires the
  consent box, stores the consent wording and its version, and returns a `Lead` with a short reference.
- **Spam-resistant without a captcha**: a honeypot field (bots get a normal-looking success and nothing is
  stored) plus a per-client rate limit (default 5 per hour).
- **First-touch source**: a 1 KB script remembers where a visitor first came from; send it with the form or
  your sign-up and it shows on the card as `utm_source=newsletter, from example.com`.
- **Phone checks**: any international number (7–15 digits) by default; `india_mobile` normalises Indian
  mobiles to `91XXXXXXXXXX`; pass your own function for other rules.
- **FastAPI in one line** (optional extra): `lead_router()` adds `POST /leads` (JSON or form posts) and
  serves the source script.
- **Zero dependencies** in the core (standard library only).

## Install

```bash
pip install leadbell             # core, standard library only
pip install "leadbell[fastapi]"  # with the FastAPI router
```

> Until the first PyPI release, install straight from GitHub:
> `pip install "leadbell @ git+https://github.com/ideatorlabs/leadbell"`

## Quickstart: business events

Create a webhook in your chat tool and export it:

```bash
export LEADBELL_WEBHOOK_URL="<your webhook URL>"
export LEADBELL_ENV=production           # or LEADBELL_SEND_LOCAL=1 to try it from your laptop
export LEADBELL_FORMAT=discord           # discord (default), slack or json
```

```python
from leadbell import Notifier, source_text

bell = Notifier()
bell.event(
    "signup",
    {
        "Business": "Sample Store",
        "City": "Pune",
        "Owner": "Asha",
        "Source": source_text({"utm_source": "newsletter", "referrer": "example.com"}),
    },
)
bell.event("activated", {"Business": "Sample Store", "What": "sent its first quote"})
bell.event("plan_upgrade", {"Business": "Sample Store", "Plan": "Team"}, title="Plan upgraded")
bell.flush()
```

## Quickstart: a lead form with FastAPI

```python
from fastapi import FastAPI

from leadbell import Lead, LeadForm, Notifier
from leadbell.fastapi import lead_router

app = FastAPI(title="sample-site")
leads: list[Lead] = []  # use your database here

form = LeadForm(consent_version="2026-01")  # bump when the consent wording changes
app.include_router(lead_router(form, save=leads.append, notifier=Notifier()))
```

On the page, include the source script once and post the form as JSON:

```html
<script src="/leadbell/source.js"></script>
<form id="demo">
  <input name="name" required> <input name="company" required> <input name="phone" required>
  <input name="website" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px">
  <label><input type="checkbox" name="consent"> I agree to be contacted about this request.</label>
  <button>Request a demo</button>
</form>
<script>
document.getElementById("demo").addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  data.consent = e.target.consent.checked;
  data.source = window.leadbellSource();
  const res = await fetch("/leads", {method: "POST", headers: {"Content-Type": "application/json"},
                                     body: JSON.stringify(data)});
  const body = await res.json();          // {"ok": true, "ref": "L-7KQ2MX"} or {"detail": "...", "field": "phone"}
});
</script>
```

Without FastAPI, call the form directly:

```python
from leadbell import LeadError, LeadForm, india_mobile

form = LeadForm(consent_version="2026-01", phone=india_mobile, ref_prefix="DEMO-")
try:
    lead = form.check(
        {
            "name": "Ravi",
            "company": "Sample Store",
            "phone": "099999 00001",
            "consent": "on",
            "source": {"utm_source": "expo", "junk": "dropped"},
        },
        client_key="203.0.113.7",
    )
except LeadError as err:
    print(err.field, err)  # show the message next to the field
else:
    print(lead.phone, lead.source)  # 919999900001 {'utm_source': 'expo'}
```

## Concepts

| Piece | What it does |
|---|---|
| `Notifier` | Formats and sends cards on a daemon thread. `enabled` is true only with a webhook URL and an environment in `send_envs` (or `send_local`). `sent`, `failed`, `dropped` count what happened. |
| `Kind` | Title and colour of a card kind. Pass `kinds={"trial_ending": Kind("Trial ends in 3 days", 0xE5782C)}` to add or override. Unknown kinds still send, titled from the kind name. |
| `LeadForm` | Validates one submission: required name and business, phone (and/or email), consent; honeypot; rate limit. Raises `LeadError(message, field, status)`. |
| `Lead` | The accepted submission, with `ref`, `consent_text`, `consent_version`, cleaned `source` and `created_at`. `as_fields()` gives card fields. `spam=True` means "answer OK, store nothing". |
| `clean_source` | Keeps only `utm_*`, `ref`, `landing` and `referrer`, each capped at 80 characters. |
| `source.js` | Stores the first touch in `localStorage` once; read it with `window.leadbellSource()`. Sends nothing by itself. |

## Configuration

| Setting | Argument | Environment variable | Default |
|---|---|---|---|
| Webhook | `Notifier(webhook_url=)` | `LEADBELL_WEBHOOK_URL` | none (off) |
| Environment name | `env=` | `LEADBELL_ENV` | `local` |
| Environments that send | `send_envs=` |  | production, staging, demo |
| Send from local | `send_local=` | `LEADBELL_SEND_LOCAL` | off |
| Card format | `format=` | `LEADBELL_FORMAT` | `discord` |
| Rate limit | `LeadForm(limiter=RateLimiter(5, 3600))` |  | 5 per hour per client |
| Honeypot field | `honeypot_field=` |  | `website` |

Cards from environments other than production carry the environment in the title, e.g. "New sign-up (demo)".

## Privacy

- Leadbell stores nothing itself; `save` is your function. Store the `consent_text` and `consent_version`
  with each lead so you can show what the person agreed to.
- The source script keeps the first touch only in the visitor's browser until they submit a form.
- Cards contain what you pass in. Keep them to what your team needs to follow up.

## Running the example

```bash
uv venv .venv && uv pip install -p .venv -e ".[dev]" uvicorn
.venv/bin/python examples/local_webhook.py &               # prints every card it receives
LEADBELL_WEBHOOK_URL=http://127.0.0.1:8766/ LEADBELL_SEND_LOCAL=1 .venv/bin/uvicorn examples.site:app
# open http://127.0.0.1:8000/?utm_source=newsletter and send the form
```

## Testing

```bash
uv venv .venv && uv pip install -p .venv -e ".[dev]"
.venv/bin/pytest --cov
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```

The suite never touches a real webhook: a local HTTP server plays the webhook, and the README's Python
blocks and the example are executed against it.

## Limitations and non-goals

- Not a CRM: no lead list, no pipeline, no reminders. Store leads where you keep the rest of your data.
- The rate limit lives in one process; behind several workers each has its own counter.
- Delivery is best effort. A failed or dropped card is counted, never retried later.
- The honeypot stops simple bots, not a determined human. Add a captcha if you are targeted.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
