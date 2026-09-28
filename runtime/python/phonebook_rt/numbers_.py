"""Area 400 — integer, floating-point and fraction arithmetic.

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


def _magnitude_gcd(a: int, b: int) -> int:
    """Euclid on the magnitudes, which may be 2**63: the caller checks the fit."""
    a = -a if a < 0 else a
    b = -b if b < 0 else b
    while b != 0:
        a, b = b, a % b
    return a


def gcd(a: int, b: int) -> int:
    """400-0000032 GCD — never negative; 2**63 does not fit and overflows.

    Not `math.gcd`, which would return 2**63 for GCD(INT64_MIN, 0). Written out
    as Euclid so it reads line for line against the Rust runtime.
    """
    return _checked(_magnitude_gcd(a, b))


def lcm(a: int, b: int) -> int:
    """400-0000033 LCM — never negative; divides before multiplying."""
    if a == 0 or b == 0:
        return 0
    divisor = _magnitude_gcd(a, b)
    a = -a if a < 0 else a
    b = -b if b < 0 else b
    return _checked((a // divisor) * b)


def product(values: list) -> int:
    """400-0000034 PRODUCT — left to right; empty is 1; a running overflow faults."""
    total = 1
    for value in values:
        total = _checked(total * value)
    return total


def is_even(a: int) -> bool:
    """400-0000035 IS_EVEN — the remainder is compared with 0, never with 1."""
    return a % 2 == 0


def is_odd(a: int) -> bool:
    """400-0000036 IS_ODD — the opposite of IS_EVEN, for negatives too."""
    return a % 2 != 0


# --------------------------------------------------------------------------
# floats
# --------------------------------------------------------------------------


def _finite(value: float, operation: str) -> float:
    """Every float result passes through here: finite, and zero has one sign."""
    if not math.isfinite(value):
        raise PhonebookFault("overflow", f"{operation} is too large to be a finite float")
    return 0.0 if value == 0.0 else value


def add_float(a: float, b: float) -> float:
    """400-0000015 ADD_FLOAT."""
    return _finite(a + b, "ADD_FLOAT")


def sub_float(a: float, b: float) -> float:
    """400-0000016 SUB_FLOAT."""
    return _finite(a - b, "SUB_FLOAT")


def mul_float(a: float, b: float) -> float:
    """400-0000017 MUL_FLOAT."""
    return _finite(a * b, "MUL_FLOAT")


def div_float(a: float, b: float) -> float:
    """400-0000018 DIV_FLOAT — dividing by zero is an error, never inf or NaN."""
    if b == 0.0:
        raise PhonebookFault("division_by_zero", "DIV_FLOAT by zero")
    return _finite(a / b, "DIV_FLOAT")


def to_float(value: int) -> float:
    """400-0000019 TO_FLOAT — nearest float, ties to even, as float() rounds."""
    return float(value)


def to_int(value: float) -> int:
    """400-0000020 TO_INT — truncates toward zero; never saturates."""
    truncated = math.trunc(value)
    if truncated < INT64_MIN or truncated > INT64_MAX:
        raise PhonebookFault("overflow", f"{value!r} does not fit in a 64-bit signed integer")
    return truncated


def round_(value: float) -> float:
    """400-0000021 ROUND — halves away from zero. NOT Python's `round()`.

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
    """400-0000022 PARSE_FLOAT — never fails; unparseable text yields the fallback."""
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


# --------------------------------------------------------------------------
# fractions
# --------------------------------------------------------------------------
#
# A fraction is an exact ratio of two 64-bit integers, always kept in lowest
# terms with a positive denominator. That one rule makes every fraction have a
# single spelling, so equality, ordering and printing need no further thought.
#
# Python's own `fractions` module is not used. Its numerator and denominator
# grow without limit, where the contract says a fraction that no longer fits in
# 64 bits is an overflow error; and the Rust runtime has no such module to lean
# on, so both are written out the same way by hand. Intermediate products here
# are unbounded Python ints; Rust does the same arithmetic in i128, which is
# wide enough for every product of two 64-bit values, so the two agree.


class Fraction:
    """An exact fraction: numerator / denominator, in lowest terms, denominator > 0.

    Build one with `_fraction`, never directly, so the invariant always holds.
    """

    __slots__ = ("numerator", "denominator")

    def __init__(self, numerator: int, denominator: int):
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "denominator", denominator)

    def __setattr__(self, name, value):
        raise AttributeError("fractions are immutable")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fraction):
            return NotImplemented
        return self.numerator == other.numerator and self.denominator == other.denominator

    def __hash__(self) -> int:
        return hash((self.numerator, self.denominator))

    def _cross(self, other: "Fraction") -> tuple[int, int]:
        return self.numerator * other.denominator, other.numerator * self.denominator

    def __lt__(self, other: "Fraction") -> bool:
        left, right = self._cross(other)
        return left < right

    def __le__(self, other: "Fraction") -> bool:
        left, right = self._cross(other)
        return left <= right

    def __gt__(self, other: "Fraction") -> bool:
        left, right = self._cross(other)
        return left > right

    def __ge__(self, other: "Fraction") -> bool:
        left, right = self._cross(other)
        return left >= right

    def __repr__(self) -> str:
        return f"Fraction({self.numerator}, {self.denominator})"


def _gcd_wide(a: int, b: int) -> int:
    """Euclid's algorithm on the wide working values, as the Rust runtime writes it."""
    while b != 0:
        a, b = b, a % b
    return a


def _fraction(numerator: int, denominator: int, operation: str) -> Fraction:
    """Lowest terms, positive denominator, and both parts inside 64 bits.

    `denominator` is never zero here; every caller has already checked.
    """
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    divisor = _gcd_wide(abs(numerator), denominator)
    numerator //= divisor
    denominator //= divisor
    if not (INT64_MIN <= numerator <= INT64_MAX and denominator <= INT64_MAX):
        raise PhonebookFault(
            "overflow", f"{operation} result does not fit in a 64-bit fraction"
        )
    return Fraction(numerator, denominator)


def make_fraction(numerator: int, denominator: int) -> Fraction:
    """400-0000080 MAKE_FRACTION — reduced to lowest terms, sign on the numerator."""
    if denominator == 0:
        raise PhonebookFault("division_by_zero", "MAKE_FRACTION with a zero denominator")
    return _fraction(numerator, denominator, "MAKE_FRACTION")


def add_fraction(a: Fraction, b: Fraction) -> Fraction:
    """400-0000081 ADD_FRACTION."""
    return _fraction(
        a.numerator * b.denominator + b.numerator * a.denominator,
        a.denominator * b.denominator,
        "ADD_FRACTION",
    )


def sub_fraction(a: Fraction, b: Fraction) -> Fraction:
    """400-0000082 SUB_FRACTION."""
    return _fraction(
        a.numerator * b.denominator - b.numerator * a.denominator,
        a.denominator * b.denominator,
        "SUB_FRACTION",
    )


def mul_fraction(a: Fraction, b: Fraction) -> Fraction:
    """400-0000083 MUL_FRACTION."""
    return _fraction(a.numerator * b.numerator, a.denominator * b.denominator, "MUL_FRACTION")


def div_fraction(a: Fraction, b: Fraction) -> Fraction:
    """400-0000084 DIV_FRACTION — dividing by a zero fraction is an error."""
    if b.numerator == 0:
        raise PhonebookFault("division_by_zero", "DIV_FRACTION by zero")
    return _fraction(a.numerator * b.denominator, a.denominator * b.numerator, "DIV_FRACTION")


def negate_fraction(a: Fraction) -> Fraction:
    """400-0000085 NEGATE_FRACTION — the smallest int64 numerator overflows."""
    return _fraction(-a.numerator, a.denominator, "NEGATE_FRACTION")


def abs_fraction(a: Fraction) -> Fraction:
    """400-0000086 ABS_FRACTION — the smallest int64 numerator overflows."""
    return _fraction(abs(a.numerator), a.denominator, "ABS_FRACTION")


def numerator(a: Fraction) -> int:
    """400-0000087 NUMERATOR — of the lowest-terms form, carrying the sign."""
    return a.numerator


def denominator(a: Fraction) -> int:
    """400-0000088 DENOMINATOR — of the lowest-terms form, always positive."""
    return a.denominator


def fraction_to_float(a: Fraction) -> float:
    """400-0000089 FRACTION_TO_FLOAT — nearest float, ties to even.

    `int / int` in Python divides the exact integers and rounds once, which is
    what the contract asks for. Dividing two floats would round three times.
    """
    return a.numerator / a.denominator


def floor_fraction(a: Fraction) -> int:
    """400-0000090 FLOOR_FRACTION — toward negative infinity; `//` already does that."""
    return a.numerator // a.denominator


def round_fraction(a: Fraction) -> int:
    """400-0000091 ROUND_FRACTION — halves away from zero, like ROUND."""
    whole, remainder = divmod(abs(a.numerator), a.denominator)
    if 2 * remainder >= a.denominator:
        whole += 1
    return -whole if a.numerator < 0 else whole


_FRACTION = re.compile(r"[+-]?[0-9]+(?:/[0-9]+)?")


def parse_fraction(value: str, fallback: Fraction) -> Fraction:
    """400-0000092 PARSE_FRACTION — never fails; unparseable text yields the fallback."""
    candidate = value.strip(WHITESPACE)
    if not _FRACTION.fullmatch(candidate):
        return fallback
    top, _, bottom = candidate.partition("/")
    top_value = int(top)
    bottom_value = int(bottom) if bottom else 1
    if not INT64_MIN <= top_value <= INT64_MAX or not 0 < bottom_value <= INT64_MAX:
        return fallback
    return _fraction(top_value, bottom_value, "PARSE_FRACTION")


def fraction_text(value: Fraction) -> str:
    """How TO_TEXT (100-0000005) renders a fraction: '-1/3', or '2' when whole."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"
