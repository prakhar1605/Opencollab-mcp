"""GitHub API client for OpenCollab MCP.

Wraps httpx with:
- Authenticated headers
- Friendly error mapping
- A tiny in-memory TTL cache to soften GitHub rate-limit pressure for
  repeat lookups inside a single conversation.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from .constants import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    DEFAULT_TIMEOUT,
    GITHUB_API_BASE,
    GITHUB_API_VERSION,
    USER_AGENT,
)

logger = logging.getLogger("opencollab_mcp.github")


# ---- in-memory TTL cache --------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}


def _cache_key(path: str, params: dict[str, Any] | None) -> str:
    if not params:
        return path
    items = sorted((k, str(v)) for k, v in params.items())
    return f"{path}?{items}"


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    if len(_cache) >= CACHE_MAX_ENTRIES:
        # Cheap eviction: drop oldest entry by expiry time.
        oldest = min(_cache.items(), key=lambda kv: kv[1][0])[0]
        _cache.pop(oldest, None)
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, value)


def clear_cache() -> None:
    """Useful for tests."""
    _cache.clear()


# ---- HTTP -----------------------------------------------------------------

def _get_headers() -> dict[str, str]:
    """Build auth headers from environment."""
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def github_get(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    use_cache: bool = True,
) -> Any:
    """Make an authenticated GET request to GitHub API.

    Returns parsed JSON. For HTTP 202 (stats still computing) returns an
    empty dict so callers can detect 'not ready yet' without a crash.
    """
    key = _cache_key(path, params)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}{path}",
            headers=_get_headers(),
            params=params or {},
        )

        # GitHub returns 202 with empty body while it computes statistics
        # (commit_activity, participation, contributors on cold repos).
        if resp.status_code == 202:
            logger.info("GitHub returned 202 (stats computing) for %s", path)
            return {}

        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            logger.warning("Non-JSON response from %s", path)
            return {}

    if use_cache:
        _cache_set(key, data)
    return data


async def github_search(
    endpoint: str,
    query: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Search GitHub (issues, repos, etc.)."""
    merged = {"q": query, "per_page": 30, **(params or {})}
    return await github_get(f"/search/{endpoint}", merged)


def _reset_hint(response: httpx.Response) -> str:
    """" Resets in ~N minutes." for a usable x-ratelimit-reset, else "".

    The header is a Unix epoch timestamp. A missing, unparseable or already
    past value yields nothing rather than a nonsense "resets in -3 minutes":
    a vague message beats a wrong one.
    """
    raw = response.headers.get("x-ratelimit-reset", "")
    try:
        reset_at = int(raw)
    except ValueError:
        return ""
    seconds = reset_at - time.time()
    if seconds <= 0:
        return ""
    if seconds < 60:
        return " Resets in under a minute."
    return f" Resets in ~{round(seconds / 60)} minutes."


def handle_github_error(e: Exception) -> str:
    """Return a human-friendly error string for GitHub API failures.

    Always logs full traceback so production deployments can diagnose,
    while users see something concise and actionable.
    """
    logger.exception("GitHub API error: %s", e)

    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return ("Error: GitHub authentication failed. "
                    "Check your GITHUB_TOKEN environment variable.")
        if code in (403, 429):
            # GitHub says which of the two a 403 is: exhausted quota leaves
            # x-ratelimit-remaining at "0", anything else is a permissions
            # problem. Reporting them together sent people to check the wrong
            # thing half the time. 429 is always a limit (secondary limits).
            remaining = e.response.headers.get("x-ratelimit-remaining", "")
            if code == 429 or remaining == "0":
                return (f"Error: GitHub API rate limit exceeded."
                        f"{_reset_hint(e.response)} Set GITHUB_TOKEN for a "
                        f"5,000 requests/hour limit.")
            return ("Error: GitHub denied access (403). Your token may be "
                    "missing the 'public_repo' scope, or the resource is "
                    "private.")
        if code == 404:
            return "Error: Resource not found on GitHub. Double-check the username or repo name."
        if code == 422:
            return f"Error: GitHub rejected the request — {e.response.text[:200]}"
        return f"Error: GitHub API returned status {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: GitHub API request timed out. Please try again."
    return f"Error: Unexpected failure — {type(e).__name__}: {e}"
