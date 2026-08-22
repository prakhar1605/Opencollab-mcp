"""Pydantic input models for OpenCollab MCP tools.

`extra="forbid"` rejects unknown fields — important defense against
LLM-generated tool calls passing through stray keys.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UsernameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    username: str = Field(..., description="GitHub username", min_length=1, max_length=39)


class RepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner (e.g. 'facebook')", min_length=1)
    repo: str = Field(..., description="Repository name (e.g. 'react')", min_length=1)


class IssueInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    owner: str = Field(..., description="Repository owner", min_length=1)
    repo: str = Field(..., description="Repository name", min_length=1)
    # Kept as str on purpose — many LLM clients pass numbers as strings,
    # and we run a permissive parser (handles '#123', '123', ' 123 ').
    issue_number: str = Field(
        ...,
        description="Issue number (e.g. '123' or '#123')",
        min_length=1,
    )

class LanguageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    language: str = Field(
        ...,
        description="Programming language (e.g. 'Python', 'TypeScript', 'Rust')",
        min_length=1,
    )

    difficulty: Literal["beginner", "intermediate"] = Field(
        default="beginner",
        description='beginner searches label:"good first issue"; intermediate searches label:"help wanted"',
)
