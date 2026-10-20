"""Shared helpers used across all OpenCollab tool modules."""

from __future__ import annotations

import base64 as _base64
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


def difficulty_label(difficulty: str) -> str:
    return 'label:"good first issue"' if difficulty == "beginner" else 'label:"help wanted"'


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
    # isascii() because str.isdigit() also accepts characters like '²' that
    # int() then rejects; the explicit zero check because '0' is all digits
    # but GitHub issue numbers start at 1.
    if not (cleaned.isascii() and cleaned.isdigit()) or int(cleaned) == 0:
        raise ValueError(f"issue_number must be a positive integer, got {raw!r}")
    return int(cleaned)


def parse_github_url(url: str) -> tuple[str, str, int | None]:
    """Parse a GitHub repository, issue or pull URL without making a request.

    Accept HTTP(S), optional www, one trailing slash, query and fragment.
    Reject userinfo, ports and extra path components rather than guessing.
    """
    if not isinstance(url, str) or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError("Expected a GitHub HTTP(S) URL")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in (
        "github.com",
        "www.github.com",
    ):
        raise ValueError("Expected a GitHub HTTP(S) URL")
    path = parsed.path.removesuffix("/")
    parts = path.split("/")
    if len(parts) not in (3, 5) or parts[0] != "":
        raise ValueError("Expected a repository, issue or pull URL")
    owner, repo = parts[1:3]
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", owner)
        or not re.fullmatch(r"[A-Za-z0-9._-]+", repo)
        or repo in (".", "..")
    ):
        raise ValueError("Invalid GitHub owner or repository")
    if len(parts) == 3:
        return owner, repo, None
    if parts[3] not in ("issues", "pull"):
        raise ValueError("Expected an issue or pull URL")
    return owner, repo, parse_issue_number(parts[4])


def decode_base64_content(content_obj: dict) -> str:
    """Decode a GitHub contents-API base64 blob to UTF-8 text."""
    if content_obj.get("encoding") != "base64":
        return ""
    return _base64.b64decode(content_obj.get("content", "")).decode("utf-8", errors="replace")
