"""Tests for the GitHub search queries the discovery tools build.

The queries are the whole product of these tools: a wrong qualifier does not
raise, it just returns the wrong issues. These tests capture the query string
handed to github_search and assert on it directly.
"""

from __future__ import annotations

from typing import Any

import pytest

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
    assert "created:>" in query
