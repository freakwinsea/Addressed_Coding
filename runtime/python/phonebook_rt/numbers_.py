"""Area 400 — integer arithmetic.

Two functions here exist purely to override Python's defaults. `DIV` must
truncate toward zero, so it cannot use `//`; `MOD` must take the sign of the
dividend, so it cannot use `%`. Python and Rust disagree on both, the contract
picks a side, and Python is the one that has to bend.
"""

from __future__ import annotations

import re

from .faults import PhonebookFault

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

_INT = re.compile(r"^[+-]?[0-9]+$")
WHITESPACE = " \t\n\r\f\v"


def _checked(value: int) -> int:
    if value < INT64_MIN or value > INT64_MAX:
        raise PhonebookFault("overflow", f"{value} does not fit in a 64-bit signed integer")
    return value


def add(a: int, b: int) -> int:
    """400-0000001 ADD."""
    return _checked(a + b)


def sub(a: int, b: int) -> int:
    """400-0000002 SUB."""
    return _checked(a - b)


def mul(a: int, b: int) -> int:
    """400-0000003 MUL."""
    return _checked(a * b)


def div(a: int, b: int) -> int:
    """400-0000004 DIV — truncates toward zero. NOT Python's `//`."""
    if b == 0:
        raise PhonebookFault("division_by_zero", "DIV by zero")
    quotient = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        quotient = -quotient
    return _checked(quotient)


def mod(a: int, b: int) -> int:
    """400-0000005 MOD — sign of the dividend. NOT Python's `%`."""
    if b == 0:
        raise PhonebookFault("division_by_zero", "MOD by zero")
    remainder = abs(a) % abs(b)
    return -remainder if a < 0 else remainder


def min_(a: int, b: int) -> int:
    """400-0000006 MIN."""
    return a if a < b else b


def max_(a: int, b: int) -> int:
    """400-0000007 MAX."""
    return a if a > b else b


def sum_(values: list) -> int:
    """400-0000008 SUM — left to right; empty sums to 0."""
    total = 0
    for value in values:
        total = _checked(total + value)
    return total


def parse_int(value: str, fallback: int) -> int:
    """400-0000009 PARSE_INT — never fails; unparseable text yields the fallback."""
    candidate = value.strip(WHITESPACE)
    if not _INT.match(candidate):
        return fallback
    parsed = int(candidate)
    if parsed < INT64_MIN or parsed > INT64_MAX:
        return fallback
    return parsed


def abs_(a: int) -> int:
    """400-0000010 ABS — the smallest int64 has no positive twin, so it overflows."""
    return _checked(-a if a < 0 else a)


def negate(a: int) -> int:
    """400-0000011 NEGATE — the smallest int64 overflows, as in ABS."""
    return _checked(-a)


def pow_(base: int, exponent: int) -> int:
    """400-0000012 POW — squares step by step so overflow is caught, not bignum'd.

    NOT Python's `**`, which would happily build a million-digit number before
    anything noticed it was too big. The base is only squared again when more
    exponent bits remain, so a result that fits never trips on a square it did
    not need.
    """
    if exponent < 0:
        raise PhonebookFault("negative_exponent", f"POW exponent {exponent} is negative")
    result = 1
    while exponent > 0:
        if exponent & 1:
            result = _checked(result * base)
        exponent >>= 1
        if exponent > 0:
            base = _checked(base * base)
    return result


def clamp(value: int, low: int, high: int) -> int:
    """400-0000013 CLAMP — both ends included; low above high is an error."""
    if low > high:
        raise PhonebookFault("invalid_range", f"CLAMP low {low} is above high {high}")
    if value < low:
        return low
    if value > high:
        return high
    return value


def sign(a: int) -> int:
    """400-0000014 SIGN — exactly -1, 0, or 1."""
    if a < 0:
        return -1
    if a > 0:
        return 1
    return 0
