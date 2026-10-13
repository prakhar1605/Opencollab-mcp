"""Retry temporary server failures once without retrying client errors."""

import asyncio

import httpx
import pytest

from opencollab_mcp import github_client


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [502, 503, 504])
@pytest.mark.parametrize("recovers", [True, False])
async def test_transient_failure_retries_once(monkeypatch, status, recovers):
    requests, delays = [], []

    def handler(request):
        requests.append(request)
        code = 200 if recovers and len(requests) > 1 else status
        return httpx.Response(code, json={"ok": True})

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(github_client, "GITHUB_RETRY_DELAY_SECONDS", 0, raising=False)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        if recovers:
            assert await github_client.github_get("/test", {"per_page": 2}) == {"ok": True}
            assert await github_client.github_get("/test", {"per_page": 2}) == {"ok": True}
        else:
            with pytest.raises(httpx.HTTPStatusError) as exc:
                await github_client.github_get("/test", {"per_page": 2})
            assert exc.value.response.status_code == status
            assert github_client._cache == {}
    assert len(requests) == 2
    assert requests[0].url == requests[1].url
    assert requests[0].headers == requests[1].headers
    assert delays == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429, 500, 501])
async def test_other_statuses_are_not_retried(monkeypatch, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        with pytest.raises(httpx.HTTPStatusError):
            await github_client.github_get("/test")
    assert len(requests) == 1
