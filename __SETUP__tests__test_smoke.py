"""Smoke tests — make sure the package imports and tools register."""
from __future__ import annotations


def test_import():
    import opencollab_mcp
    assert opencollab_mcp.__version__


def test_server_imports():
    from opencollab_mcp import server
    assert server.mcp is not None
    assert server.mcp.name == "opencollab_mcp"


def test_main_callable():
    from opencollab_mcp.server import main
    assert callable(main)


def test_helpers_pure():
    """Pure helpers should work without any network."""
    from opencollab_mcp.server import (
        _truncate, _parse_issue_number, _sanitize_language, _score_complexity,
    )

    assert _truncate("hello world", 5) == "hello…"
    assert _truncate("hi", 100) == "hi"
    assert _truncate(None) == ""

    assert _parse_issue_number("123") == 123
    assert _parse_issue_number("#123") == 123
    assert _parse_issue_number("  #42  ") == 42

    assert _sanitize_language("Python") == "Python"
    assert _sanitize_language("C++") == "C++"
    assert _sanitize_language("C#") == "C#"
    assert _sanitize_language("Python; rm -rf /") == "Python rm -rf "

    issue = {
        "body": "Fix the typo in README",
        "comments": 1,
        "labels": [{"name": "good first issue"}, {"name": "documentation"}],
    }
    score = _score_complexity(issue)
    assert 1 <= score["complexity_score"] <= 10
    assert score["signals"]["has_beginner_label"] is True


def test_input_models():
    """Pydantic input models should validate correctly."""
    from opencollab_mcp.server import (
        UsernameInput, RepoInput, IssueInput, OpportunityInput,
    )

    UsernameInput(username="octocat")
    RepoInput(owner="facebook", repo="react")
    IssueInput(owner="facebook", repo="react", issue_number="123")
    OpportunityInput(language="Python", mode="weekend")


def test_score_health_shape():
    """_score_health should return the expected keys regardless of input."""
    from opencollab_mcp.server import _score_health

    bundle = {
        "repo": {"pushed_at": "2026-04-01T00:00:00Z", "stargazers_count": 500,
                 "open_issues_count": 10, "forks_count": 50, "topics": ["x"]},
        "pulls": [{"merged_at": "2026-04-15T00:00:00Z"}, {"merged_at": None}],
        "community": {"files": {"contributing": {}, "license": {}, "readme": {}}},
    }
    result = _score_health(bundle)
    assert "health_score" in result
    assert 0 <= result["health_score"] <= 100
    assert "verdict" in result
    assert "details" in result
