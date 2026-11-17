"""Static assets shipped with Leadbell."""

from __future__ import annotations

from importlib.resources import files

__all__ = ["source_js"]


def source_js() -> str:
    """The first-touch source script, to serve at a URL of your choice."""
    return files(__package__).joinpath("source.js").read_text(encoding="utf-8")
