"""Pydantic input models for OpenCollab MCP tools.

`extra="forbid"` rejects unknown fields — important defense against
LLM-generated tool calls passing through stray keys.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# These values are interpolated straight into API paths like
# /repos/{owner}/{repo}, so anything outside GitHub's own character set — a
# '/', '?', '#' or '..' — would silently send the request to a different
# endpoint than the one the tool meant to call.
LOGIN_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9_-]*)$"
REPO_NAME_PATTERN = r"^[A-Za-z0-9._-]+$"


def _reject_dot_segments(value: str) -> str:
    # '.' and '..' match REPO_NAME_PATTERN but are path traversal, not names.
    if value in (".", ".."):
        raise ValueError(f"{value!r} is not a valid repository name")
    return value


class UsernameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(
        ..., description="GitHub username", min_length=1, max_length=39,
        pattern=LOGIN_PATTERN,
    )


class RepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(
        ..., description="Repository owner (e.g. 'facebook')", min_length=1,
        max_length=39, pattern=LOGIN_PATTERN,
    )
    repo: str = Field(
        ..., description="Repository name (e.g. 'react')", min_length=1,
        max_length=100, pattern=REPO_NAME_PATTERN,
    )

    _check_repo = field_validator("repo")(_reject_dot_segments)


class IssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(
        ..., description="Repository owner", min_length=1, max_length=39,
        pattern=LOGIN_PATTERN,
    )
    repo: str = Field(
        ..., description="Repository name", min_length=1, max_length=100,
        pattern=REPO_NAME_PATTERN,
    )
    # Kept as str on purpose — many LLM clients pass numbers as strings,
    # and we run a permissive parser (handles '#123', '123', ' 123 ').
    issue_number: str = Field(
        ...,
        description="Issue number (e.g. '123' or '#123')",
        min_length=1,
    )

    _check_repo = field_validator("repo")(_reject_dot_segments)


class LanguageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    language: str = Field(
        ...,
        description="Programming language (e.g. 'Python', 'TypeScript', 'Rust')",
        min_length=1,
        # The value is wrapped in double quotes in the search query, so a
        # stray '"' would close the quote and inject the rest as qualifiers.
        pattern=r'^[^"]+$',
    )

    difficulty: Literal["beginner", "intermediate"] = Field(
        default="beginner",
        description='beginner searches label:"good first issue"; intermediate searches label:"help wanted"',
    )
