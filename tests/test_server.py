"""Tests for MCPServer transport selection and network binding arguments."""

from __future__ import annotations

import sys

import pytest

from opencollab_mcp import server
from opencollab_mcp.constants import __version__


def _run_main_with(monkeypatch, env: dict[str, str]):
    """Run server.main() with a patched mcp.run, returning the calls it made."""
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["opencollab-mcp"])
    for key in ("TRANSPORT", "PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    server.main()
    return calls


def test_stdio_is_default(monkeypatch):
    calls = _run_main_with(monkeypatch, {})
    assert calls == [((), {})]


def test_streamable_http_passes_network_settings_to_run(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "streamable-http", "PORT": "9001"})
    assert calls == [((), {"transport": "streamable-http", "host": "0.0.0.0", "port": 9001})]


def test_sse_passes_network_settings_to_run(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "sse"})
    assert calls == [((), {"transport": "sse", "host": "0.0.0.0", "port": 8000})]


def test_version_flag_prints_version_and_exits(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["opencollab-mcp", "--version"])

    with pytest.raises(SystemExit) as exc_info:
        server.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert __version__ in output
    assert "opencollab-mcp" in output
    assert len(calls) == 0


def test_version_short_flag_prints_version_and_exits(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["opencollab-mcp", "-V"])

    with pytest.raises(SystemExit) as exc_info:
        server.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert __version__ in output
    assert "opencollab-mcp" in output
    assert len(calls) == 0
