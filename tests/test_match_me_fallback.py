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
    text = result[0][0].text if isinstance(result, tuple) else result[0].text
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
        "matched_language", "matched_issues",
    }
    assert payload["name"] == "Go Pher"
    assert payload["topics"] == ["cli"]
    assert payload["top_languages"] == [{"name": "Go", "percentage": 100.0}]
