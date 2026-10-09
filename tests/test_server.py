"""Tests for MCPServer transport selection and network binding arguments."""

from __future__ import annotations

import logging
import sys

import pytest

from opencollab_mcp import server
from opencollab_mcp.constants import __version__


def _run_main_with(monkeypatch, env: dict[str, str], argv: list[str] | None = None):
    """Run server.main() with a patched mcp.run, returning the calls it made."""
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["opencollab-mcp"])
    for key in ("TRANSPORT", "PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    server.main(argv)
    return calls


def test_stdio_is_default(monkeypatch):
    calls = _run_main_with(monkeypatch, {})
    assert calls == [((), {})]


@pytest.mark.parametrize("argv", [["--port", "9000"], ["--transport", "sse"]])
def test_unknown_arguments_warn_without_stopping_stdio(monkeypatch, caplog, capsys, argv):
    with caplog.at_level(logging.WARNING, logger="opencollab_mcp"):
        calls = _run_main_with(monkeypatch, {}, argv)
    assert calls == [((), {})]
    assert f"Ignoring unknown arguments: {' '.join(argv)}" in caplog.text
    assert "TRANSPORT, PORT" in caplog.text
    assert capsys.readouterr().out == ""


def test_no_unknown_arguments_does_not_warn(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="opencollab_mcp"):
        _run_main_with(monkeypatch, {}, [])
    assert "Ignoring unknown arguments" not in caplog.text


def test_streamable_http_passes_network_settings_to_run(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "streamable-http", "PORT": "9001"})
    assert calls == [((), {"transport": "streamable-http", "host": "0.0.0.0", "port": 9001})]


def test_sse_passes_network_settings_to_run(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "sse"})
    assert calls == [((), {"transport": "sse", "host": "0.0.0.0", "port": 8000})]


@pytest.mark.parametrize("port", ["abc", "8000/tcp", "0", "65536"])
def test_invalid_port_exits_cleanly(monkeypatch, capsys, port):
    with pytest.raises(SystemExit) as excinfo:
        _run_main_with(monkeypatch, {"TRANSPORT": "streamable-http", "PORT": port})
    assert excinfo.value.code == (
        f"Error: PORT must be a number between 1 and 65535, got {port!r}"
    )
    assert capsys.readouterr().out == ""


def test_unknown_log_level_warns_and_uses_info(monkeypatch, caplog):
    levels = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: levels.append(kw["level"]))
    monkeypatch.setenv("OPENCOLLAB_LOG_LEVEL", "DEBUGG")
    with caplog.at_level(logging.WARNING, logger="opencollab_mcp"):
        _run_main_with(monkeypatch, {})
    assert levels == [logging.INFO]
    assert "Unknown OPENCOLLAB_LOG_LEVEL 'DEBUGG'" in caplog.text
    assert "DEBUG, INFO, WARNING, ERROR, CRITICAL" in caplog.text


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
