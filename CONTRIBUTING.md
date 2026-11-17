# Contributing to Leadbell

Thanks for helping. Small, focused pull requests are the easiest to review and merge.

## Setup

```bash
uv venv --python 3.11 .venv
uv pip install -p .venv -e ".[dev]"
```

## Before you open a pull request

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest --cov
```

## Rules

- Tests never call a real webhook or any paid API. Use the local HTTP server fixture in `tests/conftest.py`.
- Keep the core free of third-party dependencies; FastAPI support stays behind the `fastapi` extra.
- Leadbell must never raise into the host application and never block a request.
- Never weaken consent handling: a lead without consent is never stored or announced.
- New behaviour needs a test, and user-facing changes need a line in `CHANGELOG.md`.
- No Contributor License Agreement or DCO sign-off is required. By contributing you agree that your
  contribution is licensed under the Apache License 2.0.
