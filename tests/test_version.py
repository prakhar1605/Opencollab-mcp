"""The package version has one home: pyproject.toml.

These tests exist because it previously had three, and they had already
drifted — every request advertised opencollab-mcp/0.6.0 while the package was
0.6.1, and nothing failed.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import httpx
import pytest

import opencollab_mcp
from opencollab_mcp import constants, github_client

SRC = Path(opencollab_mcp.__file__).resolve().parent


def test_dunder_version_matches_distribution_metadata():
    assert opencollab_mcp.__version__ == version("opencollab-mcp")


def test_user_agent_is_derived_from_the_version():
    assert constants.USER_AGENT == f"opencollab-mcp/{opencollab_mcp.__version__}"


def test_no_hardcoded_version_literal_in_the_package():
    # The regression this guards: a second copy of the number, free to drift
    # from pyproject.toml the way USER_AGENT did.
    current = version("opencollab-mcp")
    offenders = [
        f"{path.relative_to(SRC)}:{lineno}: {line.strip()}"
        for path in SRC.rglob("*.py")
        for lineno, line in enumerate(path.read_text().splitlines(), start=1)
        if current in line and not line.lstrip().startswith("#")
    ]

    assert not offenders, (
        f"the version {current!r} is written down inside the package; "
        "pyproject.toml is the only place it belongs:\n" + "\n".join(offenders)
    )


@pytest.mark.asyncio
async def test_requests_advertise_the_current_version(monkeypatch):
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(_handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, **{**kw, "transport": transport}),
    )

    await github_client.github_get("/rate_limit", use_cache=False)

    assert seen == [f"opencollab-mcp/{version('opencollab-mcp')}"]
