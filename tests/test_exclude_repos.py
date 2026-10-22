"""Repository exclusions follow the existing owner/name input contract."""

import pytest
from pydantic import ValidationError

from opencollab_mcp.models import LanguageInput


@pytest.mark.parametrize("repo", [
    "a/b c", "not-a-repo", "a/b/repo", "/repo", "a/", "a/..", "a/.",
    "a/b\nrepo:c/d", "a/b?x=1", "a /b", "a/ b", "x" * 40 + "/b", "a/" + "x" * 101,
])
def test_invalid_repository_exclusion(repo):
    with pytest.raises(ValidationError):
        LanguageInput(language="Python", exclude_repos=[repo])


def test_repository_exclusion_count_limit():
    assert len(LanguageInput(language="Python", exclude_repos=[f"a/r{i}" for i in range(10)]).exclude_repos) == 10
    with pytest.raises(ValidationError):
        LanguageInput(language="Python", exclude_repos=[f"a/r{i}" for i in range(11)])


def test_repository_exclusion_defaults_are_independent():
    first = LanguageInput(language="Python")
    second = LanguageInput(language="Python")
    first.exclude_repos.append("a/b")
    assert second.exclude_repos == []
