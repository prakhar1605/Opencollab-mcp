"""Tests for the input models — Pydantic validation logic, no API calls."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencollab_mcp.models import (
    IssueInput,
    LanguageInput,
    RepoInput,
    UsernameInput,
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


@pytest.mark.parametrize("bad", ["octo/cat", "octo?x=1", "-octocat", "octo cat", "../x"])
def test_username_rejects_path_characters(bad):
    with pytest.raises(ValidationError):
        UsernameInput(username=bad)


@pytest.mark.parametrize("owner, repo", [
    ("facebook", "react/issues"),
    ("facebook", ".."),
    ("facebook", "."),
    ("face/book", "react"),
    ("facebook", "react?x=1"),
    ("facebook", "react#frag"),
])
def test_repo_input_rejects_path_characters(owner, repo):
    with pytest.raises(ValidationError):
        RepoInput(owner=owner, repo=repo)
    with pytest.raises(ValidationError):
        IssueInput(owner=owner, repo=repo, issue_number="1")


@pytest.mark.parametrize("repo", ["react", "vscode-python", "next.js", "my_repo", ".github"])
def test_repo_input_accepts_real_names(repo):
    assert RepoInput(owner="some-org", repo=repo).repo == repo


def test_language_rejects_double_quote():
    with pytest.raises(ValidationError):
        LanguageInput(language='Python" label:"bug')


@pytest.mark.parametrize("lang", ["C++", "C#", "Jupyter Notebook", "F*"])
def test_language_accepts_real_names(lang):
    assert LanguageInput(language=lang).language == lang


def test_language_input_limit_defaults_to_15():
    assert LanguageInput(language="Python").limit == 15


@pytest.mark.parametrize("limit", [1, 30])
def test_language_input_accepts_limit_bounds(limit):
    assert LanguageInput(language="Python", limit=limit).limit == limit


@pytest.mark.parametrize("limit", [0, -1, 31])
def test_language_input_rejects_out_of_range_limit(limit):
    with pytest.raises(ValidationError):
        LanguageInput(language="Python", limit=limit)
