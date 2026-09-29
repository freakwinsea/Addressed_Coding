"""Area 400 — integer, floating-point, bigint, decimal and fraction arithmetic.

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

from .decimal_ import MAX_SCALE, Decimal, divide_rounded
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
# bigints
# --------------------------------------------------------------------------
#
# A bigint is a Python int, so the arithmetic is the host's own and exact. What
# the contract adds is the ceiling: at most BIGINT_MAX_DIGITS decimal digits.
# The ceiling is compared against a power of ten, never by counting the digits
# of a string, because Python refuses to turn an int of more than 4300 digits
# into text at all.

BIGINT_MAX_DIGITS = 4000
_BIGINT_LIMIT = 10**BIGINT_MAX_DIGITS


def _checked_big(value: int, operation: str) -> int:
    """Every bigint result passes through here."""
    if -_BIGINT_LIMIT < value < _BIGINT_LIMIT:
        return value
    raise PhonebookFault(
        "overflow", f"{operation} result has more than {BIGINT_MAX_DIGITS} digits"
    )


def to_big(value: int) -> int:
    """400-0000023 TO_BIG — every int is a bigint; this never fails."""
    return value


def big_to_int(value: int) -> int:
    """400-0000024 BIG_TO_INT — overflow outside the 64-bit range, never wraps."""
    if value < INT64_MIN or value > INT64_MAX:
        raise PhonebookFault("overflow", "BIG_TO_INT value does not fit in a 64-bit signed integer")
    return value


def add_big(a: int, b: int) -> int:
    """400-0000025 ADD_BIG."""
    return _checked_big(a + b, "ADD_BIG")


def sub_big(a: int, b: int) -> int:
    """400-0000026 SUB_BIG."""
    return _checked_big(a - b, "SUB_BIG")


def mul_big(a: int, b: int) -> int:
    """400-0000027 MUL_BIG."""
    return _checked_big(a * b, "MUL_BIG")


def div_big(a: int, b: int) -> int:
    """400-0000028 DIV_BIG — truncates toward zero, as DIV does. NOT `//`."""
    if b == 0:
        raise PhonebookFault("division_by_zero", "DIV_BIG by zero")
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def mod_big(a: int, b: int) -> int:
    """400-0000029 MOD_BIG — sign of the dividend, as MOD does. NOT `%`."""
    if b == 0:
        raise PhonebookFault("division_by_zero", "MOD_BIG by zero")
    remainder = abs(a) % abs(b)
    return -remainder if a < 0 else remainder


def pow_big(base: int, exponent: int) -> int:
    """400-0000030 POW_BIG — the same square-and-multiply as POW.

    NOT `**`, which would build a number of any size before anything checked
    it. Here every step is checked against the ceiling, so no intermediate is
    ever more than twice the ceiling's digits.
    """
    if exponent < 0:
        raise PhonebookFault("negative_exponent", f"POW_BIG exponent {exponent} is negative")
    result = 1
    while exponent > 0:
        if exponent & 1:
            result = _checked_big(result * base, "POW_BIG")
        exponent >>= 1
        if exponent > 0:
            base = _checked_big(base * base, "POW_BIG")
    return result


def parse_big(value: str, fallback: int) -> int:
    """400-0000031 PARSE_BIG — never fails; unparseable text yields the fallback.

    Leading zeros are dropped before the digits are counted or converted, so
    "000...0001" is 1 however many zeros it has, and `int()` never sees more
    digits than the ceiling (it would refuse past 4300).
    """
    candidate = value.strip(WHITESPACE)
    if not _INT.match(candidate):
        return fallback
    negative = candidate[0] == "-"
    digits = candidate.lstrip("+-").lstrip("0")
    if len(digits) > BIGINT_MAX_DIGITS:
        return fallback
    parsed = int(digits) if digits else 0
    return -parsed if negative else parsed


# --------------------------------------------------------------------------
# decimals
# --------------------------------------------------------------------------
#
# The type itself is in decimal_.py. What the functions below add is the
# contract around it: which scale a result has, the one rounding rule (halves
# away from zero, as ROUND), and the ceilings, which every result that can grow
# passes through `Decimal.checked` to meet.


def _checked_places(places: int, operation: str) -> int:
    if places < 0 or places > MAX_SCALE:
        raise PhonebookFault(
            "invalid_places", f"{operation} places {places} is not between 0 and {MAX_SCALE}"
        )
    return places


def to_dec(value: int) -> Decimal:
    """400-0000040 TO_DEC — an int as a decimal with no places; never fails."""
    return Decimal(value, 0)


def big_to_dec(value: int) -> Decimal:
    """400-0000041 BIG_TO_DEC — a bigint as a decimal with no places; never fails."""
    return Decimal(value, 0)


def dec_to_int(value: Decimal) -> int:
    """400-0000042 DEC_TO_INT — truncates toward zero, as TO_INT does."""
    whole = abs(value.coefficient) // 10**value.scale
    whole = -whole if value.coefficient < 0 else whole
    if whole < INT64_MIN or whole > INT64_MAX:
        raise PhonebookFault("overflow", "DEC_TO_INT value does not fit in a 64-bit signed integer")
    return whole


def add_dec(a: Decimal, b: Decimal) -> Decimal:
    """400-0000043 ADD_DEC — the result has the larger of the two scales."""
    scale = max(a.scale, b.scale)
    return Decimal(a.rescaled(scale) + b.rescaled(scale), scale).checked("ADD_DEC")


def sub_dec(a: Decimal, b: Decimal) -> Decimal:
    """400-0000044 SUB_DEC — the result has the larger of the two scales."""
    scale = max(a.scale, b.scale)
    return Decimal(a.rescaled(scale) - b.rescaled(scale), scale).checked("SUB_DEC")


def mul_dec(a: Decimal, b: Decimal) -> Decimal:
    """400-0000045 MUL_DEC — exact; the scales add, so 1.5 x 0.25 is 0.375."""
    return Decimal(a.coefficient * b.coefficient, a.scale + b.scale).checked("MUL_DEC")


def div_dec(a: Decimal, b: Decimal, places: int) -> Decimal:
    """400-0000046 DIV_DEC — the exact quotient, rounded once to `places`.

    a / b = (ca / 10^sa) / (cb / 10^sb), so the quotient at `places` places is
    ca * 10^(sb + places) / (cb * 10^sa), rounded to a whole number. Both
    exponents are never negative, so nothing is rounded before that division.
    """
    _checked_places(places, "DIV_DEC")
    if b.coefficient == 0:
        raise PhonebookFault("division_by_zero", "DIV_DEC by zero")
    numerator = a.coefficient * 10 ** (b.scale + places)
    denominator = b.coefficient * 10**a.scale
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    return Decimal(divide_rounded(numerator, denominator), places).checked("DIV_DEC")


def round_dec(value: Decimal, places: int) -> Decimal:
    """400-0000047 ROUND_DEC — to exactly `places` places, halves away from zero.

    Fewer places than the value has rounds; more pads with zeros, so
    ROUND_DEC(5, 2) is 5.00. NOT `round()`, which sends halves to even.
    """
    _checked_places(places, "ROUND_DEC")
    return Decimal(value.rescaled(places), places).checked("ROUND_DEC")


def parse_dec(value: str, fallback: Decimal) -> Decimal:
    """400-0000048 PARSE_DEC — never fails; unparseable text yields the fallback."""
    parsed = Decimal.parse(value.strip(WHITESPACE))
    return fallback if parsed is None else parsed


def dec_to_float(value: Decimal) -> float:
    """400-0000049 DEC_TO_FLOAT — the nearest float, ties to even.

    `float()` of the decimal's own text is correctly rounded however many
    digits it has, as Rust's `str::parse::<f64>` is, so both backends read the
    same digits the same way.
    """
    return _finite(float(value.text()), "DEC_TO_FLOAT")


def float_to_dec(value: float) -> Decimal:
    """400-0000050 FLOAT_TO_DEC — the float's shortest digits, as TO_TEXT
    prints them, never its exact binary value: 0.1 is 0.1, not
    0.1000000000000000055511151231257827021181583404541015625.

    With digits d1...dn and exponent E, the value is d1...dn x 10^(E-n+1).
    A float has at most 17 significant digits and E is between -324 and 308,
    so the result is always inside both ceilings.
    """
    digits, exponent = _shortest_digits(abs(value))
    power = exponent - len(digits) + 1
    coefficient = int(digits)
    if value < 0:
        coefficient = -coefficient
    if power >= 0:
        return Decimal(coefficient * 10**power, 0)
    return Decimal(coefficient, -power)


# --------------------------------------------------------------------------
# comparisons
# --------------------------------------------------------------------------


def number_equals(a, b) -> bool:
    """400-0000060 NUMBER_EQUALS — exact, floats included."""
    return a == b


def number_not_equals(a, b) -> bool:
    """400-0000061 NUMBER_NOT_EQUALS."""
    return a != b


def less_or_equal(a, b) -> bool:
    """400-0000062 LESS_OR_EQUAL."""
    return a <= b


def greater_or_equal(a, b) -> bool:
    """400-0000063 GREATER_OR_EQUAL."""
    return a >= b


def compare(a, b) -> int:
    """400-0000064 COMPARE — exactly -1, 0, or 1."""
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def close_to(a: float, b: float, tolerance: float) -> bool:
    """400-0000065 CLOSE_TO — absolute tolerance, edge included.

    A difference too large to be finite comes out as infinity, which no
    tolerance reaches, and a negative tolerance is below every difference.
    Neither needs its own branch.
    """
    return abs(a - b) <= tolerance


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


# --------------------------------------------------------------------------
# conversions between the exact types
# --------------------------------------------------------------------------


def dec_to_big(value: Decimal) -> int:
    """400-0000100 DEC_TO_BIG — truncates toward zero, as DEC_TO_INT does; never fails."""
    whole = abs(value.coefficient) // 10**value.scale
    return -whole if value.coefficient < 0 else whole


def big_to_float(value: int) -> float:
    """400-0000101 BIG_TO_FLOAT — the nearest float, ties to even.

    `float()` of the bigint's text, as DEC_TO_FLOAT reads a decimal's, so both
    backends round the same digits the same way. `float(int)` would round the
    same, but raises its own OverflowError where this should fault.
    """
    return _finite(float(str(value)), "BIG_TO_FLOAT")


def float_to_big(value: float) -> int:
    """400-0000102 FLOAT_TO_BIG — the float's exact binary value, truncated
    toward zero. `int()` of a float already does exactly that."""
    return int(value)


def dec_to_fraction(value: Decimal) -> Fraction:
    """400-0000103 DEC_TO_FRACTION — exact: coefficient / 10^scale, reduced."""
    return _fraction(value.coefficient, 10**value.scale, "DEC_TO_FRACTION")


def fraction_to_dec(value: Fraction, places: int) -> Decimal:
    """400-0000104 FRACTION_TO_DEC — rounded once to `places`, halves away from zero.

    numerator * 10^places / denominator, rounded to a whole number, is the
    coefficient. The denominator is always positive, as divide_rounded needs.
    """
    _checked_places(places, "FRACTION_TO_DEC")
    return Decimal(divide_rounded(value.numerator * 10**places, value.denominator), places)


def big_to_fraction(value: int) -> Fraction:
    """400-0000105 BIG_TO_FRACTION — the value over 1; overflow past 64 bits."""
    if value < INT64_MIN or value > INT64_MAX:
        raise PhonebookFault("overflow", "BIG_TO_FRACTION value does not fit in a 64-bit fraction")
    return Fraction(value, 1)
# printing
# --------------------------------------------------------------------------
#
# Each of these prints a number with exactly `places` digits after the point,
# rounding halves away from zero, as ROUND and ROUND_DEC do. None uses Python's
# `format()` or f-strings: those decide on a float's exact binary value and send
# halves to even, so f"{2.675:.2f}" is '2.67'. The contract rounds the digits
# TO_TEXT prints, so 2.675 is '2.68'. Every result is plain digits, never an
# exponent, and never a negative zero.


def _fixed(coefficient: int, places: int) -> str:
    """coefficient x 10^-places as text, the way a decimal prints: '-0.05'."""
    return Decimal(coefficient, places).text()


def format_float(value: float, places: int) -> str:
    """400-0000120 FORMAT_FLOAT — the float's shortest digits, rounded to `places`.

    FLOAT_TO_DEC gives exactly the digits TO_TEXT prints, and ROUND_DEC's rule
    rounds those. NOT `format()`, which rounds the binary value half to even.
    """
    _checked_places(places, "FORMAT_FLOAT")
    return _fixed(float_to_dec(value).rescaled(places), places)


def format_dec(value: Decimal, places: int) -> str:
    """400-0000121 FORMAT_DEC — ROUND_DEC then TO_TEXT, without the 4000-digit ceiling."""
    _checked_places(places, "FORMAT_DEC")
    return _fixed(value.rescaled(places), places)


def format_fraction(value: Fraction, places: int) -> str:
    """400-0000122 FORMAT_FRACTION — the exact value, rounded once to `places`.

    n/d at `places` places is n x 10^places / d rounded to a whole number, so
    1/3 to 4 places is 3333 / 10^4. Nothing is rounded before that division.
    """
    _checked_places(places, "FORMAT_FRACTION")
    return _fixed(divide_rounded(value.numerator * 10**places, value.denominator), places)
# roots, floors, ceilings and remainders
# --------------------------------------------------------------------------
#
# Square roots are worked out on whole numbers, never with a host `sqrt`, so
# both backends follow one written-down method and agree bit for bit. A whole
# number's square root rounded down is a single right answer, so Python's
# `math.isqrt` is safe to use for it; the Rust runtime writes the same thing
# out by hand. Everything else (the rounding of the float and the decimal) is
# spelled out here and there, step for step.


def _no_negative_root(negative: bool, operation: str) -> None:
    if negative:
        raise PhonebookFault("negative_root", f"{operation} of a negative number")


def sqrt_(value: float) -> float:
    """400-0000140 SQRT — the exact square root, rounded once to the nearest
    float, ties to even. NOT `math.sqrt`: the same answer, but written out so
    the two runtimes share a method instead of trusting two maths libraries.

    value = m x 2^e with m a whole number. Make e even, then scale m up by a
    power of four until its root has at least 55 bits. That root, rounded to
    53 bits with the bits it drops and whether it was exact, is the answer.
    """
    _no_negative_root(value < 0.0, "SQRT")
    if value == 0.0:
        return 0.0
    fraction, exponent = math.frexp(value)
    mantissa = int(math.ldexp(fraction, 53))
    exponent -= 53
    if exponent % 2:
        mantissa <<= 1
        exponent -= 1
    shift = max(0, (111 - mantissa.bit_length()) // 2)
    scaled = mantissa << (2 * shift)
    root = math.isqrt(scaled)
    inexact = root * root != scaled
    drop = root.bit_length() - 53
    kept, rest = root >> drop, root & ((1 << drop) - 1)
    half = 1 << (drop - 1)
    if rest > half or (rest == half and (inexact or kept & 1)):
        kept += 1
    return math.ldexp(kept, exponent // 2 - shift + drop)


def floor_(value: float) -> float:
    """400-0000141 FLOOR — the largest whole float not above the value."""
    return _finite(float(math.floor(value)), "FLOOR")


def ceil_(value: float) -> float:
    """400-0000142 CEIL — the smallest whole float not below the value. `_finite`
    turns CEIL(-0.5), which is -0.0, into 0.0."""
    return _finite(float(math.ceil(value)), "CEIL")


def mod_float(a: float, b: float) -> float:
    """400-0000143 MOD_FLOAT — sign of the dividend, like MOD. `math.fmod` and
    Rust's `%` are both the exact IEEE remainder; Python's `%` is not."""
    if b == 0.0:
        raise PhonebookFault("division_by_zero", "MOD_FLOAT by zero")
    return _finite(math.fmod(a, b), "MOD_FLOAT")


def isqrt(value: int) -> int:
    """400-0000144 ISQRT — the square root rounded down."""
    _no_negative_root(value < 0, "ISQRT")
    return math.isqrt(value)


def isqrt_big(value: int) -> int:
    """400-0000145 ISQRT_BIG — the square root rounded down; never grows."""
    _no_negative_root(value < 0, "ISQRT_BIG")
    return math.isqrt(value)


def sqrt_dec(value: Decimal, places: int) -> Decimal:
    """400-0000146 SQRT_DEC — the exact root, rounded once to `places`,
    halves away from zero.

    The answer's coefficient is sqrt(c x 10^(2p - s)) rounded, which is
    sqrt(top / bottom) with both whole. q = isqrt(top // bottom) is that root
    rounded down, and it rounds up when the root is at least q + 1/2, that is
    when 4 x top >= bottom x (2q + 1)^2.
    """
    _checked_places(places, "SQRT_DEC")
    _no_negative_root(value.coefficient < 0, "SQRT_DEC")
    power = 2 * places - value.scale
    top = value.coefficient * 10 ** max(power, 0)
    bottom = 10 ** max(-power, 0)
    root = math.isqrt(top // bottom)
    if 4 * top >= bottom * (2 * root + 1) ** 2:
        root += 1
    return Decimal(root, places).checked("SQRT_DEC")


def _whole_dec(value: Decimal, up: bool, operation: str) -> Decimal:
    """The decimal's whole number toward -inf (FLOOR) or +inf (CEIL), 0 places."""
    whole, remainder = divmod(value.coefficient, 10**value.scale)
    if up and remainder:
        whole += 1
    return Decimal(whole, 0).checked(operation)


def floor_dec(value: Decimal) -> Decimal:
    """400-0000147 FLOOR_DEC — down to a whole number, with no places."""
    return _whole_dec(value, False, "FLOOR_DEC")


def ceil_dec(value: Decimal) -> Decimal:
    """400-0000148 CEIL_DEC — up to a whole number, with no places."""
    return _whole_dec(value, True, "CEIL_DEC")


def _truncated_remainder(a: int, b: int) -> int:
    """a - b x trunc(a / b): the remainder with the dividend's sign, as MOD."""
    remainder = abs(a) % abs(b)
    return -remainder if a < 0 else remainder


def mod_dec(a: Decimal, b: Decimal) -> Decimal:
    """400-0000149 MOD_DEC — exact, sign of the dividend, the larger scale."""
    if b.coefficient == 0:
        raise PhonebookFault("division_by_zero", "MOD_DEC by zero")
    scale = max(a.scale, b.scale)
    remainder = _truncated_remainder(a.rescaled(scale), b.rescaled(scale))
    return Decimal(remainder, scale).checked("MOD_DEC")


def ceil_fraction(a: Fraction) -> int:
    """400-0000150 CEIL_FRACTION — toward positive infinity."""
    return -(-a.numerator // a.denominator)


def mod_fraction(a: Fraction, b: Fraction) -> Fraction:
    """400-0000151 MOD_FRACTION — exact, sign of the dividend.

    Over the shared denominator a.den x b.den, the two numerators are
    a.num x b.den and b.num x a.den, and the remainder is theirs.
    """
    if b.numerator == 0:
        raise PhonebookFault("division_by_zero", "MOD_FRACTION by zero")
    remainder = _truncated_remainder(a.numerator * b.denominator, b.numerator * a.denominator)
    return _fraction(remainder, a.denominator * b.denominator, "MOD_FRACTION")


# --------------------------------------------------------------------------
# bits and bases
# --------------------------------------------------------------------------
#
# An int is 64 bits in two's complement on every backend. Python's own ints
# have no width, so `~`, `&`, `|` and `^` already agree with Rust on int64
# inputs, but `<<` would grow forever and `bin(-5)` prints '-0b101'. Every
# function below works on the 64-bit pattern: `_bits` reads it as an unsigned
# number, `_signed` reads it back.

_BITS_MASK = 2**64 - 1
_BASE_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _bits(value: int) -> int:
    """The 64-bit pattern of an int, as an unsigned number from 0 to 2**64 - 1."""
    return value & _BITS_MASK


def _signed(bits: int) -> int:
    """A 64-bit pattern read back as a signed int."""
    return bits - 2**64 if bits > INT64_MAX else bits


def _checked_shift(count: int, operation: str) -> int:
    if count < 0:
        raise PhonebookFault("invalid_shift", f"{operation} count {count} is negative")
    return count


def _checked_base(base: int, operation: str) -> int:
    if base < 2 or base > 36:
        raise PhonebookFault("invalid_base", f"{operation} base {base} is not between 2 and 36")
    return base


def _digits_in_base(magnitude: int, base: int) -> str:
    """The digits of a non-negative number, lowercase, most significant first."""
    if magnitude == 0:
        return "0"
    digits = []
    while magnitude > 0:
        magnitude, digit = divmod(magnitude, base)
        digits.append(_BASE_DIGITS[digit])
    return "".join(reversed(digits))


def _read_digits(digits: str, base: int, limit: int) -> int | None:
    """ASCII digits in `base`, either case, to a number below `limit`.

    NOT `int(text, base)`, which takes underscores, a '0x' prefix when the base
    is 16, and digits from other scripts. None for any of those, and as soon as
    the number reaches the limit, so a long input is never read to the end.
    """
    if not digits:
        return None
    value = 0
    for char in digits:
        digit = _BASE_DIGITS.find(char.lower()) if char.isascii() else -1
        if digit < 0 or digit >= base:
            return None
        value = value * base + digit
        if value >= limit:
            return None
    return value


def _split_sign(text: str) -> tuple[bool, str]:
    if text[:1] == "-":
        return True, text[1:]
    if text[:1] == "+":
        return False, text[1:]
    return False, text


def bit_and(a: int, b: int) -> int:
    """400-0000160 BIT_AND — on the two 64-bit patterns."""
    return _signed(_bits(a) & _bits(b))


def bit_or(a: int, b: int) -> int:
    """400-0000161 BIT_OR — on the two 64-bit patterns."""
    return _signed(_bits(a) | _bits(b))


def bit_xor(a: int, b: int) -> int:
    """400-0000162 BIT_XOR — on the two 64-bit patterns."""
    return _signed(_bits(a) ^ _bits(b))


def bit_not(a: int) -> int:
    """400-0000163 BIT_NOT — every bit flipped, so the result is -a - 1."""
    return _signed(_bits(a) ^ _BITS_MASK)


def shift_left(value: int, count: int) -> int:
    """400-0000164 SHIFT_LEFT — bits pushed past bit 63 are dropped.

    NOT Python's `<<`, which never drops a bit. 64 or more shifts every bit out.
    """
    count = _checked_shift(count, "SHIFT_LEFT")
    if count >= 64:
        return 0
    return _signed((_bits(value) << count) & _BITS_MASK)


def shift_right(value: int, count: int) -> int:
    """400-0000165 SHIFT_RIGHT — copies of the sign bit come in at the top."""
    count = _checked_shift(count, "SHIFT_RIGHT")
    if count >= 64:
        return -1 if value < 0 else 0
    return value >> count


def shift_right_unsigned(value: int, count: int) -> int:
    """400-0000166 SHIFT_RIGHT_UNSIGNED — zeros come in at the top."""
    count = _checked_shift(count, "SHIFT_RIGHT_UNSIGNED")
    if count >= 64:
        return 0
    return _signed(_bits(value) >> count)


def count_bits(value: int) -> int:
    """400-0000167 COUNT_BITS — ones in the 64-bit pattern, so -1 has 64.

    NOT `bin(value).count("1")`, which counts the ones of the magnitude.
    """
    return bin(_bits(value)).count("1")


def to_base(value: int, base: int) -> str:
    """400-0000168 TO_BASE — a '-' then the magnitude. NOT `bin()` or `hex()`."""
    base = _checked_base(base, "TO_BASE")
    digits = _digits_in_base(-value if value < 0 else value, base)
    return "-" + digits if value < 0 else digits


def parse_base(value: str, base: int, fallback: int) -> int:
    """400-0000169 PARSE_BASE — never fails on the text; a bad base is an error."""
    base = _checked_base(base, "PARSE_BASE")
    negative, digits = _split_sign(value.strip(WHITESPACE))
    # The magnitude can be one more than INT64_MAX when the sign is '-'.
    magnitude = _read_digits(digits, base, 2**63 + 1 if negative else 2**63)
    if magnitude is None:
        return fallback
    return -magnitude if negative else magnitude


def to_base_unsigned(value: int, base: int) -> str:
    """400-0000170 TO_BASE_UNSIGNED — the 64-bit pattern, so -1 in 16 is 16 f's."""
    base = _checked_base(base, "TO_BASE_UNSIGNED")
    return _digits_in_base(_bits(value), base)


def parse_base_unsigned(value: str, base: int, fallback: int) -> int:
    """400-0000171 PARSE_BASE_UNSIGNED — 0 to 2**64 - 1, read back as a pattern."""
    base = _checked_base(base, "PARSE_BASE_UNSIGNED")
    bits = _read_digits(value.strip(WHITESPACE), base, 2**64)
    if bits is None:
        return fallback
    return _signed(bits)


def big_to_base(value: int, base: int) -> str:
    """400-0000172 BIG_TO_BASE — a '-' then the magnitude, as TO_BASE."""
    base = _checked_base(base, "BIG_TO_BASE")
    digits = _digits_in_base(-value if value < 0 else value, base)
    return "-" + digits if value < 0 else digits


def parse_big_base(value: str, base: int, fallback: int) -> int:
    """400-0000173 PARSE_BIG_BASE — never fails on the text; the 4000-digit ceiling holds."""
    base = _checked_base(base, "PARSE_BIG_BASE")
    negative, digits = _split_sign(value.strip(WHITESPACE))
    magnitude = _read_digits(digits, base, _BIGINT_LIMIT)
    if magnitude is None:
        return fallback
    return -magnitude if negative else magnitude
