"""A one-page site with a demo-request form: consent, honeypot, rate limit and first-touch source.

LEADBELL_WEBHOOK_URL=http://127.0.0.1:8766/ LEADBELL_SEND_LOCAL=1 uvicorn examples.site:app
open http://127.0.0.1:8000/?utm_source=newsletter
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from leadbell import DEFAULT_CONSENT, Lead, LeadForm, Notifier
from leadbell.fastapi import lead_router

app = FastAPI(title="sample-site")
LEADS: list[Lead] = []  # a real site saves to its database
bell = Notifier()
form = LeadForm(consent_version="2026-01")
app.include_router(lead_router(form, save=LEADS.append, notifier=bell))

PAGE = f"""<!doctype html><meta charset="utf-8"><title>Sample Store software</title>
<script src="/leadbell/source.js"></script>
<h1>Book a demo</h1>
<form id="demo">
  <p><label>Name <input name="name" required></label></p>
  <p><label>Business <input name="company" required></label></p>
  <p><label>Phone <input name="phone" required></label></p>
  <input name="website" tabindex="-1" autocomplete="off" aria-hidden="true"
         style="position:absolute;left:-9999px">
  <p><label><input type="checkbox" name="consent"> {DEFAULT_CONSENT}</label></p>
  <button>Request a demo</button>
</form>
<p id="msg" role="status"></p>
<script>
document.getElementById("demo").addEventListener("submit", async (e) => {{
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  data.consent = e.target.consent.checked;
  data.source = window.leadbellSource();
  const res = await fetch("/leads", {{method: "POST", headers: {{"Content-Type": "application/json"}},
                                      body: JSON.stringify(data)}});
  const body = await res.json();
  document.getElementById("msg").textContent = res.ok ? "Thanks! Reference " + body.ref : body.detail;
}});
</script>"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return PAGE
