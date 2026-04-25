"""Tests for the GitHub client — caching, error handling, no real network calls."""
from __future__ import annotations

import httpx
import pytest

from opencollab_mcp import github_client
from opencollab_mcp.github_client import (
    StatsComputingError,
    _cache,
    _cache_key,
    handle_github_error,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


def test_cache_key_stable():
    a = _cache_key("/repos/x/y", {"per_page": 10, "sort": "stars"})
    b = _cache_key("/repos/x/y", {"sort": "stars", "per_page": 10})
    assert a == b


def test_cache_key_distinct():
    a = _cache_key("/repos/x/y", {"per_page": 10})
    b = _cache_key("/repos/x/y", {"per_page": 30})
    assert a != b


def test_handle_github_error_404():
    fake_resp = httpx.Response(404, request=httpx.Request("GET", "https://api.github.com/x"))
    err = httpx.HTTPStatusError("not found", request=fake_resp.request, response=fake_resp)
    msg = handle_github_error(err)
    assert "Not found" in msg


def test_handle_github_error_401():
    fake_resp = httpx.Response(401, request=httpx.Request("GET", "https://api.github.com/x"))
    err = httpx.HTTPStatusError("unauth", request=fake_resp.request, response=fake_resp)
    msg = handle_github_error(err)
    assert "authentication" in msg.lower()


def test_handle_github_error_403_with_reset():
    fake_resp = httpx.Response(
        403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1735689600"},
        request=httpx.Request("GET", "https://api.github.com/x"),
    )
    err = httpx.HTTPStatusError("rate", request=fake_resp.request, response=fake_resp)
    msg = handle_github_error(err)
    assert "rate limit" in msg.lower()
    assert "remaining: 0" in msg


def test_handle_stats_computing_error():
    err = StatsComputingError("/repos/x/y/stats/commit_activity")
    msg = handle_github_error(err)
    assert "computing" in msg.lower()


def test_handle_timeout():
    err = httpx.TimeoutException("timeout")
    msg = handle_github_error(err)
    assert "timed out" in msg.lower()


@pytest.mark.asyncio
async def test_github_get_uses_cache(monkeypatch):
    """Second call with same params should hit cache, not make a request."""
    call_count = {"n": 0}

    class FakeClient:
        async def get(self, url, headers, params):
            call_count["n"] += 1
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr(github_client, "_get_client", fake_get_client)

    r1 = await github_client.github_get("/test", {"a": 1})
    r2 = await github_client.github_get("/test", {"a": 1})
    assert r1 == {"ok": True}
    assert r2 == {"ok": True}
    assert call_count["n"] == 1  # second call cached


@pytest.mark.asyncio
async def test_github_get_raises_stats_computing(monkeypatch):
    """A 202 response should raise StatsComputingError."""
    class FakeClient:
        async def get(self, url, headers, params):
            return httpx.Response(202, request=httpx.Request("GET", url))

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr(github_client, "_get_client", fake_get_client)

    with pytest.raises(StatsComputingError):
        await github_client.github_get("/repos/x/y/stats/commit_activity", use_cache=False)
