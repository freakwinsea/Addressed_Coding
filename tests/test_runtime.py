"""Run every value-level conformance case in the registry against the Python runtime.

These are the cases written into the entries themselves, so a contract note and
its test live in the same file and move together.
"""

from __future__ import annotations

import pytest
from phonebook.registry import Registry
from phonebook_rt import IMPLEMENTATIONS, PhonebookFault


def normalize(value):
    """JSON has no tuples and no distinction between our pairs and lists."""
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
            yield pytest.param(entry.address, case, id=f"{entry.name}:{case['id']}")


@pytest.mark.parametrize("address,case", list(collect_cases()))
def test_registry_conformance_case(address: str, case: dict):
    implementation = IMPLEMENTATIONS[address]
    if case.get("raises"):
        with pytest.raises(PhonebookFault) as excinfo:
            implementation(*case["args"])
        assert excinfo.value.code == case["raises"]
        return
    assert normalize(implementation(*case["args"])) == normalize(case["expect"])


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
