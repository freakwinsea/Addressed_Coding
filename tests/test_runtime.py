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


class TestFractionPromises:
    """Exact, lowest terms, 64-bit parts. Python's own Fraction would grow without limit."""

    def test_lowest_terms_with_the_sign_on_top(self):
        from phonebook_rt import numbers_

        half = numbers_.make_fraction(3, -6)
        assert (numbers_.numerator(half), numbers_.denominator(half)) == (-1, 2)
        zero = numbers_.make_fraction(0, -5)
        assert (numbers_.numerator(zero), numbers_.denominator(zero)) == (0, 1)
        assert numbers_.make_fraction(2, 4) == numbers_.make_fraction(-1, -2)

    def test_arithmetic_is_exact(self):
        from phonebook_rt import numbers_

        tenth = numbers_.make_fraction(1, 10)
        fifth = numbers_.make_fraction(2, 10)
        assert numbers_.add_fraction(tenth, fifth) == numbers_.make_fraction(3, 10)
        third = numbers_.make_fraction(1, 3)
        assert numbers_.sub_fraction(third, third) == numbers_.make_fraction(0, 1)
        assert numbers_.mul_fraction(third, numbers_.make_fraction(3, 1)) == numbers_.make_fraction(1, 1)
        assert numbers_.div_fraction(third, numbers_.make_fraction(-1, 2)) == numbers_.make_fraction(-2, 3)

    def test_zero_is_a_contract_error(self):
        from phonebook_rt import numbers_

        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.make_fraction(1, 0)
        assert excinfo.value.code == "division_by_zero"
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.div_fraction(numbers_.make_fraction(1, 2), numbers_.make_fraction(0, 1))
        assert excinfo.value.code == "division_by_zero"

    def test_a_result_past_64_bits_overflows(self):
        from phonebook_rt import numbers_

        big = 2**63 - 1
        near_one = numbers_.make_fraction(big - 1, big)
        nearer = numbers_.make_fraction(big - 2, big - 1)
        most_negative = numbers_.make_fraction(-(2**63), 1)
        for failing in (
            lambda: numbers_.make_fraction(-(2**63), -1),
            lambda: numbers_.sub_fraction(near_one, nearer),  # 1 / (big * (big - 1))
            lambda: numbers_.add_fraction(numbers_.make_fraction(big, 1), numbers_.make_fraction(1, 1)),
            lambda: numbers_.negate_fraction(most_negative),
            lambda: numbers_.abs_fraction(most_negative),
        ):
            with pytest.raises(PhonebookFault) as excinfo:
                failing()
            assert excinfo.value.code == "overflow"

    def test_the_working_is_wider_than_64_bits(self):
        from phonebook_rt import numbers_

        big = 2**63 - 1
        product = numbers_.mul_fraction(numbers_.make_fraction(big, 2), numbers_.make_fraction(2, big))
        assert product == numbers_.make_fraction(1, 1)

    def test_floor_goes_down_and_round_goes_away_from_zero(self):
        from phonebook_rt import numbers_

        assert numbers_.floor_fraction(numbers_.make_fraction(-7, 2)) == -4
        assert numbers_.floor_fraction(numbers_.make_fraction(7, 2)) == 3
        assert numbers_.round_fraction(numbers_.make_fraction(5, 2)) == 3  # round() says 2
        assert numbers_.round_fraction(numbers_.make_fraction(-5, 2)) == -3
        assert numbers_.round_fraction(numbers_.make_fraction(-(2**63), 1)) == -(2**63)

    def test_to_float_rounds_once(self):
        from phonebook_rt import numbers_

        value = numbers_.make_fraction(9007199254740993, 7)
        assert numbers_.fraction_to_float(value) == 1286742750677284.8
        assert 9007199254740993.0 / 7.0 != 1286742750677284.8  # the float route is off
        assert str(numbers_.fraction_to_float(numbers_.make_fraction(0, 1))) == "0.0"

    def test_prints_in_lowest_terms_and_reads_back(self):
        from phonebook_rt import core, numbers_

        zero = numbers_.make_fraction(0, 1)
        for n, d, text in ((1, 3, "1/3"), (-5, 2, "-5/2"), (4, 2, "2"), (0, 7, "0")):
            value = numbers_.make_fraction(n, d)
            assert core.to_text(value) == text
            assert numbers_.parse_fraction(text, zero) == value
        assert core.to_text([numbers_.make_fraction(1, 2)]) == "[1/2]"

    def test_parse_accepts_only_the_pinned_shape(self):
        from phonebook_rt import numbers_

        fallback = numbers_.make_fraction(-1, 1)
        assert numbers_.parse_fraction(" +2/4 ", fallback) == numbers_.make_fraction(1, 2)
        for text in ("1 / 3", "1/-3", "1/0", "1.5", "/3", "1/", "", "1_0/3", "9223372036854775808/2", "١/٣"):
            assert numbers_.parse_fraction(text, fallback) is fallback, text

    def test_fractions_order_and_key_by_value(self):
        from phonebook_rt import collections_, numbers_

        half = numbers_.make_fraction(1, 2)
        third = numbers_.make_fraction(1, 3)
        assert collections_.sort_seq([half, third]) == [third, half]
        assert numbers_.make_fraction(2, 4) in {half}
        tallies = collections_.count_occurrences([half, third, numbers_.make_fraction(2, 4)])
        assert collections_.entries(tallies) == [(third, 1), (half, 2)]


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


class TestRootsAndRemainders:
    """SQRT and SQRT_DEC are worked out by hand, so each gets an oracle used
    only here: `math.sqrt` for the float, which IEEE 754 requires to be
    correctly rounded, and exact `Fraction` bounds for the decimal. The
    conformance suite then holds Rust to whatever Python prints."""

    def test_sqrt_is_the_correctly_rounded_root(self):
        import math
        import random
        import struct

        from phonebook_rt import numbers_

        rng = random.Random(140)
        values = [5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 2.0, 0.5]
        for _ in range(50_000):
            (value,) = struct.unpack("<d", struct.pack("<Q", rng.getrandbits(63)))
            if math.isfinite(value):
                values.append(value)
        for value in values:
            assert numbers_.sqrt_(value) == math.sqrt(value), value

    def test_sqrt_dec_is_the_nearest_at_its_places(self):
        import random
        from fractions import Fraction

        from phonebook_rt import numbers_

        rng = random.Random(146)
        for _ in range(2_000):
            value = Decimal(rng.choice([rng.randrange(10**30), rng.randrange(1000) ** 2]), rng.randrange(12))
            places = rng.choice([0, 1, 2, 5, 12])
            root = numbers_.sqrt_dec(value, places)
            assert root.scale == places
            exact, half = Fraction(value.coefficient, 10**value.scale), Fraction(1, 2 * 10**places)
            middle = Fraction(root.coefficient, 10**places)
            # Halves away from zero: the root may sit exactly on the lower edge.
            assert max(middle - half, 0) ** 2 <= exact < (middle + half) ** 2

    def test_remainders_follow_the_dividend(self):
        import math
        import random
        from fractions import Fraction

        from phonebook_rt import numbers_

        def expected(a, b):
            quotient = a / b
            return a - b * (math.floor(quotient) if quotient >= 0 else math.ceil(quotient))

        rng = random.Random(149)
        for _ in range(2_000):
            a = Decimal(rng.randrange(-(10**12), 10**12), rng.randrange(6))
            b = Decimal(rng.choice([-1, 1]) * rng.randrange(1, 10**8), rng.randrange(6))
            result = numbers_.mod_dec(a, b)
            exact_a, exact_b = (Fraction(x.coefficient, 10**x.scale) for x in (a, b))
            assert Fraction(result.coefficient, 10**result.scale) == expected(exact_a, exact_b)
            assert result.scale == max(a.scale, b.scale)

            p, q = rng.randrange(-(10**9), 10**9), rng.randrange(1, 10**9)
            r, s = rng.choice([-1, 1]) * rng.randrange(1, 10**9), rng.randrange(1, 10**9)
            got = numbers_.mod_fraction(numbers_.make_fraction(p, q), numbers_.make_fraction(r, s))
            assert Fraction(got.numerator, got.denominator) == expected(Fraction(p, q), Fraction(r, s))
            assert numbers_.ceil_fraction(numbers_.make_fraction(p, q)) == math.ceil(Fraction(p, q))

    def test_whole_decimals(self):
        import math
        import random
        from fractions import Fraction

        from phonebook_rt import numbers_

        rng = random.Random(147)
        for _ in range(2_000):
            value = Decimal(rng.randrange(-(10**15), 10**15), rng.randrange(8))
            exact = Fraction(value.coefficient, 10**value.scale)
            assert numbers_.floor_dec(value).coefficient == math.floor(exact)
            assert numbers_.ceil_dec(value).coefficient == math.ceil(exact)
            assert numbers_.floor_dec(value).scale == numbers_.ceil_dec(value).scale == 0

    def test_mod_fraction_overflow_is_a_contract_error(self):
        from phonebook_rt import numbers_

        a = numbers_.make_fraction(1, 4294967311)  # two large primes: the
        b = numbers_.make_fraction(1, 4294967357)  # shared denominator is too big
        with pytest.raises(PhonebookFault) as excinfo:
            numbers_.mod_fraction(a, b)
        assert excinfo.value.code == "overflow"
