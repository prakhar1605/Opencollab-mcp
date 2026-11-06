"""GET redirects must stay on the configured API origin before sending auth."""

import asyncio
import json

import httpx
import pytest

from opencollab_mcp import github_client
from opencollab_mcp.server import build_server


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_renamed_repository_redirect(mock_github, monkeypatch, status):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    requests = []

    def old_name(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://api.github.com/repositories/123"})

    def renamed(request):
        requests.append(request)
        return httpx.Response(200, json={"full_name": "new/name"})

    mock_github({"/repos/old/name": old_name, "/repositories/123": renamed})
    assert await github_client.github_get("/repos/old/name") == {"full_name": "new/name"}
    assert [r.url.path for r in requests] == ["/repos/old/name", "/repositories/123"]
    assert all(r.headers["Authorization"] == "Bearer test-token" for r in requests)
    assert all(r.method == "GET" for r in requests)


@pytest.mark.asyncio
async def test_relative_redirect_and_cache(mock_github):
    requests = []

    def old_name(request):
        requests.append(request)
        return httpx.Response(301, headers={"Location": "../../repositories/123?per_page=2"})

    def renamed(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id": 1}])

    mock_github({"/repos/old/name": old_name, "/repositories/123": renamed})
    for _ in range(2):
        assert await github_client.github_get("/repos/old/name", {"per_page": 1}) == [{"id": 1}]
    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["per_page"] == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["https://attacker.example/data", "http://api.github.com/data"])
@pytest.mark.parametrize("auto_follow", [False, True])
async def test_redirect_refuses_untrusted_origin_before_request(
    mock_github, monkeypatch, target, auto_follow,
):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(301, headers={"Location": target})

    mock_github({"/repos/old/name": redirect, "/data": redirect})
    async with httpx.AsyncClient(follow_redirects=auto_follow) as client:
        monkeypatch.setattr(github_client, "_get_client", lambda: client)
        with pytest.raises(ValueError, match="untrusted"):
            await github_client.github_get("/repos/old/name")
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.github.com/repos/old/name"


@pytest.mark.asyncio
async def test_redirect_loop_is_bounded(mock_github, monkeypatch):
    monkeypatch.setattr(github_client, "GITHUB_MAX_REDIRECTS", 2, raising=False)
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(301, headers={"Location": str(request.url)})

    mock_github({"/loop": redirect})
    with pytest.raises(httpx.TooManyRedirects):
        await github_client.github_get("/loop")
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_redirect_without_location_stays_an_http_error(mock_github):
    mock_github({"/missing": (301, {})})
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await github_client.github_get("/missing")
    assert exc.value.response.status_code == 301


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [502, 503, 504])
async def test_redirect_target_retains_transient_retry(mock_github, monkeypatch, status):
    attempts, delays = [], []

    def renamed(request):
        attempts.append(request)
        return httpx.Response(status if len(attempts) == 1 else 200, json={"id": 123})

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    mock_github({
        "/old": lambda request: httpx.Response(301, headers={"Location": "/repositories/123"}),
        "/repositories/123": renamed,
    })
    assert await github_client.github_get("/old") == {"id": 123}
    assert len(attempts) == 2
    assert attempts[0].url == attempts[1].url
    assert len(delays) == 1


@pytest.mark.asyncio
async def test_pagination_uses_redirected_response_links(mock_github):
    def items(request):
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[1], headers={
                "Link": '<https://api.github.com/repositories/123/items?page=2>; rel="next"',
            })
        return httpx.Response(200, json=[2])

    mock_github({
        "/old/items": lambda request: httpx.Response(301, headers={
            "Location": "/repositories/123/items?page=1",
        }),
        "/repositories/123/items": items,
    })
    assert await github_client.github_get_all("/old/items") == ([1, 2], False)


@pytest.mark.asyncio
async def test_impact_tool_accepts_renamed_repository(mock_github):
    mock_github({
        "/repos/old/name": lambda request: httpx.Response(301, headers={
            "Location": "/repositories/123",
        }),
        "/repositories/123": {"stargazers_count": 5, "forks_count": 0, "topics": []},
    })
    result = await build_server().call_tool(
        "opencollab_impact_estimator", {"params": {"owner": "old", "repo": "name"}},
    )
    assert not result.is_error
    assert json.loads(result.content[0].text)["impact_tier"] == "LOW"
