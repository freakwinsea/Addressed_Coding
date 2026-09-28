"""The `decimal` type: an exact base-10 number, such as money.

A decimal is a whole-number coefficient and a scale, the count of digits after
the point: 0.30 is (30, 2), and -1.5 is (-15, 1). 0.10 + 0.20 is exactly 0.30,
where a float would give 0.30000000000000004.

This does NOT use Python's `decimal` module. That module rounds to a context
precision, has signed zeros, NaN and infinity, and prints in its own layout;
pinning all of that down to match the Rust runtime would be more work than
writing the few operations out. So the Python and Rust runtimes each carry
their own, written side by side (`runtime/rust/phonebook_rt/src/decimal.rs`),
with the coefficient kept in the host's big integer: Python's `int`, and the
Rust runtime's hand-written `BigInt`.

The scale is kept, not normalized away, so 0.10 + 0.20 prints as "0.30": the
number of places is part of what a money amount says. Comparison is by value,
so 0.3 and 0.30 are equal and sort as ties.
"""

from __future__ import annotations

import re

from .faults import PhonebookFault

#: At most this many digits in the coefficient, the same ceiling as bigint.
MAX_DIGITS = 4000
#: At most this many digits after the point.
MAX_SCALE = 1000

_LIMIT = 10**MAX_DIGITS
_DECIMAL = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")


class Decimal:
    """coefficient x 10^-scale. Zero is never negative: Python's int 0 has no sign."""

    __slots__ = ("coefficient", "scale")

    def __init__(self, coefficient: int, scale: int):
        self.coefficient = coefficient
        self.scale = scale

    @staticmethod
    def parse(text: str) -> Decimal | None:
        """Read `[+-]?digits('.'digits)?`, nothing else. `None` for any other
        text, or for more than MAX_DIGITS digits once leading zeros are
        dropped, or more than MAX_SCALE digits after the point."""
        if not _DECIMAL.fullmatch(text):
            return None
        negative = text[0] == "-"
        whole, _, fraction = text.lstrip("+-").partition(".")
        digits = (whole + fraction).lstrip("0")
        if len(digits) > MAX_DIGITS or len(fraction) > MAX_SCALE:
            return None
        coefficient = int(digits) if digits else 0
        return Decimal(-coefficient if negative else coefficient, len(fraction))

    @staticmethod
    def literal(text: str) -> Decimal:
        """A decimal literal from a program. The parser has already checked
        it, so a failure here is a bug in the toolchain, not the program."""
        value = Decimal.parse(text)
        if value is None:
            raise ValueError(f"invalid decimal literal {text!r}")
        return value

    def checked(self, operation: str) -> Decimal:
        """Fault unless the value is within both ceilings."""
        if self.scale > MAX_SCALE:
            raise PhonebookFault(
                "overflow", f"{operation} result has more than {MAX_SCALE} digits after the point"
            )
        if not -_LIMIT < self.coefficient < _LIMIT:
            raise PhonebookFault("overflow", f"{operation} result has more than {MAX_DIGITS} digits")
        return self

    def rescaled(self, scale: int) -> int:
        """The coefficient this value would have at `scale`, rounding halves
        away from zero when that drops digits."""
        if scale >= self.scale:
            return self.coefficient * 10 ** (scale - self.scale)
        return divide_rounded(self.coefficient, 10 ** (self.scale - scale))

    def compare(self, other: Decimal) -> int:
        """-1, 0 or 1, by value: 0.3 and 0.30 are equal."""
        scale = max(self.scale, other.scale)
        a, b = self.rescaled(scale), other.rescaled(scale)
        return (a > b) - (a < b)

    def text(self) -> str:
        """Every digit of the coefficient, with the point `scale` digits from
        the right and at least one digit before it: '0.30', '-0.05', '12'."""
        digits = str(abs(self.coefficient))
        if self.scale > 0:
            digits = digits.rjust(self.scale + 1, "0")
            digits = digits[: -self.scale] + "." + digits[-self.scale :]
        return ("-" if self.coefficient < 0 else "") + digits

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Decimal) and self.compare(other) == 0

    def __lt__(self, other: Decimal) -> bool:
        return self.compare(other) < 0

    def __le__(self, other: Decimal) -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: Decimal) -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: Decimal) -> bool:
        return self.compare(other) >= 0

    def __hash__(self) -> int:
        # Equal values must hash alike, so trailing zeros are dropped first.
        coefficient, scale = self.coefficient, self.scale
        while scale > 0 and coefficient % 10 == 0:
            coefficient //= 10
            scale -= 1
        return hash((coefficient, scale))

    def __str__(self) -> str:
        return self.text()

    def __repr__(self) -> str:
        return f"Decimal({self.text()!r})"


def divide_rounded(numerator: int, denominator: int) -> int:
    """numerator / denominator to the nearest whole number, halves away from
    zero. The denominator is positive. NOT `//` or `round()`: the first floors
    and the second sends halves to even."""
    quotient, remainder = divmod(abs(numerator), denominator)
    if 2 * remainder >= denominator:
        quotient += 1
    return -quotient if numerator < 0 else quotient
