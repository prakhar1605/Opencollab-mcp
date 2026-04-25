"""Tests for the input models — Pydantic validation logic, no API calls."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencollab_mcp.models import (
    UsernameInput,
    RepoInput,
    IssueInput,
    LanguageInput,
    CompareInput,
)


def test_username_strips_whitespace():
    m = UsernameInput(username="  octocat  ")
    assert m.username == "octocat"


def test_username_rejects_empty():
    with pytest.raises(ValidationError):
        UsernameInput(username="")


def test_username_rejects_too_long():
    with pytest.raises(ValidationError):
        UsernameInput(username="a" * 40)


def test_username_rejects_extra_fields():
    with pytest.raises(ValidationError):
        UsernameInput(username="octocat", extra_field="bad")


def test_repo_input_requires_both():
    with pytest.raises(ValidationError):
        RepoInput(owner="facebook")  # missing repo


def test_repo_input_strips_whitespace():
    m = RepoInput(owner=" facebook ", repo=" react ")
    assert m.owner == "facebook"
    assert m.repo == "react"


def test_issue_input_accepts_string_number():
    # We accept strings on purpose — many LLM clients pass numbers as strings.
    m = IssueInput(owner="x", repo="y", issue_number="123")
    assert m.issue_number == "123"


def test_issue_input_accepts_hashed_number():
    m = IssueInput(owner="x", repo="y", issue_number="#456")
    assert m.issue_number == "#456"


def test_language_input_required():
    with pytest.raises(ValidationError):
        LanguageInput()  # type: ignore


def test_compare_input_all_four_required():
    with pytest.raises(ValidationError):
        CompareInput(owner_a="a", repo_a="b", owner_b="c")  # type: ignore


def test_compare_input_strips_all():
    m = CompareInput(
        owner_a=" a ", repo_a=" b ", owner_b=" c ", repo_b=" d ",
    )
    assert (m.owner_a, m.repo_a, m.owner_b, m.repo_b) == ("a", "b", "c", "d")
