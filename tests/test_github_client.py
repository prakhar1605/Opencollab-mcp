"""Tests for the github_client wrapper — uses MockTransport."""

from __future__ import annotations

import time

import httpx
import pytest

from opencollab_mcp import github_client


@pytest.mark.asyncio
async def test_github_get_returns_json(mock_github):
    mock_github({"/users/octocat": {"login": "octocat", "id": 1}})
    result = await github_client.github_get("/users/octocat")
    assert result == {"login": "octocat", "id": 1}


@pytest.mark.asyncio
async def test_github_get_caches_results(monkeypatch):
    """Second call to the same path should hit the cache, not the network."""
    call_count = {"n": 0}

    def _counting_handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"login": "cached"})

    transport = httpx.MockTransport(_counting_handler)
    real_async_client = httpx.AsyncClient

    def _patched(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _patched)

    a = await github_client.github_get("/users/cached")
    b = await github_client.github_get("/users/cached")
    assert a == b
    assert call_count["n"] == 1, "cache should have served second call"


@pytest.mark.asyncio
async def test_github_get_handles_202(mock_github):
    """GitHub returns 202 + empty body when stats are still computing."""
    mock_github({"/repos/foo/bar/stats/commit_activity": (202, b"")})
    result = await github_client.github_get(
        "/repos/foo/bar/stats/commit_activity",
        use_cache=False,
    )
    assert result == {}


@pytest.mark.asyncio
async def test_github_get_raises_on_404(mock_github):
    mock_github({"/users/exists": {"ok": True}})
    with pytest.raises(httpx.HTTPStatusError):
        await github_client.github_get("/users/missing")


def test_handle_github_error_401():
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(401, request=request)
    err = httpx.HTTPStatusError("auth", request=request, response=response)
    msg = github_client.handle_github_error(err)
    assert "authentication" in msg.lower()


def _status_error(code: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_handle_github_error_403_exhausted_quota_is_a_rate_limit():
    msg = github_client.handle_github_error(
        _status_error(403, {"x-ratelimit-remaining": "0"})
    )
    assert "rate limit" in msg.lower()
    assert "GITHUB_TOKEN" in msg
    assert "scope" not in msg.lower(), "a quota problem must not send people to check scopes"


def test_handle_github_error_403_with_quota_left_is_a_permission_problem():
    msg = github_client.handle_github_error(
        _status_error(403, {"x-ratelimit-remaining": "4999"})
    )
    assert "denied access" in msg.lower()
    assert "public_repo" in msg
    assert "rate limit" not in msg.lower(), "a scope problem must not read as a quota problem"


def test_handle_github_error_403_without_the_header_reads_as_permissions():
    # No header at all: GitHub sends the remaining count on every rate-limited
    # response, so its absence is not a quota problem.
    msg = github_client.handle_github_error(_status_error(403))
    assert "denied access" in msg.lower()


def test_handle_github_error_429_is_always_a_rate_limit():
    # Secondary limits come back as 429 with no remaining header.
    msg = github_client.handle_github_error(_status_error(429))
    assert "rate limit" in msg.lower()


def test_rate_limit_message_says_when_to_retry():
    reset = int(time.time()) + 12 * 60
    msg = github_client.handle_github_error(
        _status_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)})
    )
    assert "rate limit" in msg.lower()
    assert "12 minutes" in msg


def test_rate_limit_message_rounds_a_near_reset_to_under_a_minute():
    reset = int(time.time()) + 20
    msg = github_client.handle_github_error(
        _status_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)})
    )
    assert "under a minute" in msg


@pytest.mark.parametrize(
    "reset",
    ["", "not-a-number", str(int(time.time()) - 300)],
)
def test_rate_limit_message_omits_a_reset_it_cannot_trust(reset):
    # A missing, unparseable or already-past reset must not become
    # "resets in ~-5 minutes" — vague beats wrong.
    msg = github_client.handle_github_error(
        _status_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset})
    )
    assert "rate limit" in msg.lower()
    assert "resets in" not in msg.lower()
    assert "-" not in msg.split("exceeded.")[1]


def test_handle_github_error_404():
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(404, request=request)
    err = httpx.HTTPStatusError("nf", request=request, response=response)
    msg = github_client.handle_github_error(err)
    assert "not found" in msg.lower()


def test_handle_github_error_timeout():
    err = httpx.TimeoutException("slow")
    msg = github_client.handle_github_error(err)
    assert "timed out" in msg.lower()


def test_handle_github_error_unknown():
    msg = github_client.handle_github_error(RuntimeError("boom"))
    assert "RuntimeError" in msg
