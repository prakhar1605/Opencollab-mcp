"""match_me must not present a guess as a detection.

With no language data on a profile the tool falls back to Python. That is a
reasonable default, but the assistant relaying the results has no way to know
it happened unless the response says so.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from opencollab_mcp.server import build_server
from opencollab_mcp.tools import discovery


@pytest.fixture
def no_search(monkeypatch):
    """Stub the issue search: these tests are about the response envelope."""

    async def _fake_search(endpoint: str, query: str, params: dict[str, Any] | None = None):
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(discovery, "github_search", _fake_search)


@pytest.fixture
def server():
    return build_server()


async def _match_me(server, username: str) -> dict[str, Any]:
    result = server.call_tool("opencollab_match_me", {"params": {"username": username}})
    if hasattr(result, "__await__"):
        result = await result
    text = result.content[0].text
    return json.loads(text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "repos"),
    [
        ("brand-new account", []),
        ("fork-only account", [{"language": None, "size": 10, "topics": []}]),
        ("repos with no language", [{"size": 10, "topics": ["docs"]}]),
    ],
)
async def test_match_me_flags_the_python_fallback(server, no_search, mock_github, label, repos):
    mock_github({"/users/nobody": {"login": "nobody"}, "/users/nobody/repos": repos})

    payload = await _match_me(server, "nobody")

    assert payload["matched_language"] == "Python", label
    assert payload["language_fallback"] is True, label
    assert "note" in payload, f"{label}: the fallback is invisible to the assistant"
    assert "defaulted to Python" in payload["note"]
    assert "opencollab_find_issues" in payload["note"], "the note should say what to do next"


@pytest.mark.asyncio
async def test_match_me_says_nothing_when_a_language_is_detected(server, no_search, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": []}],
    })

    payload = await _match_me(server, "gopher")

    assert payload["matched_language"] == "Go"
    assert "language_fallback" not in payload, "the flag must not appear on the happy path"
    assert "note" not in payload, "no null key on the happy path"


@pytest.mark.asyncio
async def test_match_me_response_shape_is_otherwise_unchanged(server, no_search, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher", "name": "Go Pher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": ["cli"]}],
    })

    payload = await _match_me(server, "gopher")

    assert set(payload) == {
        "username", "name", "top_languages", "topics",
        "matched_language", "matched_issues", "difficulty"
    }
    assert payload["name"] == "Go Pher"
    assert payload["topics"] == ["cli"]
    assert payload["top_languages"] == [{"name": "Go", "percentage": 100.0}]


@pytest.mark.asyncio
async def test_match_me_ignores_forked_repos(server, no_search, mock_github):
    # One big fork of a C++ project must not outweigh the user's own Rust.
    mock_github({
        "/users/rustacean": {"login": "rustacean"},
        "/users/rustacean/repos": [
            {"language": "C++", "size": 500_000, "fork": True, "topics": []},
            {"language": "Rust", "size": 200, "fork": False, "topics": []},
        ],
    })

    payload = await _match_me(server, "rustacean")

    assert payload["matched_language"] == "Rust"
    assert [lang["name"] for lang in payload["top_languages"]] == ["Rust"]


@pytest.mark.asyncio
async def test_match_me_counts_owned_repositories_not_disk_size(
    server, no_search, mock_github, monkeypatch
):
    repos = [
        {"language": "Python", "size": 500_000, "fork": False, "topics": []},
        *[
            {"language": "TypeScript", "size": 100, "fork": False, "topics": []}
            for _ in range(5)
        ],
        {"language": None, "size": 10_000, "fork": False, "topics": []},
        {"language": "C++", "size": 900_000, "fork": True, "topics": []},
    ]
    mock_github({"/users/dev": {"login": "dev"}, "/users/dev/repos": repos})

    calls = {"get": 0, "search": 0}
    original_get = discovery.github_get
    original_search = discovery.github_search

    async def counted_get(*args, **kwargs):
        calls["get"] += 1
        return await original_get(*args, **kwargs)

    async def counted_search(*args, **kwargs):
        calls["search"] += 1
        return await original_search(*args, **kwargs)

    monkeypatch.setattr(discovery, "github_get", counted_get)
    monkeypatch.setattr(discovery, "github_search", counted_search)

    payload = await _match_me(server, "dev")

    assert payload["matched_language"] == "TypeScript"
    assert payload["top_languages"] == [
        {"name": "TypeScript", "percentage": 83.3},
        {"name": "Python", "percentage": 16.7},
    ]
    assert calls == {"get": 2, "search": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("public_repos", [40, 100, 250])
async def test_match_me_discloses_partial_repository_analysis(
    server, no_search, mock_github, monkeypatch, public_repos
):
    returned = min(public_repos, 100)
    # Forks count towards public_repos and the API page size, even though
    # language analysis ignores them.
    repos = [
        {"language": "Python", "fork": i % 2 == 0, "topics": []}
        for i in range(returned)
    ]
    mock_github({
        "/users/dev": {"login": "dev", "public_repos": public_repos},
        "/users/dev/repos": repos,
    })
    calls = []
    original_get = discovery.github_get

    async def counted_get(*args, **kwargs):
        calls.append(args)
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(discovery, "github_get", counted_get)

    payload = await _match_me(server, "dev")

    assert len(calls) == 2, "disclosing truncation must not add pagination requests"
    assert payload["matched_language"] == "Python"
    if public_repos > returned:
        assert payload["repos_analyzed"] == returned
        assert payload["repos_total"] == public_repos
        assert "100" in payload["note"]
        assert "most recently pushed" in payload["note"]
    else:
        assert "repos_analyzed" not in payload
        assert "repos_total" not in payload
        assert "note" not in payload


@pytest.mark.asyncio
async def test_match_me_keeps_both_partial_analysis_and_language_fallback_notes(
    server, no_search, mock_github
):
    mock_github({
        "/users/dev": {"login": "dev", "public_repos": 250},
        "/users/dev/repos": [{"fork": True, "language": "Rust"}] * 100,
    })

    payload = await _match_me(server, "dev")

    assert payload["repos_analyzed"] == 100
    assert payload["repos_total"] == 250
    assert payload["language_fallback"] is True
    assert "most recently pushed" in payload["note"]
    assert "defaulted to Python" in payload["note"]
    assert "opencollab_find_issues" in payload["note"]
