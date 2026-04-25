"""GitHub API client for OpenCollab MCP.

Uses a module-level httpx.AsyncClient (connection reuse) and a TTL cache
to reduce duplicate calls across chained tools.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = "opencollab-mcp/0.5.0"

# 5 min TTL, max 500 entries — good balance for chained tool calls
_cache: TTLCache = TTLCache(maxsize=500, ttl=300)
_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, creating it if needed."""
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:  # double-checked locking
                _client = httpx.AsyncClient(
                    timeout=DEFAULT_TIMEOUT,
                    http2=False,  # set True once h2 is a dep
                    headers={"User-Agent": USER_AGENT},
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
    return _client


async def aclose() -> None:
    """Close the shared client. Called at shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _cache_key(path: str, params: Optional[dict[str, Any]]) -> tuple:
    items = tuple(sorted((params or {}).items()))
    return (path, items)


async def github_get(
    path: str,
    params: Optional[dict[str, Any]] = None,
    use_cache: bool = True,
) -> Any:
    """Authenticated GET with TTL caching and one retry on 5xx."""
    key = _cache_key(path, params)
    if use_cache and key in _cache:
        logger.debug("cache hit: %s", path)
        return _cache[key]

    client = await _get_client()
    url = f"{GITHUB_API_BASE}{path}"

    for attempt in range(2):
        try:
            resp = await client.get(url, headers=_auth_headers(), params=params or {})
            # GitHub stats endpoints return 202 while computing
            if resp.status_code == 202:
                raise StatsComputingError(path)
            resp.raise_for_status()
            data = resp.json()
            if use_cache:
                _cache[key] = data
            return data
        except httpx.HTTPStatusError as e:
            if 500 <= e.response.status_code < 600 and attempt == 0:
                await asyncio.sleep(1.0)
                continue
            raise


async def github_search(
    endpoint: str,
    query: str,
    params: Optional[dict[str, Any]] = None,
) -> Any:
    """Search GitHub (issues, repositories, etc.)."""
    merged = {"q": query, "per_page": 30, **(params or {})}
    return await github_get(f"/search/{endpoint}", merged)


class StatsComputingError(Exception):
    """GitHub is still computing stats for this repo (202 response)."""
    def __init__(self, path: str):
        super().__init__(f"GitHub is computing stats for {path}. Try again in ~5 seconds.")


def handle_github_error(e: Exception) -> str:
    """Human-friendly error string for GitHub API failures."""
    if isinstance(e, StatsComputingError):
        return f"Info: {e}"
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error: GitHub authentication failed. Check your GITHUB_TOKEN."
        if code == 403:
            remaining = e.response.headers.get("x-ratelimit-remaining", "?")
            reset = e.response.headers.get("x-ratelimit-reset", "")
            reset_msg = ""
            if reset:
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromtimestamp(int(reset), tz=timezone.utc)
                    reset_msg = f" Resets at {dt.isoformat()}."
                except Exception:
                    pass
            return f"Error: GitHub rate limit or permission issue (remaining: {remaining}).{reset_msg}"
        if code == 404:
            return "Error: Not found on GitHub. Double-check the username or repo name."
        if code == 422:
            return f"Error: GitHub rejected the request — {e.response.text[:200]}"
        return f"Error: GitHub API returned status {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: GitHub API request timed out. Please try again."
    return f"Error: Unexpected failure — {type(e).__name__}: {e}"
