"""Tests for pure helper functions — no network needed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from opencollab_mcp.helpers import (
    days_ago,
    decode_base64_content,
    parse_issue_number,
    recent_date_str,
    truncate,
)


class TestDaysAgo:
    def test_none_input(self):
        assert days_ago(None) is None
        assert days_ago("") is None

    def test_unparseable_returns_none(self):
        assert days_ago("not-a-date") is None

    def test_z_suffix_handled(self):
        # Build a UTC timestamp 5 days ago, then format with the Z suffix
        # that GitHub uses.
        five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
        iso = five_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert days_ago(iso) in (4, 5)  # tolerate hour-rounding

    def test_recent(self):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert days_ago(now) == 0


class TestTruncate:
    def test_none_returns_empty(self):
        assert truncate(None) == ""

    def test_empty_returns_empty(self):
        assert truncate("") == ""

    def test_short_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_long_truncated_with_ellipsis(self):
        result = truncate("a" * 200, 50)
        assert len(result) == 51  # 50 chars + ellipsis
        assert result.endswith("…")

    def test_exactly_at_limit_no_ellipsis(self):
        text = "x" * 10
        assert truncate(text, 10) == text


class TestRecentDateStr:
    def test_format(self):
        result = recent_date_str(30)
        # Must parse as a date.
        datetime.strptime(result, "%Y-%m-%d")

    def test_zero_days_is_today(self):
        result = recent_date_str(0)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result == today


class TestParseIssueNumber:
    def test_plain_number(self):
        assert parse_issue_number("123") == 123

    def test_with_hash(self):
        assert parse_issue_number("#456") == 456

    def test_with_whitespace(self):
        assert parse_issue_number("  789  ") == 789

    def test_with_hash_and_whitespace(self):
        assert parse_issue_number("  #1011  ") == 1011

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            parse_issue_number("abc")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_issue_number("")

    def test_negative_raises(self):
        # Stripping '#' from '-12' leaves '-12', not all-digits.
        with pytest.raises(ValueError):
            parse_issue_number("-12")


class TestDecodeBase64:
    def test_non_base64_returns_empty(self):
        assert decode_base64_content({"encoding": "utf-8", "content": "hi"}) == ""

    def test_decodes_base64(self):
        # "hello world" base64 == "aGVsbG8gd29ybGQ="
        result = decode_base64_content({"encoding": "base64", "content": "aGVsbG8gd29ybGQ="})
        assert result == "hello world"

    def test_empty_content(self):
        assert decode_base64_content({"encoding": "base64", "content": ""}) == ""
