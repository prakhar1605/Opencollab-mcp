"""Reject oversized language values before constructing a GitHub query."""

import pytest
from pydantic import ValidationError

from opencollab_mcp.models import LanguageInput


@pytest.mark.parametrize("length", [51, 5000])
def test_language_rejects_overlong_names(length):
    with pytest.raises(ValidationError) as exc:
        LanguageInput(language="x" * length)
    assert exc.value.errors()[0]["type"] == "string_too_long"
    assert exc.value.errors()[0]["loc"] == ("language",)


@pytest.mark.parametrize("language", ["x" * 50, "Jupyter Notebook", "Visual Basic .NET"])
def test_language_accepts_limit_and_real_names(language):
    assert LanguageInput(language=language).language == language


def test_language_still_rejects_query_injection():
    with pytest.raises(ValidationError):
        LanguageInput(language='Python" label:"bug')


def test_language_rejects_more_than_three_languages():
    with pytest.raises(ValidationError):
        LanguageInput(language="Python, TypeScript, Rust, Go")
