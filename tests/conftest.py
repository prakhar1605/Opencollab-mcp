"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from opencollab_mcp import github_client


@pytest.fixture(autouse=True)
def _reset_client_state():
    """Every test gets a clean cache and a fresh HTTP client.

    Resetting the client matters as much as the cache: it is shared and
    lazily created, so without this a test could reuse a client built by an
    earlier test — one that was not built through this test's mock transport.
    """
    github_client.clear_cache()
    github_client.reset_client()
    yield
    github_client.clear_cache()
    github_client.reset_client()


@pytest.fixture
def mock_github(monkeypatch) -> Callable[[dict[str, Any]], None]:
    """Install a mock GitHub responder.

    Pass a dict mapping `path` (the part after https://api.github.com) to
    either a JSON-able value or a (status, value) tuple. Query strings are
    stripped before matching, so '/users/foo' matches both '/users/foo'
    and '/users/foo?per_page=10'.
    """

    routes: dict[str, Any] = {}

    def _install(new_routes: dict[str, Any]) -> None:
        routes.update(new_routes)

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path not in routes:
            return httpx.Response(404, json={"message": "Not Found (mock)"})
        spec = routes[path]
        if isinstance(spec, tuple):
            status, body = spec
        else:
            status, body = 200, spec
        if isinstance(body, dict | list):
            return httpx.Response(status, json=body)
        return httpx.Response(status, content=body)

    transport = httpx.MockTransport(_handler)

    # Patch the AsyncClient constructor so github_get uses our transport.
    real_async_client = httpx.AsyncClient

    def _patched(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _patched)
    return _install
