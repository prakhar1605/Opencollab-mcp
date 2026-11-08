"""Reject transport typos before starting any server."""

import pytest

from opencollab_mcp import server


@pytest.mark.parametrize("transport", ["htttp", "streamable_http", "", " stdio "])
def test_invalid_transport_never_starts_server(monkeypatch, transport):
    calls = []
    monkeypatch.setenv("TRANSPORT", transport)
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(SystemExit) as exc:
        server.main([])
    assert str(exc.value) == (
        "Error: TRANSPORT must be one of stdio, streamable-http, http, sse; "
        f"got {transport!r}"
    )
    assert calls == []


@pytest.mark.parametrize("transport, expected", [
    ("STDIO", {}),
    ("STREAMABLE-HTTP", {"transport": "streamable-http", "host": "0.0.0.0", "port": 8000}),
    ("HTTP", {"transport": "streamable-http", "host": "0.0.0.0", "port": 8000}),
    ("SSE", {"transport": "sse", "host": "0.0.0.0", "port": 8000}),
])
def test_transport_names_remain_case_insensitive(monkeypatch, transport, expected):
    calls = []
    monkeypatch.setenv("TRANSPORT", transport)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    server.main([])
    assert calls == [expected]


def test_transport_flag_beats_invalid_env_value(monkeypatch):
    """A --transport flag wins even when TRANSPORT is set to garbage."""
    calls = []
    monkeypatch.setenv("TRANSPORT", "htttp")
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    server.main(["--transport", "stdio"])
    assert calls == [{}]


def test_port_flag_beats_env_value(monkeypatch):
    calls = []
    monkeypatch.setenv("TRANSPORT", "streamable-http")
    monkeypatch.setenv("PORT", "8000")
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    server.main(["--port", "9000"])
    assert calls == [{"transport": "streamable-http", "host": "0.0.0.0", "port": 9000}]


@pytest.mark.parametrize("port", ["abc", "0", "65536"])
def test_invalid_port_flag_exits_like_env_port(monkeypatch, port):
    monkeypatch.setenv("TRANSPORT", "streamable-http")
    monkeypatch.setenv("PORT", "8000")
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: None)
    with pytest.raises(SystemExit) as exc:
        server.main(["--port", port])
    assert str(exc.value) == (
        f"Error: PORT must be a number between 1 and 65535, got {port!r}"
    )
