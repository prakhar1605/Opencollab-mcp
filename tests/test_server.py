"""Tests for the server entry point's transport selection.

FastMCP.run() only accepts `transport` (and `mount_path`) — host/port must go
through mcp.settings. These tests guard against regressing to run(host=, port=),
which raises TypeError at startup and would break every remote deployment.
"""

from __future__ import annotations

from opencollab_mcp import server


def _run_main_with(monkeypatch, env: dict[str, str]):
    """Run server.main() with a patched mcp.run, returning the calls it made."""
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    for key in ("TRANSPORT", "PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    server.main()
    return calls


def test_stdio_is_default(monkeypatch):
    calls = _run_main_with(monkeypatch, {})
    assert calls == [((), {})]


def test_streamable_http_configures_settings(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "streamable-http", "PORT": "9001"})
    assert calls == [((), {"transport": "streamable-http"})]
    assert server.mcp.settings.host == "0.0.0.0"
    assert server.mcp.settings.port == 9001


def test_sse_configures_settings(monkeypatch):
    calls = _run_main_with(monkeypatch, {"TRANSPORT": "sse"})
    assert calls == [((), {"transport": "sse"})]
    assert server.mcp.settings.host == "0.0.0.0"
    assert server.mcp.settings.port == 8000
