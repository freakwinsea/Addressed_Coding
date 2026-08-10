"""Area 600 — logic and comparison.

Nothing short-circuits. Arguments arrive as already-bound values, so there is
nothing left to skip evaluating.
"""

from __future__ import annotations


def not_(value: bool) -> bool:
    """600-0000001 NOT."""
    return not value


def and_(a: bool, b: bool) -> bool:
    """600-0000002 AND — eager."""
    return a and b


def or_(a: bool, b: bool) -> bool:
    """600-0000003 OR — eager."""
    return a or b


def equals(a, b) -> bool:
    """600-0000004 EQUALS — exact code-point equality for text."""
    return a == b


def less_than(a, b) -> bool:
    """600-0000005 LESS_THAN."""
    return a < b


def greater_than(a, b) -> bool:
    """600-0000006 GREATER_THAN."""
    return a > b


def is_empty(value: str) -> bool:
    """600-0000007 IS_EMPTY — whitespace is not empty."""
    return value == ""
