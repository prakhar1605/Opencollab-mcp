"""Tests for the python -m opencollab_mcp entry point."""

import subprocess
import sys
from importlib.metadata import version


def test_module_entry_point_displays_version():
    expected_version = version("opencollab-mcp")

    result = subprocess.run(
        [sys.executable, "-m", "opencollab_mcp", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert expected_version in result.stdout + result.stderr
