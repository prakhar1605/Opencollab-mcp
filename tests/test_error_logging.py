"""Expected client errors should not hide real server failures in the logs."""

import logging

import httpx
import pytest

from opencollab_mcp.github_client import handle_github_error


def status_error(code):
    request = httpx.Request("GET", "https://api.github.com/repos/o/r")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("synthetic status error", request=request, response=response)


@pytest.mark.parametrize("code", [400, 401, 403, 404, 422, 429, 499])
@pytest.mark.parametrize("active_exception", [False, True])
def test_client_errors_warn_without_traceback(caplog, code, active_exception):
    error = status_error(code)
    with caplog.at_level(logging.WARNING, logger="opencollab_mcp.github"):
        if active_exception:
            try:
                raise error
            except httpx.HTTPStatusError as caught:
                handle_github_error(caught)
        else:
            handle_github_error(error)
    records = [r for r in caplog.records if r.name == "opencollab_mcp.github"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is None
    assert str(code) in records[0].getMessage()
    assert "NoneType: None" not in caplog.text


@pytest.mark.parametrize("error", [RuntimeError("boom"), status_error(503)])
def test_unexpected_errors_keep_the_actual_traceback(caplog, error):
    try:
        raise error
    except Exception as caught:
        saved = caught
    # Handle it after leaving the except block, as callers/tests may do.
    with caplog.at_level(logging.ERROR, logger="opencollab_mcp.github"):
        handle_github_error(saved)
    record = next(r for r in caplog.records if r.name == "opencollab_mcp.github")
    assert record.levelno == logging.ERROR
    assert record.exc_info == (type(saved), saved, saved.__traceback__)
    assert record.exc_info[2] is not None
