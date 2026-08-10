"""Area 200 — text.

Every index and length here counts Unicode scalar values, which Python's `str`
gives for free and Rust's `String` does not. That asymmetry is handled in each
backend rather than leaking into the contract.
"""

from __future__ import annotations

import re

from .faults import PhonebookFault

#: The contract's whitespace set: ASCII only, deliberately not Unicode-wide.
WHITESPACE = " \t\n\r\f\v"
_RUNS = re.compile(r"[ \t\n\r\f\v]+")

_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_UPPER = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def split_lines(value: str) -> list[str]:
    """200-0000001 SPLIT_LINES — CRLF-tolerant, absorbs one trailing newline."""
    if not value:
        return []
    if value.endswith("\n"):
        value = value[:-1]
    return [part[:-1] if part.endswith("\r") else part for part in value.split("\n")]


def split(value: str, separator: str) -> list[str]:
    """200-0000002 SPLIT."""
    if separator == "":
        raise PhonebookFault("empty_separator", "SPLIT needs a non-empty separator")
    return value.split(separator)


def split_words(value: str) -> list[str]:
    """200-0000003 SPLIT_WORDS — ASCII whitespace runs, no empty words."""
    return [word for word in _RUNS.split(value) if word]


def join(parts: list, separator: str) -> str:
    """200-0000004 JOIN."""
    return separator.join(parts)


def trim(value: str) -> str:
    """200-0000005 TRIM."""
    return value.strip(WHITESPACE)


def lowercase(value: str) -> str:
    """200-0000006 LOWERCASE — ASCII only, by contract."""
    return value.translate(_LOWER)


def uppercase(value: str) -> str:
    """200-0000007 UPPERCASE — ASCII only, by contract."""
    return value.translate(_UPPER)


def replace(value: str, find: str, replace_with: str) -> str:
    """200-0000008 REPLACE — left to right, non-overlapping, never rescanned."""
    if find == "":
        raise PhonebookFault("empty_find", "REPLACE needs a non-empty search string")
    return value.replace(find, replace_with)


def contains(haystack: str, needle: str) -> bool:
    """200-0000009 CONTAINS."""
    return needle in haystack


def starts_with(value: str, prefix: str) -> bool:
    """200-0000010 STARTS_WITH."""
    return value.startswith(prefix)


def length(value: str) -> int:
    """200-0000011 LENGTH — Unicode scalar values, not bytes."""
    return len(value)


def slice_(value: str, start: int, end: int) -> str:
    """200-0000012 SLICE — clamped; negative indices clamp to 0, never wrap."""
    size = len(value)
    lo = max(0, min(start, size))
    hi = max(0, min(end, size))
    if hi <= lo:
        return ""
    return value[lo:hi]
