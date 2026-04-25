"""Tests for the github_client wrapper — uses MockTransport."""

from __future__ import annotations

import httpx
import pytest

from opencollab_mcp import github_client


@pytest.mark.asyncio
async def test_github_get_returns_json(mock_github):
    mock_github({"/users/octocat": {"login": "octocat", "id": 1}})
    result = await github_client.github_get("/users/octocat")
    assert result == {"login": "octocat", "id": 1}


@pytest.mark.asyncio
async def test_github_get_caches_results(mock_github):
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

    import httpx as httpx_mod
    httpx_mod.AsyncClient = _patched
    try:
        a = await github_client.github_get("/users/cached")
        b = await github_client.github_get("/users/cached")
        assert a == b
        assert call_count["n"] == 1, "cache should have served second call"
    finally:
        httpx_mod.AsyncClient = real_async_client


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


def test_handle_github_error_403_includes_remaining():
    request = httpx.Request("GET", "https://api.github.com/test")
    response = httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, request=request)
    err = httpx.HTTPStatusError("rate", request=request, response=response)
    msg = github_client.handle_github_error(err)
    assert "rate limit" in msg.lower()
    assert "remaining: 0" in msg


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
