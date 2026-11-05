"""Tests for the `opencollab-mcp --check` self-check flag.

Uses MockTransport (via the `mock_github` fixture); no live API is used.
The token value must never appear in the output.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from opencollab_mcp import server

TOKEN = "synthetic-token-must-not-appear"
RESET_EPOCH = 1790000000
RESET_TEXT = datetime.fromtimestamp(RESET_EPOCH, tz=timezone.utc).strftime(
    "%Y-%m-%d %H:%M UTC"
)

RATE_LIMIT_OK = {
    "resources": {
        "core": {"limit": 5000, "remaining": 4999, "reset": RESET_EPOCH},
        "search": {"limit": 30, "remaining": 29, "reset": RESET_EPOCH},
        "graphql": {"limit": 5000, "remaining": 4998, "reset": RESET_EPOCH},
    },
}


def _user_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"login": "octocat"},
        headers={"x-oauth-scopes": "public_repo, read:user"},
    )


def _must_not_be_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url.path}")


def _run_check(monkeypatch, capsys, env: dict[str, str]):
    """Run server.main(["--check"]) and return (exit code, stdout, run calls)."""
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    for key in ("TRANSPORT", "PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(SystemExit) as excinfo:
        server.main(["--check"])
    return excinfo.value.code, capsys.readouterr().out, calls


def test_check_valid_token_reports_login_scopes_and_limits(
    monkeypatch, capsys, mock_github
):
    mock_github({"/user": _user_response, "/rate_limit": RATE_LIMIT_OK})
    code, out, calls = _run_check(monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN})
    assert code == 0
    assert calls == []
    assert "Token: GITHUB_TOKEN is set" in out
    assert "Authenticated as: octocat" in out
    assert "Scopes: public_repo, read:user" in out
    assert "Rate limit core: 4999 remaining" in out
    assert "Rate limit search: 29 remaining" in out
    assert "Rate limit graphql: 4998 remaining" in out
    assert RESET_TEXT in out
    assert "Check passed" in out
    assert TOKEN not in out


def test_check_prefers_github_token_over_gh_token(monkeypatch, capsys, mock_github):
    mock_github({"/user": _user_response, "/rate_limit": RATE_LIMIT_OK})
    code, out, _ = _run_check(
        monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN, "GH_TOKEN": "other-token"}
    )
    assert code == 0
    assert "Token: GITHUB_TOKEN is set" in out
    assert TOKEN not in out
    assert "other-token" not in out


def test_check_falls_back_to_gh_token(monkeypatch, capsys, mock_github):
    mock_github({"/user": _user_response, "/rate_limit": RATE_LIMIT_OK})
    code, out, _ = _run_check(monkeypatch, capsys, {"GH_TOKEN": TOKEN})
    assert code == 0
    assert "Token: GH_TOKEN is set" in out
    assert TOKEN not in out


def test_check_fine_grained_token_reports_no_scopes_header(
    monkeypatch, capsys, mock_github
):
    mock_github({
        "/user": lambda r: httpx.Response(200, json={"login": "octocat"}),
        "/rate_limit": RATE_LIMIT_OK,
    })
    code, out, _ = _run_check(monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN})
    assert code == 0
    assert "Scopes: not reported (fine-grained token" in out
    assert TOKEN not in out


def test_check_bad_credentials_exits_nonzero(monkeypatch, capsys, mock_github):
    mock_github({
        "/user": (401, {"message": "Bad credentials"}),
        "/rate_limit": _must_not_be_called,
    })
    code, out, calls = _run_check(monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN})
    assert code == 1
    assert calls == []
    assert "authentication failed" in out.lower()
    assert "Bad credentials" not in out
    assert TOKEN not in out


def test_check_network_error_exits_nonzero(monkeypatch, capsys, mock_github):
    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic network detail", request=request)

    mock_github({"/user": _raise, "/rate_limit": _must_not_be_called})
    code, out, calls = _run_check(monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN})
    assert code == 1
    assert calls == []
    assert "Could not reach api.github.com" in out
    assert "synthetic network detail" not in out
    assert TOKEN not in out


def test_check_no_token_still_reports_rate_limit_but_exits_nonzero(
    monkeypatch, capsys, mock_github
):
    mock_github({"/user": _must_not_be_called, "/rate_limit": RATE_LIMIT_OK})
    code, out, calls = _run_check(monkeypatch, capsys, {})
    assert code == 1
    assert calls == []
    assert "no GITHUB_TOKEN or GH_TOKEN set" in out
    assert "Rate limit core: 4999 remaining" in out
    assert "No token set" in out


def test_check_exhausted_core_limit_exits_nonzero(
    monkeypatch, capsys, mock_github
):
    exhausted = {
        "resources": {
            "core": {"limit": 5000, "remaining": 0, "reset": RESET_EPOCH},
            "search": {"limit": 30, "remaining": 29, "reset": RESET_EPOCH},
            "graphql": {"limit": 5000, "remaining": 4998, "reset": RESET_EPOCH},
        },
    }
    mock_github({"/user": _user_response, "/rate_limit": exhausted})
    code, out, _ = _run_check(monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN})
    assert code == 1
    assert "Rate limit exhausted" in out
    assert TOKEN not in out


def test_check_runs_before_transport_validation(monkeypatch, capsys, mock_github):
    mock_github({"/user": _user_response, "/rate_limit": RATE_LIMIT_OK})
    code, out, calls = _run_check(
        monkeypatch, capsys, {"GITHUB_TOKEN": TOKEN, "TRANSPORT": "bogus"}
    )
    assert code == 0
    assert calls == []
    assert "Check passed" in out
    assert TOKEN not in out
