"""Shared helpers used across all OpenCollab tool modules."""

from __future__ import annotations

import base64 as _base64
from datetime import datetime, timedelta, timezone


def days_ago(iso_str: str | None) -> int | None:
    """Days between an ISO timestamp and now (UTC). None if unparseable."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def truncate(text: str | None, length: int = 120) -> str:
    """Truncate to `length` chars, appending an ellipsis if cut."""
    if not text:
        return ""
    return text[:length] + ("…" if len(text) > length else "")


def recent_date_str(days_back: int = 90) -> str:
    """Return ISO date for `days_back` days before today (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")


def parse_issue_number(raw: str) -> int:
    """Parse an issue number safely.

    Accepts '123', '#123', ' 123 '. Raises ValueError otherwise.
    """
    cleaned = raw.strip().lstrip("#").strip()
    if not cleaned.isdigit():
        raise ValueError(f"issue_number must be a positive integer, got {raw!r}")
    return int(cleaned)


def decode_base64_content(content_obj: dict) -> str:
    """Decode a GitHub contents-API base64 blob to UTF-8 text."""
    if content_obj.get("encoding") != "base64":
        return ""
    return _base64.b64decode(content_obj.get("content", "")).decode(
        "utf-8", errors="replace"
    )
