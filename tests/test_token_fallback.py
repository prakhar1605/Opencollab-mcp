"""Token precedence is explicit, with no dependence on the developer's env."""

import pytest

from opencollab_mcp.github_client import _get_headers, has_github_token


@pytest.mark.parametrize("github_token, gh_token, expected", [
    (None, "cli-token", "cli-token"),
    ("primary-token", "cli-token", "primary-token"),
    ("", "cli-token", "cli-token"),
    (" \n", " cli-token\n", "cli-token"),
    (" primary-token\n", None, "primary-token"),
    (None, None, None),
    ("", " \n", None),
])
def test_token_precedence(monkeypatch, github_token, gh_token, expected):
    for name, value in (("GITHUB_TOKEN", github_token), ("GH_TOKEN", gh_token)):
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    headers = _get_headers()
    if expected is None:
        assert "Authorization" not in headers
        assert has_github_token() is False
    else:
        assert headers["Authorization"] == f"Bearer {expected}"
        assert has_github_token() is True
