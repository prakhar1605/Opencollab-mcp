"""Tests for MCP tool registration and safety annotations."""

import pytest

from opencollab_mcp.server import build_server

EXPECTED_TOOLS = {
    "opencollab_find_issues",
    "opencollab_match_me",
    "opencollab_repo_health",
    "opencollab_impact_estimator",
    "opencollab_check_issue_availability",
    "opencollab_generate_pr_plan",
}


@pytest.mark.asyncio
async def test_all_tools_are_registered_with_read_only_annotations():
    server = build_server()
    tools = await server.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) == EXPECTED_TOOLS

    for tool in tools_by_name.values():
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
