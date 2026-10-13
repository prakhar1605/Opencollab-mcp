"""Both discovery entry points should search only unassigned issues."""

import pytest

from opencollab_mcp.server import build_server
from opencollab_mcp.tools import discovery


@pytest.mark.asyncio
@pytest.mark.parametrize("difficulty", ["beginner", "intermediate"])
@pytest.mark.parametrize("tool, identity", [
    ("opencollab_find_issues", {"language": "Jupyter Notebook"}),
    ("opencollab_match_me", {"username": "example"}),
])
async def test_discovery_excludes_assigned_issues(monkeypatch, mock_github, difficulty, tool, identity):
    queries = []

    async def search(endpoint, query, params=None):
        queries.append(query)
        return {"total_count": 0, "items": []}

    monkeypatch.setattr(discovery, "github_search", search)
    mock_github({
        "/users/example": {"login": "example"},
        "/users/example/repos": [{"language": "Jupyter Notebook"}],
    })
    result = build_server().call_tool(tool, {"params": {**identity, "difficulty": difficulty}})
    if hasattr(result, "__await__"):
        await result
    assert len(queries) == 1
    query = queries[0]
    assert "no:assignee" in query.split()
    assert "is:issue" in query.split()
    assert 'language:"Jupyter Notebook"' in query
    label = "good first issue" if difficulty == "beginner" else "help wanted"
    assert f'label:"{label}"' in query
