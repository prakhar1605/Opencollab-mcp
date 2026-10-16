"""Pydantic models for OpenCollab MCP tools.

Input models use `extra="forbid"` to reject unknown fields — important defense
against LLM-generated tool calls passing through stray keys.

Output models (e.g. `ImpactEstimate`) describe a tool's structured result. The
MCP SDK publishes their JSON schema as the tool's `outputSchema`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import RECENT_ISSUES_DAYS

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


class MatchMeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username", min_length=1, max_length=39, pattern=LOGIN_PATTERN,)
    difficulty: Literal["beginner", "intermediate"] = Field(
        default="beginner",
        description='beginner searches label:"good first issue"; intermediate searches label:"help wanted"',
    )
    limit: int = Field(
        default=10,
        description="Max number of issues to return (1-30)",
        ge=1,
        le=30,
    )


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
    # Normalize JSON integers to the string parser's existing input format.
    issue_number: str = Field(
        ...,
        description="Issue number (e.g. 123, '123' or '#123')",
        min_length=1,
    )

    _check_repo = field_validator("repo")(_reject_dot_segments)

    @field_validator("issue_number", mode="before")
    @classmethod
    def normalize_issue_number(cls, value: object) -> object:
        return str(value) if type(value) is int else value


class LanguageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    language: str = Field(
        ...,
        description="Programming language(s), comma-separated (up to 3; e.g. 'Python, TypeScript')",
        min_length=1,
        max_length=50,
        # The value is wrapped in double quotes in the search query, so a
        # stray '"' would close the quote and inject the rest as qualifiers.
        pattern=r'^[^"]+$',
    )

    @field_validator("language")
    @classmethod
    def validate_language_count(cls, value: str) -> str:
        languages = [language.strip() for language in value.split(",")]
        if len(languages) > 3:
            raise ValueError("at most 3 languages may be provided")
        if any(not language for language in languages):
            raise ValueError("languages must not be empty")
        return value

    difficulty: Literal["beginner", "intermediate"] = Field(
        default="beginner",
        description='beginner searches label:"good first issue"; intermediate searches label:"help wanted"',
    )

    limit: int = Field(
        default=15,
        description="Max number of issues to return (1-30)",
        ge=1,
        le=30,
    )

    max_age_days: int = Field(
        default=RECENT_ISSUES_DAYS,
        description="Search issues created within this many days (1-365; default 90)",
        ge=1,
        le=365,
    )


class ImpactEstimate(BaseModel):
    """Structured result of `opencollab_impact_estimator`."""

    repo: str = Field(..., description="Repository as 'owner/name'")
    archived: bool = Field(..., description="True if the repository is archived (read-only)")
    impact_tier: Literal["LOW", "MODERATE", "MEDIUM", "HIGH", "MASSIVE"] = Field(
        ..., description="Impact tier derived from the star count",
    )
    estimated_reach: str = Field(..., description="Human-readable estimate of audience size")
    stars: int = Field(..., ge=0, description="Stargazer count")
    forks: int = Field(..., ge=0, description="Fork count")
    watchers: int = Field(..., ge=0, description="Subscriber (watcher) count")
    open_issues: int = Field(..., ge=0, description="Open issues and pull requests count")
    visibility_score: int = Field(..., ge=0, le=100, description="Visibility score (0-100)")
    suggested_resume_line: str | None = Field(
        ..., description="Suggested resume line; null for archived repositories",
    )
    topics: list[str] = Field(..., description="Repository topics")
    note: str | None = Field(
        default=None, description="Present only for archived repositories",
    )
