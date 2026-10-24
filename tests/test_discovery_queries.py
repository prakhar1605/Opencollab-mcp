"""Tests for the GitHub search queries the discovery tools build.

The queries are the whole product of these tools: a wrong qualifier does not
raise, it just returns the wrong issues. These tests capture the query string
handed to github_search and assert on it directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from opencollab_mcp.helpers import recent_date_str
from opencollab_mcp.server import build_server
from opencollab_mcp.tools import discovery


@pytest.fixture
def captured_queries(monkeypatch) -> list[str]:
    """Record every query string the discovery tools send to GitHub."""
    queries: list[str] = []

    async def _fake_search(endpoint: str, query: str, params: dict[str, Any] | None = None):
        queries.append(query)
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(discovery, "github_search", _fake_search)
    return queries


async def _call(server, name: str, arguments: dict):
    result = server.call_tool(name, arguments)
    if hasattr(result, "__await__"):
        result = await result
    return result


@pytest.fixture
def server():
    return build_server()


# ---- language quoting (#13) ------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language",
    ["Jupyter Notebook", "Vim Script", "Common Lisp", "Emacs Lisp"],
)
async def test_find_issues_quotes_multi_word_language(server, captured_queries, language):
    await _call(server, "opencollab_find_issues", {"params": {"language": language}})

    assert captured_queries, "the tool did not reach github_search"
    assert f'language:"{language}"' in captured_queries[0]


@pytest.mark.asyncio
async def test_find_issues_quotes_single_word_language(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python"}})

    assert 'language:"Python"' in captured_queries[0]


@pytest.mark.asyncio
async def test_find_issues_quotes_multiple_languages(server, captured_queries):
    await _call(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Python, TypeScript"}},
    )

    assert 'language:"Python"' in captured_queries[0]
    assert 'language:"TypeScript"' in captured_queries[0]


@pytest.mark.asyncio
async def test_match_me_quotes_detected_language(server, captured_queries, mock_github):
    mock_github({
        "/users/dataperson": {"login": "dataperson", "name": "Data Person"},
        "/users/dataperson/repos": [
            {"language": "Jupyter Notebook", "size": 900, "topics": ["ml"]},
            {"language": "Python", "size": 100, "topics": []},
        ],
    })

    await _call(server, "opencollab_match_me", {"params": {"username": "dataperson"}})

    assert captured_queries, "the tool did not reach github_search"
    assert 'language:"Jupyter Notebook"' in captured_queries[0]


# ---- is:issue (#11) --------------------------------------------------------

@pytest.mark.asyncio
async def test_find_issues_excludes_pull_requests(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Go"}})

    assert "is:issue" in captured_queries[0].split()


@pytest.mark.asyncio
async def test_match_me_excludes_pull_requests(server, captured_queries, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": []}],
    })

    await _call(server, "opencollab_match_me", {"params": {"username": "gopher"}})

    assert "is:issue" in captured_queries[0].split()


# ---- the rest of the query is unchanged ------------------------------------

@pytest.mark.asyncio
async def test_find_issues_keeps_its_other_qualifiers(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Rust"}})

    query = captured_queries[0]
    assert 'label:"good first issue"' in query
    assert "state:open" in query.split()
    assert "is:public" in query.split()
    assert "created:>" in query


@pytest.mark.asyncio
async def test_find_issues_intermediate_keeps_quoting_and_is_issue(server, captured_queries):
    await _call(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Jupyter Notebook", "difficulty": "intermediate"}},
    )

    query = captured_queries[0]
    assert 'language:"Jupyter Notebook"' in query
    assert 'label:"help wanted"' in query
    assert "is:issue" in query.split()


@pytest.mark.asyncio
async def test_match_me_intermediate_sends_help_wanted(server, captured_queries, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": []}],
    })

    await _call(
        server,
        "opencollab_match_me",
        {"params": {"username": "gopher", "difficulty": "intermediate"}},
    )

    query = captured_queries[0]
    assert 'label:"help wanted"' in query
    assert 'label:"good first issue"' not in query
    assert "is:issue" in query.split()


@pytest.mark.asyncio
async def test_match_me_keeps_its_other_qualifiers(server, captured_queries, mock_github):
    mock_github({
        "/users/rustacean": {"login": "rustacean"},
        "/users/rustacean/repos": [{"language": "Rust", "size": 500, "topics": []}],
    })

    await _call(server, "opencollab_match_me", {"params": {"username": "rustacean"}})

    query = captured_queries[0]
    assert 'label:"good first issue"' in query
    assert "state:open" in query.split()
    assert "is:public" in query.split()
    assert f"created:>{recent_date_str(90)}" in query


# ---- limit (#16) -----------------------------------------------------------

@pytest.fixture
def captured_params(monkeypatch) -> list[dict[str, Any]]:
    """Record the request params the discovery tools send to GitHub search."""
    calls: list[dict[str, Any]] = []

    async def _fake_search(endpoint: str, query: str, params: dict[str, Any] | None = None):
        calls.append(params or {})
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(discovery, "github_search", _fake_search)
    return calls


@pytest.mark.asyncio
async def test_find_issues_defaults_to_15_per_page(server, captured_params):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python"}})

    assert captured_params[0]["per_page"] == 15


@pytest.mark.asyncio
async def test_find_issues_passes_limit_as_per_page(server, captured_params):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python", "limit": 3}})

    assert captured_params[0]["per_page"] == 3


@pytest.mark.asyncio
async def test_match_me_defaults_to_10_per_page(server, captured_params, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": []}],
    })

    await _call(server, "opencollab_match_me", {"params": {"username": "gopher"}})

    assert captured_params[0]["per_page"] == 10


@pytest.mark.asyncio
async def test_match_me_passes_limit_as_per_page(server, captured_params, mock_github):
    mock_github({
        "/users/gopher": {"login": "gopher"},
        "/users/gopher/repos": [{"language": "Go", "size": 500, "topics": []}],
    })

    await _call(server, "opencollab_match_me", {"params": {"username": "gopher", "limit": 5}})

    assert captured_params[0]["per_page"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [None, 1, 365])
async def test_find_issues_uses_requested_age(server, captured_queries, days):
    params = {"language": "Python"}
    if days is not None:
        params["max_age_days"] = days
    expected_since = recent_date_str(days if days is not None else 90)
    await _call(server, "opencollab_find_issues", {"params": params})
    assert len(captured_queries) == 1
    assert f"created:>{expected_since}" in captured_queries[0].split()


# ---- sort (#177) -----------------------------------------------------------

@pytest.mark.asyncio
async def test_find_issues_sort_defaults_to_newest(server, captured_params):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python"}})

    assert len(captured_params) == 1
    assert captured_params[0]["sort"] == "created"
    assert captured_params[0]["order"] == "desc"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sort_value, expected_sort, expected_order",
    [
        ("newest", "created", "desc"),
        ("recently_updated", "updated", "desc"),
        ("least_discussed", "comments", "asc"),
    ],
)
async def test_find_issues_sort_mappings(
    server, captured_params, sort_value, expected_sort, expected_order
):
    await _call(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Python", "sort": sort_value}},
    )

    assert len(captured_params) == 1
    assert captured_params[0]["sort"] == expected_sort
    assert captured_params[0]["order"] == expected_order


# ---- scope (#176) ----------------------------------------------------------

@pytest.mark.asyncio
async def test_find_issues_scope_org(server, captured_queries):
    await _call(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Python", "scope": "huggingface"}},
    )

    assert len(captured_queries) == 1
    assert "org:huggingface" in captured_queries[0].split()
    assert "repo:" not in captured_queries[0]


@pytest.mark.asyncio
async def test_find_issues_scope_repo(server, captured_queries):
    await _call(
        server,
        "opencollab_find_issues",
        {"params": {"language": "Python", "scope": "pandas-dev/pandas"}},
    )

    assert len(captured_queries) == 1
    assert "repo:pandas-dev/pandas" in captured_queries[0].split()
    assert "org:" not in captured_queries[0]


@pytest.mark.asyncio
async def test_find_issues_no_scope_unchanged(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python"}})

    query = captured_queries[0]
    tokens = query.split()
    assert not any(t.startswith("org:") or t.startswith("repo:") for t in tokens)
    assert 'language:"Python"' in query
    assert 'label:"good first issue"' in query
    assert "state:open" in tokens
    assert "no:assignee" in tokens
    assert "is:issue" in tokens
    assert "is:public" in tokens
    assert "archived:false" in tokens

@pytest.mark.asyncio
async def test_find_issues_excludes_requested_repositories(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {
        "language": "Python", "exclude_repos": ["a/b", "example-org/repo.name"],
    }})
    assert captured_queries
    assert "-repo:a/b" in captured_queries[0].split()
    assert "-repo:example-org/repo.name" in captured_queries[0].split()
    assert "no:assignee" in captured_queries[0].split()


@pytest.mark.asyncio
async def test_empty_repository_exclusions_preserve_query(server, captured_queries):
    await _call(server, "opencollab_find_issues", {"params": {"language": "Python"}})
    await _call(server, "opencollab_find_issues", {"params": {
        "language": "Python", "exclude_repos": [],
    }})
    assert len(captured_queries) == 2
    assert captured_queries[0] == captured_queries[1]
