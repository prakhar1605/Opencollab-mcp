"""Utilities for asserting on GitHub search query strings in tests."""

from __future__ import annotations

import re

_KEY_RE = re.compile(r"-?[A-Za-z_][\w.]*:")


def _split_values(raw: str) -> list[str]:
    """Split on commas outside double quotes, dropping the quote characters."""
    values: list[str] = []
    buf: list[str] = []
    in_quotes = False
    for ch in raw:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            values.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    values.append("".join(buf))
    return [value.strip() for value in values if value.strip()]


def parse_query(query: str) -> dict[str, list[str]]:
    """Parse a `key:value` search string into {key: [values]}.

    A value runs until the next `key:` that starts a token outside quotes, so
    unquoted multi-word values work. Values are split on commas outside quotes.
    Repeated keys are merged, and a leading "-" stays part of the key.
    """
    starts: list[tuple[int, int, str]] = []
    in_quotes = False
    for i, ch in enumerate(query):
        if ch == '"':
            in_quotes = not in_quotes
        elif not in_quotes and (i == 0 or query[i - 1].isspace()):
            if match := _KEY_RE.match(query, i):
                starts.append((i, match.end(), match.group()[:-1]))

    result: dict[str, list[str]] = {}
    for n, (_, value_start, key) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(query)
        result.setdefault(key, []).extend(_split_values(query[value_start:end]))
    return result
