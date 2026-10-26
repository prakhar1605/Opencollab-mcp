"""Shared helpers used across all OpenCollab tool modules."""

from __future__ import annotations

import base64 as _base64
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit
from .constants import (
    BEGINNER_SEARCH_LABELS,
    INTERMEDIATE_SEARCH_LABELS
)

def difficulty_label(difficulty: str) -> str:
    result=", ".join(BEGINNER_SEARCH_LABELS if difficulty == "beginner" else INTERMEDIATE_SEARCH_LABELS)
    return 'label:'+result


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


# HTML comments and code spans/blocks inside PR descriptions do not create
# GitHub closing links (e.g. unfilled template hints like `<!-- Closes #12 -->`
# or prose notes like ``did not write `Closes #12` intentionally``).
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")

# Official GitHub closing keywords:
# https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue
_CLOSING_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"
    r"(?:\s*:\s*|\s+)"
    r"(?:"
    r"https?://(?:www\.)?github\.com/"
    r"(?P<url_owner>[A-Za-z0-9][A-Za-z0-9_-]*)/"
    r"(?P<url_repo>[A-Za-z0-9._-]+)/issues/(?P<url_num>[1-9][0-9]*)/?"
    r"|(?P<ref_owner>[A-Za-z0-9][A-Za-z0-9_-]*)/(?P<ref_repo>[A-Za-z0-9._-]+)#(?P<ref_num>[1-9][0-9]*)"
    r"|#(?P<local_num>[1-9][0-9]*)"
    r")"
    r"(?![A-Za-z0-9_/])",
    re.IGNORECASE,
)


def extract_issue_repo(issue_obj: dict[str, Any]) -> tuple[str, str] | None:
    """Extract `(owner, repo)` from a GitHub REST issue/PR object if present."""
    repo_obj = issue_obj.get("repository")
    if isinstance(repo_obj, dict):
        full_name = repo_obj.get("full_name", "")
        if isinstance(full_name, str) and "/" in full_name:
            parts = full_name.split("/", 1)
            if parts[0] and parts[1]:
                return parts[0], parts[1]

    repo_url = issue_obj.get("repository_url")
    if isinstance(repo_url, str) and "/repos/" in repo_url:
        tail = repo_url.split("/repos/", 1)[1].strip("/")
        parts = tail.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]

    html_url = issue_obj.get("html_url")
    if isinstance(html_url, str) and html_url:
        try:
            owner, repo, _ = parse_github_url(html_url)
            return owner, repo
        except ValueError:
            pass

    return None


def pr_closes_issue(
    title: str | None,
    body: str | None,
    *,
    owner: str,
    repo: str,
    issue_number: int,
    pr_repo: tuple[str, str] | None = None,
) -> bool:
    """Return True if a PR's title or body contains a GitHub closing reference
    targeting `owner/repo#issue_number`.

    Supports all nine GitHub closing keywords (`close/s/d`, `fix/es/ed`,
    `resolve/s/d`), optional colons, `#N` (when the PR lives in the same
    repository), `owner/repo#N`, and full issue URLs.
    """
    target_repo = (owner.lower(), repo.lower())
    same_repo = pr_repo is None or (pr_repo[0].lower(), pr_repo[1].lower()) == target_repo

    cleaned_body = ""
    if body:
        cleaned_body = _HTML_COMMENT_RE.sub(" ", body)
        cleaned_body = _FENCED_CODE_RE.sub(" ", cleaned_body)
        cleaned_body = _INLINE_CODE_RE.sub(" ", cleaned_body)

    for text in (title or "", cleaned_body):
        if not text:
            continue
        for match in _CLOSING_REF_RE.finditer(text):
            if match.group("url_num") is not None:
                ref_target = (
                    match.group("url_owner").lower(),
                    match.group("url_repo").lower(),
                )
                if ref_target == target_repo and int(match.group("url_num")) == issue_number:
                    return True
            elif match.group("ref_num") is not None:
                ref_target = (
                    match.group("ref_owner").lower(),
                    match.group("ref_repo").lower(),
                )
                if ref_target == target_repo and int(match.group("ref_num")) == issue_number:
                    return True
            elif match.group("local_num") is not None:
                if same_repo and int(match.group("local_num")) == issue_number:
                    return True

    return False
