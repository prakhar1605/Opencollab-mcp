"""GitHub API client for OpenCollab MCP.

Wraps httpx with:
- Authenticated headers
- Friendly error mapping
- A tiny in-memory TTL cache to soften GitHub rate-limit pressure for
  repeat lookups inside a single conversation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from .constants import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    DEFAULT_TIMEOUT,
    GITHUB_API_BASE,
    GITHUB_API_VERSION,
    GITHUB_DEFAULT_MAX_PAGES,
    GITHUB_RATE_LIMIT_WARNING_THRESHOLD,
    GITHUB_RETRY_DELAY_SECONDS,
    USER_AGENT,
)

logger = logging.getLogger("opencollab_mcp.github")

_rate_limit_warned = False
_graphql_rate_limit_warned = False

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

# One client, one connection pool. Tools like repo_health and
# generate_pr_plan fan out 3-5 requests through asyncio.gather, and a
# per-request client paid a fresh TCP + TLS handshake for every one of them.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Return the shared client, creating it on first use."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    return _client


def reset_client() -> None:
    """Drop the shared client so the next request builds a fresh one.

    Useful for tests, in the same way as clear_cache(): a test that installs a
    mock transport by patching httpx.AsyncClient needs the next request to go
    through the patch rather than reuse a client built earlier. The old client
    is not awaited closed — it holds only idle pooled connections, and this is
    not a production code path.
    """
    global _client, _rate_limit_warned, _graphql_rate_limit_warned
    _client = None
    _rate_limit_warned = False
    _graphql_rate_limit_warned = False


def _get_token() -> str:
    """Return stripped auth token (`GITHUB_TOKEN` preferred over `GH_TOKEN`)."""
    return (
        os.environ.get("GITHUB_TOKEN", "").strip()
        or os.environ.get("GH_TOKEN", "").strip()
    )


def has_github_token() -> bool:
    """Return True when a non-empty GitHub token is configured."""
    return bool(_get_token())


def _get_headers() -> dict[str, str]:
    """Build auth headers from environment."""
    # Strip whitespace: a token from a file or `$(cat token.txt)` often
    # carries a trailing newline, which httpx rejects as an illegal header
    # value with an error that doesn't mention the token at all.
    token = _get_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _validate_api_url(url: str) -> None:
    """Ensure `url` targets `GITHUB_API_BASE` before sending auth headers."""
    expected = urlsplit(GITHUB_API_BASE)
    parsed = urlsplit(url)
    if (
        parsed.scheme.lower() != expected.scheme.lower()
        or parsed.netloc.lower() != expected.netloc.lower()
    ):
        raise ValueError(
            f"Refusing to send GitHub API request to untrusted URL: {url!r}"
        )


async def _request(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    label: str | None = None,
) -> tuple[Any, bool, httpx.Response]:
    """Perform a single authenticated GET with retry, rate-limit check, and JSON parsing.

    Returns `(data, cacheable, response)`. HTTP 202 (stats still computing) and
    non-JSON bodies return `({}, False, response)` so callers degrade gracefully
    without caching transient placeholders.
    """
    _validate_api_url(url)
    target = label or url

    for attempt in range(2):
        req_kwargs: dict[str, Any] = {"headers": _get_headers()}
        if params is not None:
            req_kwargs["params"] = params
        resp = await _get_client().get(url, **req_kwargs)
        if resp.status_code not in (502, 503, 504) or attempt == 1:
            break
        await asyncio.sleep(GITHUB_RETRY_DELAY_SECONDS)

    resp.raise_for_status()
    _check_rate_limit(resp)

    # GitHub returns 202 with empty body while it computes statistics
    # (commit_activity, participation, contributors on cold repos).
    if resp.status_code == 202:
        logger.info("GitHub returned 202 (stats computing) for %s", target)
        return {}, False, resp

    try:
        data = resp.json()
    except ValueError:
        logger.warning("Non-JSON response from %s", target)
        return {}, False, resp

    return data, True, resp


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

    data, cacheable, _ = await _request(
        f"{GITHUB_API_BASE}{path}",
        params=params or {},
        label=path,
    )
    if use_cache and cacheable:
        _cache_set(key, data)
    return data


async def github_get_all(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    max_pages: int = GITHUB_DEFAULT_MAX_PAGES,
    use_cache: bool = True,
) -> tuple[list[Any], bool]:
    """Follow `Link: rel="next"` until exhausted or `max_pages`; return `(items, truncated)`.

    Caches the assembled `(items, truncated)` snapshot under an isolated key so:
    1. Repeated calls return a consistent snapshot without page-boundary drift.
    2. Multi-page scans occupy one slot in `CACHE_MAX_ENTRIES` rather than `N`.
    3. Single-page `github_get` calls on the same path never collide in shape.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    key = f"all:{max_pages}:{_cache_key(path, params)}"
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            cached_items, cached_truncated = cached
            return list(cached_items), cached_truncated

    items: list[Any] = []
    next_url: str | None = f"{GITHUB_API_BASE}{path}"
    next_params: dict[str, Any] | None = params or {}
    seen_urls: set[str] = set()
    pages_fetched = 0
    truncated = False
    cacheable = True

    while next_url is not None:
        data, page_cacheable, resp = await _request(
            next_url,
            params=next_params,
            label=path if pages_fetched == 0 else next_url,
        )
        pages_fetched += 1
        next_params = None  # Subsequent `Link` URLs already carry query/cursor params.

        if not page_cacheable or not isinstance(data, list):
            cacheable = page_cacheable
            break

        items.extend(data)
        raw_next = resp.links.get("next", {}).get("url")
        candidate = raw_next if isinstance(raw_next, str) and raw_next else None

        if candidate is None or candidate in seen_urls:
            truncated = False
            break
        if pages_fetched >= max_pages:
            truncated = True
            break

        seen_urls.add(candidate)
        next_url = candidate

    if use_cache and cacheable:
        _cache_set(key, (list(items), truncated))
    return items, truncated


class GitHubGraphQLError(Exception):
    """Raised when GitHub's GraphQL endpoint returns HTTP 200 with `errors`."""

    def __init__(self, errors: list[Any], response: httpx.Response) -> None:
        self.errors = errors
        self.response = response
        first = errors[0] if errors and isinstance(errors[0], dict) else {}
        self.error_type: str = str(first.get("type") or "").upper()
        message = first.get("message")
        self.detail: str = (
            message if isinstance(message, str) and message else "GraphQL query failed"
        )
        super().__init__(self.detail)


async def github_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a POST request against GitHub's GraphQL API.

    GraphQL often returns HTTP 200 with an `errors` list on failure (missing
    resource, missing scopes, or exhausted GraphQL rate limit). Those responses
    raise `GitHubGraphQLError` so callers can either fall back to REST or map
    them through `handle_github_error`.
    """
    body: dict[str, Any] = {"query": query, "variables": variables or {}}
    for attempt in range(2):
        resp = await _get_client().post(
            f"{GITHUB_API_BASE}/graphql",
            headers=_get_headers(),
            json=body,
        )
        if resp.status_code not in (502, 503, 504) or attempt == 1:
            break
        await asyncio.sleep(GITHUB_RETRY_DELAY_SECONDS)

    resp.raise_for_status()
    _check_rate_limit(resp)

    try:
        payload = resp.json()
    except ValueError as err:
        raise GitHubGraphQLError(
            [{"message": "Invalid JSON response from GitHub GraphQL API"}],
            resp,
        ) from err

    if not isinstance(payload, dict):
        raise GitHubGraphQLError(
            [{"message": "Unexpected response format from GitHub GraphQL API"}],
            resp,
        )

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        raise GitHubGraphQLError(errors, resp)

    data = payload.get("data")
    return data if isinstance(data, dict) else {}


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


def _check_rate_limit(response: httpx.Response) -> None:
    """Log a warning when GitHub API quota is running low.

    REST (`core`) and GraphQL (`x-ratelimit-resource: graphql`) maintain
    separate hourly buckets, so their warning flags are tracked independently.
    """
    global _rate_limit_warned, _graphql_rate_limit_warned
    header_value = response.headers.get("x-ratelimit-remaining")
    if header_value is None:
        return
    try:
        remaining = int(header_value)
    except (ValueError, TypeError):
        return
    is_graphql = response.headers.get("x-ratelimit-resource", "").lower() == "graphql"
    if remaining >= GITHUB_RATE_LIMIT_WARNING_THRESHOLD:
        if is_graphql:
            _graphql_rate_limit_warned = False
        else:
            _rate_limit_warned = False
        return
    warned = _graphql_rate_limit_warned if is_graphql else _rate_limit_warned
    if not warned:
        quota_label = "GitHub GraphQL API quota" if is_graphql else "GitHub API quota"
        logger.warning(
            "%s is running low (%s requests remaining).%s"
            "Set GITHUB_TOKEN for a 5,000 requests/hour limit.",
            quota_label,
            remaining,
            _reset_hint(response),
        )
        if is_graphql:
            _graphql_rate_limit_warned = True
        else:
            _rate_limit_warned = True


def _validation_message(response: httpx.Response) -> str:
    fallback = response.text[:200]
    try:
        payload = response.json()
    except ValueError:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        return fallback
    errors = payload.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        detail = errors[0].get("message")
        if isinstance(detail, str) and detail:
            return f"{message}: {detail}"
    return message


def handle_github_error(e: Exception) -> str:
    """Return a human-friendly error string for GitHub API failures.

    Expected HTTP/GraphQL client errors log warnings without tracebacks. Other
    failures retain their traceback for diagnosis while users see guidance.
    """
    if isinstance(e, GitHubGraphQLError):
        logger.warning(
            "GitHub GraphQL error (%s): %s",
            e.error_type or "untyped",
            e.detail,
        )
        detail_lower = e.detail.lower()
        remaining = e.response.headers.get("x-ratelimit-remaining", "")
        if (
            e.error_type == "RATE_LIMITED"
            or remaining == "0"
            or "rate limit" in detail_lower
        ):
            return (
                f"Error: GitHub API rate limit exceeded."
                f"{_reset_hint(e.response)} Set GITHUB_TOKEN for a "
                f"5,000 requests/hour limit."
            )
        if (
            e.error_type in ("UNAUTHORIZED", "UNAUTHENTICATED")
            or "requires authentication" in detail_lower
            or "bad credentials" in detail_lower
        ):
            return (
                "Error: GitHub authentication failed. "
                "Check your GITHUB_TOKEN environment variable."
            )
        if e.error_type in ("FORBIDDEN", "INSUFFICIENT_SCOPES"):
            return (
                "Error: GitHub denied access (403). Your token may be "
                "missing the 'public_repo' scope, or the resource is "
                "private."
            )
        if e.error_type == "NOT_FOUND":
            return "Error: Resource not found on GitHub. Double-check the username or repo name."
        return f"Error: GitHub rejected the request — {e.detail}"

    if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
        logger.warning("GitHub API %s for %s", e.response.status_code, e.request.url)
    else:
        logger.exception("GitHub API error: %s", e, exc_info=(type(e), e, e.__traceback__))

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
            return f"Error: GitHub rejected the request — {_validation_message(e.response)}"
        return f"Error: GitHub API returned status {code}."
    if isinstance(e, httpx.TimeoutException):
        return "Error: GitHub API request timed out. Please try again."
    if isinstance(e, httpx.TransportError):
        return ("Error: Could not reach api.github.com. "
                "Check your internet connection or proxy settings and try again.")
    return f"Error: Unexpected failure — {type(e).__name__}: {e}"
