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
