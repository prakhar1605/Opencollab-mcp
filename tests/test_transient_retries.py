"""Retry transient HTTP and transport failures with one shared retry budget."""

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


async def _call_api(api):
    if api == "rest":
        return await github_client.github_get("/test", {"per_page": 2})
    return await github_client.github_graphql(
        "query Test($name: String!) { viewer { login } }", {"name": "test"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["rest", "graphql"])
@pytest.mark.parametrize(
    "error_type",
    [
        httpx.ConnectError,
        httpx.ReadError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
    ],
)
@pytest.mark.parametrize("recovers", [True, False])
async def test_transport_failure_retries_once(monkeypatch, api, error_type, recovers):
    requests, errors, delays = [], [], []
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def handler(request):
        requests.append(request)
        if len(requests) == 1 or not recovers:
            error = error_type("temporary network failure", request=request)
            errors.append(error)
            raise error
        payload = {"ok": True}
        return httpx.Response(200, json={"data": payload} if api == "graphql" else payload)

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        if recovers:
            assert await _call_api(api) == {"ok": True}
            if api == "rest":
                assert await _call_api(api) == {"ok": True}
        else:
            with pytest.raises(error_type) as exc:
                await _call_api(api)
            assert exc.value is errors[-1]
            message = github_client.handle_github_error(exc.value)
            assert (
                "timed out" if issubclass(error_type, httpx.TimeoutException) else "Could not reach"
            ) in message
            assert github_client._cache == {}
    assert len(requests) == 2
    assert requests[0].url == requests[1].url
    assert requests[0].headers == requests[1].headers
    assert requests[0].content == requests[1].content
    assert requests[0].method == ("GET" if api == "rest" else "POST")
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert delays == [github_client.GITHUB_RETRY_DELAY_SECONDS]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["rest", "graphql"])
@pytest.mark.parametrize("transport_first", [True, False])
async def test_transport_and_status_failures_share_retry_budget(monkeypatch, api, transport_first):
    requests, errors, delays = [], [], []

    def handler(request):
        requests.append(request)
        if (len(requests) == 1) == transport_first:
            error = httpx.ConnectError("connection failed", request=request)
            errors.append(error)
            raise error
        return httpx.Response(503)

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        error_type = httpx.HTTPStatusError if transport_first else httpx.ConnectError
        with pytest.raises(error_type) as exc:
            await _call_api(api)
        if transport_first:
            assert exc.value.response.status_code == 503
        else:
            assert exc.value is errors[-1]
    assert len(requests) == 2
    assert delays == [github_client.GITHUB_RETRY_DELAY_SECONDS]
    assert github_client._cache == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["rest", "graphql"])
@pytest.mark.parametrize("during_sleep", [True, False])
async def test_cancellation_is_not_retried(monkeypatch, api, during_sleep):
    requests, delays = [], []
    cancelled = asyncio.CancelledError()

    def handler(request):
        requests.append(request)
        if during_sleep:
            raise httpx.ReadTimeout("timed out", request=request)
        raise cancelled

    async def sleep(delay):
        delays.append(delay)
        raise cancelled

    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        with pytest.raises(asyncio.CancelledError) as exc:
            await _call_api(api)
        assert exc.value is cancelled
    assert len(requests) == 1
    assert delays == ([github_client.GITHUB_RETRY_DELAY_SECONDS] if during_sleep else [])
    assert github_client._cache == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["rest", "graphql"])
async def test_unrelated_request_errors_are_not_retried(monkeypatch, api):
    requests, delays = [], []
    error = ValueError("invalid request")

    def handler(request):
        requests.append(request)
        raise error

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        with pytest.raises(ValueError) as exc:
            await _call_api(api)
        assert exc.value is error
    assert len(requests) == 1
    assert delays == []


@pytest.mark.asyncio
async def test_transport_retry_stays_on_validated_redirect_target(mock_github, monkeypatch):
    requests, delays = [], []
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def old_name(request):
        requests.append(request)
        return httpx.Response(301, headers={"Location": "/repos/new/name?per_page=2"})

    def new_name(request):
        requests.append(request)
        if len(requests) == 2:
            raise httpx.ConnectError("connection failed", request=request)
        return httpx.Response(200, json={"full_name": "new/name"})

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    mock_github({"/repos/old/name": old_name, "/repos/new/name": new_name})
    for _ in range(2):
        assert await github_client.github_get("/repos/old/name", {"per_page": 1}) == {
            "full_name": "new/name"
        }
    assert [request.url.path for request in requests] == [
        "/repos/old/name",
        "/repos/new/name",
        "/repos/new/name",
    ]
    assert requests[1].url == requests[2].url
    assert requests[1].url.params["per_page"] == "2"
    assert all(request.headers["Authorization"] == "Bearer test-token" for request in requests)
    assert delays == [github_client.GITHUB_RETRY_DELAY_SECONDS]
