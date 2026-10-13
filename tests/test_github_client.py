"""Tests for the github_client wrapper — uses MockTransport."""

from __future__ import annotations

import asyncio
import logging
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


@pytest.mark.parametrize("errors, detail", [
    ([{"message": "The requested repositories cannot be searched."}],
     ": The requested repositories cannot be searched."),
    ([{"message": "First error"}, {"message": "Second error"}], ": First error"),
    ([], ""),
    ([{"code": "invalid"}], ""),
    (["invalid"], ""),
    (None, ""),
])
def test_handle_github_error_422_formats_json(errors, detail):
    request = httpx.Request("GET", "https://api.github.com/search/issues")
    response = httpx.Response(
        422, request=request, json={"message": "Validation Failed", "errors": errors},
    )
    err = httpx.HTTPStatusError("validation", request=request, response=response)
    assert github_client.handle_github_error(err) == (
        f"Error: GitHub rejected the request — Validation Failed{detail}"
    )


@pytest.mark.parametrize("body", ["invalid query " * 30, "[]", '{"errors": []}'])
def test_handle_github_error_422_preserves_raw_fallback(body):
    request = httpx.Request("GET", "https://api.github.com/search/issues")
    response = httpx.Response(422, request=request, text=body)
    err = httpx.HTTPStatusError("validation", request=request, response=response)
    assert github_client.handle_github_error(err) == (
        f"Error: GitHub rejected the request — {body[:200]}"
    )


def test_handle_github_error_unknown():
    msg = github_client.handle_github_error(RuntimeError("boom"))
    assert "RuntimeError" in msg


@pytest.mark.asyncio
async def test_github_get_reuses_one_client(monkeypatch):
    """One AsyncClient, one connection pool — not a handshake per request."""
    constructions = {"n": 0}
    built: list[httpx.AsyncClient] = []

    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
    real_async_client = httpx.AsyncClient

    def _counting(*args, **kwargs):
        constructions["n"] += 1
        kwargs["transport"] = transport
        client = real_async_client(*args, **kwargs)
        built.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", _counting)

    # Distinct paths, so the cache cannot hide a second construction.
    await github_client.github_get("/users/one")
    await github_client.github_get("/users/two")
    await github_client.github_get("/users/three")

    assert constructions["n"] == 1, "a client was built per request"
    assert built[0] is github_client._get_client()


@pytest.mark.asyncio
async def test_client_survives_between_requests(monkeypatch):
    """The shared client must still be open after a request completes.

    The previous implementation used `async with`, which closed the client at
    the end of every call; reusing that object would raise.
    """
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, **{**kw, "transport": transport}),
    )

    await github_client.github_get("/users/first", use_cache=False)
    client = github_client._get_client()

    assert not client.is_closed
    await github_client.github_get("/users/second", use_cache=False)
    assert github_client._get_client() is client


@pytest.mark.asyncio
async def test_concurrent_requests_share_the_client(monkeypatch):
    """The fan-out case from the issue: gather must not build N clients."""
    constructions = {"n": 0}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    real_async_client = httpx.AsyncClient

    def _counting(*args, **kwargs):
        constructions["n"] += 1
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _counting)

    await asyncio.gather(*(
        github_client.github_get(f"/repos/o/r/{n}") for n in ("a", "b", "c", "d", "e")
    ))

    assert constructions["n"] == 1


def test_reset_client_forces_a_new_one(monkeypatch):
    """reset_client is the seam tests need after patching httpx.AsyncClient."""
    first = github_client._get_client()
    assert github_client._get_client() is first

    github_client.reset_client()

    assert github_client._get_client() is not first


@pytest.mark.asyncio
async def test_closed_client_is_replaced(monkeypatch):
    """A client closed out from under us is rebuilt rather than reused."""
    client = github_client._get_client()
    await client.aclose()

    assert github_client._get_client() is not client


@pytest.mark.asyncio
async def test_cache_expires_after_ttl(monkeypatch):
    """Cached entries should expire after TTL, forcing a fresh network call."""
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
    github_client.clear_cache()

    # Fake clock: we control time instead of waiting 5 minutes
    fake_now = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake_now["t"])

    # First call: hits network
    await github_client.github_get("/users/expiring")
    assert call_count["n"] == 1

    # Second call immediately: cache hit, no new network request
    await github_client.github_get("/users/expiring")
    assert call_count["n"] == 1, "should be served from cache"

    # Fast-forward past TTL
    fake_now["t"] += github_client.CACHE_TTL_SECONDS + 1

    # Third call: cache expired, hits network again
    await github_client.github_get("/users/expiring")
    assert call_count["n"] == 2, "cache should have expired and re-fetched"


def test_cache_evicts_oldest_when_full(monkeypatch):
    """When cache exceeds max entries, the oldest-expiry entry is evicted."""
    # Shrink the cap so we can fill it with 3 entries
    monkeypatch.setattr(github_client, "CACHE_MAX_ENTRIES", 2)
    github_client.clear_cache()

    # Use a fake clock so each entry gets a distinct expiry time
    fake_now = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake_now["t"])

    # Insert 3 entries; the 3rd triggers eviction of the earliest-expiry one
    fake_now["t"] = 0.0
    github_client._cache_set("key1", "value1")  # expires at 0 + 300 = 300

    fake_now["t"] = 10.0
    github_client._cache_set("key2", "value2")  # expires at 10 + 300 = 310

    fake_now["t"] = 20.0
    github_client._cache_set("key3", "value3")  # expires at 20 + 300 = 320

    # key1 has the earliest expiry (300), should be evicted
    assert "key1" not in github_client._cache, "oldest-expiry entry should be evicted"
    assert "key2" in github_client._cache
    assert "key3" in github_client._cache


def test_get_headers_strips_trailing_whitespace_from_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "  ghp_abc\n")
    assert github_client._get_headers()["Authorization"] == "Bearer ghp_abc"


def test_get_headers_treats_whitespace_only_token_as_no_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "   ")
    assert "Authorization" not in github_client._get_headers()


@pytest.mark.asyncio
async def test_rate_limit_warns_only_once(monkeypatch, caplog):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"name": "octotat"},
            headers={
                "x-ratelimit-remaining": "5",
                "x-ratelimit-reset": str(int(time.time()) + 1800),
            },
        )

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    github_client.reset_client()
    github_client.clear_cache()
    monkeypatch.setattr(github_client, "_rate_limit_warned", False)

    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        await github_client.github_get("/users/octocat", use_cache=False)
        await github_client.github_get("/users/octocat", use_cache=False)

    target_message = "GitHub API quota is running low"
    messages = [
        record.getMessage() for record in caplog.records if target_message in record.getMessage()
    ]

    assert len(messages) == 1


@pytest.mark.asyncio
async def test_rate_limit_warning_resets_after_recovery(monkeypatch, caplog):
    remaining_values = iter(["5", "4000", "5"])

    def mock_handler(request: httpx.Request) -> httpx.Response:
        remaining = next(remaining_values)
        return httpx.Response(
            status_code=200,
            json={"name": "octotat"},
            headers={
                "x-ratelimit-remaining": remaining,
                "x-ratelimit-reset": str(int(time.time()) + 1800),
            },
        )

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    github_client.reset_client()
    github_client.clear_cache()
    monkeypatch.setattr(github_client, "_rate_limit_warned", False)

    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        await github_client.github_get("/users/octocat", use_cache=False)
        await github_client.github_get("/users/octocat", use_cache=False)
        await github_client.github_get("/users/octocat", use_cache=False)

    target_message = "GitHub API quota is running low"
    messages = [
        record.getMessage() for record in caplog.records if target_message in record.getMessage()
    ]

    assert len(messages) == 2
    assert "5 requests remaining" in messages[0]
    assert "5 requests remaining" in messages[1]


@pytest.mark.parametrize(
    "remaining",
    [None, "invalid", "", "10", "4000"],
)
@pytest.mark.asyncio
async def test_rate_limit_does_not_warn_for_safe_or_invalid_headers(monkeypatch, caplog, remaining):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        headers = {}
        if remaining is not None:
            headers["x-ratelimit-remaining"] = remaining

        return httpx.Response(
            status_code=200,
            json={"name": "octotat"},
            headers=headers,
        )

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    github_client.reset_client()
    github_client.clear_cache()
    monkeypatch.setattr(github_client, "_rate_limit_warned", False)

    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        await github_client.github_get("/users/octocat", use_cache=False)

    target_message = "GitHub API quota is running low"
    messages = [
        record.getMessage() for record in caplog.records if target_message in record.getMessage()
    ]

    assert messages == []


@pytest.mark.asyncio
async def test_rate_limit_does_not_warn_on_http_error(monkeypatch, caplog):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=403,
            json={"message": "Forbidden"},
            headers={"x-ratelimit-remaining": "5"},
        )

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    github_client.reset_client()
    github_client.clear_cache()
    monkeypatch.setattr(github_client, "_rate_limit_warned", False)

    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        with pytest.raises(httpx.HTTPStatusError):
            await github_client.github_get("/users/octocat", use_cache=False)

    target_message = "GitHub API quota is running low"
    messages = [
        record.getMessage() for record in caplog.records if target_message in record.getMessage()
    ]

    assert messages == []


@pytest.mark.asyncio
async def test_rate_limit_warns_on_202_response(monkeypatch, caplog):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=202,
            content=b"",
            headers={"x-ratelimit-remaining": "5"},
        )

    transport = httpx.MockTransport(mock_handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    github_client.reset_client()
    github_client.clear_cache()
    monkeypatch.setattr(github_client, "_rate_limit_warned", False)

    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        result = await github_client.github_get(
            "/repos/foo/bar/stats/commit_activity",
            use_cache=False,
        )

    target_message = "GitHub API quota is running low"
    messages = [
        record.getMessage() for record in caplog.records if target_message in record.getMessage()
    ]

    assert result == {}
    assert len(messages) == 1
