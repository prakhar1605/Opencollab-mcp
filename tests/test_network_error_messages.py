"""Actionable messages for network failures without leaking raw diagnostics."""

import httpx
import pytest

from opencollab_mcp.github_client import handle_github_error


@pytest.mark.parametrize("error_type", [
    httpx.ConnectError, httpx.ProxyError, httpx.ReadError, httpx.RemoteProtocolError,
])
def test_network_failure_has_connection_guidance(error_type):
    result = handle_github_error(error_type("synthetic internal network detail"))
    assert result == (
        "Error: Could not reach api.github.com. "
        "Check your internet connection or proxy settings and try again."
    )
    assert "synthetic internal network detail" not in result


@pytest.mark.parametrize("error_type", [
    httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout,
])
def test_timeout_keeps_specific_message(error_type):
    assert handle_github_error(error_type("timeout")) == (
        "Error: GitHub API request timed out. Please try again."
    )


def test_unexpected_errors_keep_generic_diagnostic():
    assert handle_github_error(RuntimeError("boom")) == "Error: Unexpected failure — RuntimeError: boom"
