# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-17

### Added

- Initial release.
- `Notifier`: business-event cards (sign-up, lead, first real use, payment, churn, or your own kinds) to
  Discord, Slack or any JSON webhook, sent from a background thread, never raising; environment gating.
- `clean()` and `source_text()`: visitor text made safe for chat cards; one-line first-touch summary.
- `LeadForm` / `Lead` / `LeadError`: lead-form validation with required consent (wording and version
  stored), honeypot, per-client rate limit, short references.
- Phone checks: `any_phone` (7–15 digits) and `india_mobile`.
- `source.js` first-touch script and `source_js()`.
- `leadbell.fastapi.lead_router()`: `POST /leads` (JSON or form) and the script route.

[Unreleased]: https://github.com/ideatorlabs/leadbell/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ideatorlabs/leadbell/releases/tag/v0.1.0
