"""Area 400 — integer and floating-point arithmetic.

Two functions here exist purely to override Python's defaults. `DIV` must
truncate toward zero, so it cannot use `//`; `MOD` must take the sign of the
dividend, so it cannot use `%`. Python and Rust disagree on both, the contract
picks a side, and Python is the one that has to bend. `ROUND` is a third: it
sends halves away from zero, so it cannot use `round()`.

Floats are IEEE 754 binary64 in both backends, and the hardware already agrees
on `+ - * /`. What the hosts disagree on is everything around the arithmetic:
NaN, infinity, negative zero, rounding halves, and how a float prints. Every
float function below funnels its result through `_finite`, which is where the
first three are settled; `float_text` settles the last.
"""

from __future__ import annotations

import math
import re

from .faults import PhonebookFault

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

_INT = re.compile(r"^[+-]?[0-9]+$")
_FLOAT = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
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


# --------------------------------------------------------------------------
# floats
# --------------------------------------------------------------------------


def _finite(value: float, operation: str) -> float:
    """Every float result passes through here: finite, and zero has one sign."""
    if not math.isfinite(value):
        raise PhonebookFault("overflow", f"{operation} is too large to be a finite float")
    return 0.0 if value == 0.0 else value


def add_float(a: float, b: float) -> float:
    """400-0000010 ADD_FLOAT."""
    return _finite(a + b, "ADD_FLOAT")


def sub_float(a: float, b: float) -> float:
    """400-0000011 SUB_FLOAT."""
    return _finite(a - b, "SUB_FLOAT")


def mul_float(a: float, b: float) -> float:
    """400-0000012 MUL_FLOAT."""
    return _finite(a * b, "MUL_FLOAT")


def div_float(a: float, b: float) -> float:
    """400-0000013 DIV_FLOAT — dividing by zero is an error, never inf or NaN."""
    if b == 0.0:
        raise PhonebookFault("division_by_zero", "DIV_FLOAT by zero")
    return _finite(a / b, "DIV_FLOAT")


def to_float(value: int) -> float:
    """400-0000014 TO_FLOAT — nearest float, ties to even, as float() rounds."""
    return float(value)


def to_int(value: float) -> int:
    """400-0000015 TO_INT — truncates toward zero; never saturates."""
    truncated = math.trunc(value)
    if truncated < INT64_MIN or truncated > INT64_MAX:
        raise PhonebookFault("overflow", f"{value!r} does not fit in a 64-bit signed integer")
    return truncated


def round_(value: float) -> float:
    """400-0000016 ROUND — halves away from zero. NOT Python's `round()`.

    Decided on the exact binary value: `magnitude - whole` is exact because
    `whole` is `magnitude` with its fraction bits dropped, so there is no
    `+ 0.5` here to round 0.49999999999999994 up to 1.
    """
    magnitude = abs(value)
    whole = float(math.floor(magnitude))
    if magnitude - whole >= 0.5:
        whole += 1.0
    return _finite(-whole if value < 0 else whole, "ROUND")


def parse_float(value: str, fallback: float) -> float:
    """400-0000017 PARSE_FLOAT — never fails; unparseable text yields the fallback."""
    candidate = value.strip(WHITESPACE)
    if not _FLOAT.match(candidate):
        return fallback
    parsed = float(candidate)
    if not math.isfinite(parsed):
        return fallback
    return 0.0 if parsed == 0.0 else parsed


def float_text(value: float) -> str:
    """How TO_TEXT (100-0000005) renders a float.

    The digits come from `repr`, which is the shortest string that reads back
    as the same float. The layout is then applied by hand, the same way the Rust
    runtime applies it, rather than trusting either host's own layout.
    """
    digits, exponent = _shortest_digits(abs(value))
    return ("-" if value < 0 else "") + _layout(digits, exponent)


def _shortest_digits(magnitude: float) -> tuple[str, int]:
    """Significant digits d1 d2 ... dn and exponent E, value = d1.d2...dn x 10^E."""
    mantissa, _, exp = repr(magnitude).partition("e")
    whole, _, fraction = mantissa.partition(".")
    digits = whole + fraction
    exponent = int(exp or "0") + len(whole) - 1
    significant = digits.lstrip("0")
    exponent -= len(digits) - len(significant)
    significant = significant.rstrip("0")
    if not significant:
        return "0", 0
    return significant, exponent


def _layout(digits: str, exponent: int) -> str:
    """Positional for -4 <= E < 16, otherwise d.ddde+XX."""
    if -4 <= exponent < 16:
        if exponent < 0:
            return "0." + "0" * (-exponent - 1) + digits
        whole = digits[: exponent + 1].ljust(exponent + 1, "0")
        fraction = digits[exponent + 1 :] or "0"
        return whole + "." + fraction
    mantissa = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
    sign = "+" if exponent >= 0 else "-"
    return f"{mantissa}e{sign}{abs(exponent):02d}"
