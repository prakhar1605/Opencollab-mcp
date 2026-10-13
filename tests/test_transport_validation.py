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
