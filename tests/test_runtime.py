"""Run every value-level conformance case in the registry against the Python runtime.

These are the cases written into the entries themselves, so a contract note and
its test live in the same file and move together.
"""

from __future__ import annotations

import pytest
from phonebook.registry import Registry
from phonebook_rt import IMPLEMENTATIONS, PhonebookFault
from phonebook_rt.decimal_ import Decimal


def normalize(value):
    """JSON has no tuples and no distinction between our pairs and lists.

    Floats are tagged so that an int result never passes for an expected float
    just because 3 == 3.0 in Python.
    """
    if isinstance(value, float):
        return ("float", value)
    if isinstance(value, Decimal):
        return ("decimal", value.text())
    if isinstance(value, tuple):
        return [normalize(v) for v in value]
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    return value


def collect_cases():
    registry = Registry.load()
    for entry in registry:
        for case in entry.conformance:
            yield pytest.param(entry, case, id=f"{entry.name}:{case['id']}")


def decimals_from_text(types, values):
    """JSON has no decimal, so a case writes one as its text: "0.30"."""
    return [
        Decimal.literal(value) if index < len(types) and types[index].name == "decimal" else value
        for index, value in enumerate(values)
    ]


@pytest.mark.parametrize("entry,case", list(collect_cases()))
def test_registry_conformance_case(entry, case: dict):
    implementation = IMPLEMENTATIONS[entry.address]
    args = decimals_from_text([i.type for i in entry.contract.inputs], case["args"])
    if case.get("raises"):
        with pytest.raises(PhonebookFault) as excinfo:
            implementation(*args)
        assert excinfo.value.code == case["raises"]
        return
    (expect,) = decimals_from_text([entry.contract.output.type], [case["expect"]])
    assert normalize(implementation(*args)) == normalize(expect)


def test_every_address_has_a_python_implementation(registry: Registry):
    missing = [e.label for e in registry if e.address not in IMPLEMENTATIONS]
    assert missing == []


def test_no_orphan_implementations(registry: Registry):
    orphans = [a for a in IMPLEMENTATIONS if a not in registry]
    assert orphans == []


class TestContractsThatOverrideTheHostLanguage:
    """Places where the runtime had to disagree with Python to keep a promise."""

    def test_div_truncates_toward_zero_not_floor(self):
        from phonebook_rt import numbers_

        assert numbers_.div(-7, 2) == -3  # Python's // would say -4
        assert -7 // 2 == -4

    def test_mod_takes_the_dividend_sign(self):
        from phonebook_rt import numbers_

        assert numbers_.mod(-7, 2) == -1  # Python's % would say 1
        assert -7 % 2 == 1

    def test_div_and_mod_are_coherent(self):
        from phonebook_rt import numbers_

        for a in (-9, -7, -1, 0, 1, 7, 9):
            for b in (-3, -2, 2, 3):
                assert a == numbers_.div(a, b) * b + numbers_.mod(a, b)

    def test_to_text_renders_lowercase_booleans(self):
        from phonebook_rt import core

        assert core.to_text(True) == "true"  # Python's str() would say "True"
        assert str(True) == "True"

    def test_lowercase_is_ascii_only(self):
        from phonebook_rt import text

        assert text.lowercase("ÄbC") == "Äbc"
        assert "ÄbC".lower() == "äbc"

    def test_split_words_uses_the_ascii_whitespace_set(self):
        from phonebook_rt import text

        # U+00A0 is whitespace to Python's str.split() but not to the contract.
        assert text.split_words("a b") == ["a b"]
        assert "a b".split() == ["a", "b"]

    def test_overflow_is_an_error_not_a_bignum(self):
        from phonebook_rt import numbers_

        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.add(numbers_.INT64_MAX, 1)
        assert excinfo.value.code == "overflow"

    @pytest.mark.parametrize("name", ["abs_", "negate"])
    def test_abs_and_negate_overflow_on_the_smallest_int(self, name):
        from phonebook_rt import numbers_

        with pytest.raises(PhonebookFault) as excinfo:
            getattr(numbers_, name)(numbers_.INT64_MIN)
        assert excinfo.value.code == "overflow"
        assert abs(numbers_.INT64_MIN) == numbers_.INT64_MAX + 1  # Python would not

    def test_pow_agrees_with_python_wherever_the_result_fits(self):
        from phonebook_rt import numbers_

        for base in range(-12, 13):
            for exponent in range(0, 70):
                true = base**exponent
                if numbers_.INT64_MIN <= true <= numbers_.INT64_MAX:
                    assert numbers_.pow_(base, exponent) == true, (base, exponent)
                else:
                    with pytest.raises(PhonebookFault) as excinfo:
                        numbers_.pow_(base, exponent)
                    assert excinfo.value.code == "overflow", (base, exponent)

    def test_pow_fails_fast_instead_of_building_a_bignum(self):
        from phonebook_rt import numbers_

        # Python's ** would try to build a number with ~2.8e18 digits.
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.pow_(10, numbers_.INT64_MAX)
        assert excinfo.value.code == "overflow"

    def test_clamp_with_a_reversed_range_is_a_contract_error(self):
        from phonebook_rt import numbers_

        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.clamp(5, 10, 0)
        assert excinfo.value.code == "invalid_range"

    def test_gcd_and_lcm_agree_with_math_wherever_the_result_fits(self):
        import math

        from phonebook_rt import numbers_

        edges = [numbers_.INT64_MIN, numbers_.INT64_MIN + 1, -(2**32), -12, -1, 0,
                 1, 6, 18, 2**32, numbers_.INT64_MAX]
        for a in edges + list(range(-30, 31)):
            for b in edges + list(range(-30, 31)):
                for name, true in (("gcd", math.gcd(a, b)), ("lcm", math.lcm(a, b))):
                    if true <= numbers_.INT64_MAX:
                        assert getattr(numbers_, name)(a, b) == true, (name, a, b)
                    else:
                        with pytest.raises(PhonebookFault) as excinfo:
                            getattr(numbers_, name)(a, b)
                        assert excinfo.value.code == "overflow", (name, a, b)

    def test_product_overflows_before_a_later_zero(self):
        from phonebook_rt import numbers_

        assert numbers_.product([]) == 1
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.product([numbers_.INT64_MAX, 2, 0])
        assert excinfo.value.code == "overflow"

    def test_parity_holds_for_negatives(self):
        from phonebook_rt import numbers_

        for a in list(range(-20, 21)) + [numbers_.INT64_MIN, numbers_.INT64_MAX]:
            assert numbers_.is_even(a) == (a % 2 == 0), a
            assert numbers_.is_odd(a) != numbers_.is_even(a), a


class TestFloatPromises:
    """Where Python's own float behavior is not the contract."""

    def test_round_sends_halves_away_from_zero(self):
        from phonebook_rt import numbers_

        assert numbers_.round_(2.5) == 3.0  # Python's round() would say 2
        assert round(2.5) == 2
        assert numbers_.round_(-2.5) == -3.0
        assert numbers_.round_(0.49999999999999994) == 0.0  # floor(x + 0.5) says 1.0

    def test_no_negative_zero(self):
        import math

        from phonebook_rt import numbers_

        for result in (
            numbers_.mul_float(-2.0, 0.0),
            numbers_.sub_float(0.0, 0.0),
            numbers_.round_(-0.4),
            numbers_.parse_float("-0", 1.0),
            numbers_.div_float(-5e-324, 2.0),
        ):
            assert result == 0.0 and math.copysign(1.0, result) == 1.0

    def test_nan_and_infinity_never_exist(self):
        from phonebook_rt import numbers_

        for text in ("nan", "NaN", "inf", "-inf", "infinity", "1e400"):
            assert numbers_.parse_float(text, -1.0) == -1.0
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.div_float(0.0, 0.0)
        assert excinfo.value.code == "division_by_zero"
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.mul_float(1e300, 1e300)
        assert excinfo.value.code == "overflow"

    def test_parse_float_rejects_what_float_accepts(self):
        from phonebook_rt import numbers_

        for text in ("1_000.5", ".5", "5.", "0x1p3", "1e", "+", " "):
            assert numbers_.parse_float(text, -1.0) == -1.0, text

    def test_to_int_never_saturates(self):
        from phonebook_rt import numbers_

        assert numbers_.to_int(-9.223372036854775808e18) == numbers_.INT64_MIN
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.to_int(9.223372036854775808e18)
        assert excinfo.value.code == "overflow"

    def test_float_text_matches_repr(self):
        """The layout is written by hand; repr is the independent check of it."""
        import random
        import struct

        from phonebook_rt import numbers_

        rng = random.Random(0)
        checked = 0
        while checked < 20000:
            bits = rng.getrandbits(64).to_bytes(8, "little")
            value = struct.unpack("<d", bits)[0]
            if value != value or value in (float("inf"), float("-inf")) or value == 0.0:
                continue
            assert numbers_.float_text(value) == repr(value)
            checked += 1

    def test_float_text_layout_boundaries(self):
        from phonebook_rt import core

        assert core.to_text(0.0) == "0.0"
        assert core.to_text(0.0001) == "0.0001"
        assert core.to_text(0.00001) == "1e-05"
        assert core.to_text(1e15) == "1000000000000000.0"
        assert core.to_text(1e16) == "1e+16"
        assert core.to_text(1e100) == "1e+100"
        assert core.to_text([1.0, -0.5]) == "[1.0, -0.5]"
        # A tie between two shortest candidates goes to the even digit.
        assert core.to_text(635057293855503.25) == "635057293855503.2"


class TestOrderingPromises:
    def test_entries_sorts_by_key(self):
        from phonebook_rt import collections_

        assert collections_.entries({"b": 1, "a": 2}) == [("a", 2), ("b", 1)]

    def test_unique_keeps_first_occurrence_order(self):
        from phonebook_rt import collections_

        assert collections_.unique(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]

    def test_sort_by_is_stable_when_descending(self):
        from phonebook_rt import collections_

        pairs = [("a", 1), ("b", 1), ("c", 2)]
        ranked = collections_.sort_by(pairs, lambda p: p[1], True)
        assert ranked == [("c", 2), ("a", 1), ("b", 1)]


class TestCsvStateMachine:
    def test_quotes_commas_and_short_rows(self, tmp_path):
        from phonebook_rt import io_

        source = tmp_path / "in.csv"
        source.write_text(
            'name,note\nAda,"has, a comma"\nGrace,"says ""hi"""\nShort\n',
            encoding="utf-8",
            newline="",
        )
        rows = io_.read_csv(str(source))
        assert rows == [
            {"name": "Ada", "note": "has, a comma"},
            {"name": "Grace", "note": 'says "hi"'},
            {"name": "Short", "note": ""},
        ]

    def test_round_trip_is_byte_stable(self, tmp_path):
        from phonebook_rt import io_

        rows = [{"a": "x,y", "b": 'q"z'}, {"a": "plain", "b": ""}]
        out = tmp_path / "out.csv"
        io_.write_csv(str(out), rows, ["a", "b"])
        assert out.read_bytes() == b'a,b\n"x,y","q""z"\nplain,\n'
        assert io_.read_csv(str(out)) == rows

    def test_too_many_cells_is_a_contract_error(self, tmp_path):
        from phonebook_rt import io_

        source = tmp_path / "wide.csv"
        source.write_text("a,b\n1,2,3\n", encoding="utf-8", newline="")
        with pytest.raises(PhonebookFault) as excinfo:
            io_.read_csv(str(source))
        assert excinfo.value.code == "malformed_csv"


class TestDecimalAgainstFractions:
    """The Python decimal is hand-written, so it gets an oracle of its own:
    the standard library's exact `Fraction`, used here only, never by a runtime.
    The conformance suite then holds Rust to whatever Python prints."""

    @staticmethod
    def operands(seed: int, count: int = 300):
        import random

        rng = random.Random(seed)
        for _ in range(count):
            pair = []
            for _ in range(2):
                scale = rng.choice([0, 1, 2, 3, 9, 10, 25])
                coefficient = rng.choice(
                    [0, 5, 10**9 - 1, 10**9, rng.randrange(10**30), 5 * 10 ** rng.randrange(20)]
                )
                pair.append(Decimal(-coefficient if rng.random() < 0.5 else coefficient, scale))
            yield pair

    @staticmethod
    def exact(value: Decimal):
        from fractions import Fraction

        return Fraction(value.coefficient, 10**value.scale)

    @staticmethod
    def rounded(value, places: int):
        """Half away from zero, the contract's rule, done on a Fraction."""
        import math
        from fractions import Fraction

        scaled = abs(value) * 10**places
        whole = math.floor(scaled + Fraction(1, 2))
        return Fraction(-whole if value < 0 else whole, 10**places)

    def test_arithmetic(self):
        from phonebook_rt import numbers_

        for a, b in self.operands(1):
            scale = max(a.scale, b.scale)
            for function, expected in (
                (numbers_.add_dec, self.exact(a) + self.exact(b)),
                (numbers_.sub_dec, self.exact(a) - self.exact(b)),
            ):
                result = function(a, b)
                assert (self.exact(result), result.scale) == (expected, scale)
            product = numbers_.mul_dec(a, b)
            assert self.exact(product) == self.exact(a) * self.exact(b)
            assert product.scale == a.scale + b.scale

    def test_division_and_rounding(self):
        from phonebook_rt import numbers_

        for places in (0, 1, 2, 7):
            for a, b in self.operands(places + 2):
                rounded = numbers_.round_dec(a, places)
                assert rounded.scale == places
                assert self.exact(rounded) == self.rounded(self.exact(a), places)
                if b.coefficient == 0:
                    continue
                quotient = numbers_.div_dec(a, b, places)
                assert quotient.scale == places
                assert self.exact(quotient) == self.rounded(self.exact(a) / self.exact(b), places)

    def test_text_round_trips(self):
        for a, _ in self.operands(9):
            assert Decimal.parse(a.text()).text() == a.text()
            assert self.exact(Decimal.parse(a.text())) == self.exact(a)
