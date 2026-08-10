"""The registry has to be trustworthy before anything built on it can be."""

from __future__ import annotations

import json

import pytest
from phonebook.registry import Registry, area_of, contract_hash, lint
from phonebook.types import parse_type


def test_loads_every_area(registry: Registry):
    assert len(registry) == 54
    assert {e.area for e in registry} == {"100", "200", "300", "400", "500", "600"}


def test_lint_is_clean(registry: Registry):
    assert lint(registry) == []


def test_addresses_and_names_are_unique(registry: Registry):
    addresses = [e.address for e in registry]
    names = [e.name for e in registry]
    assert len(set(addresses)) == len(addresses)
    assert len(set(names)) == len(names)


def test_every_entry_parses_its_own_types(registry: Registry):
    for entry in registry:
        for param in entry.contract.inputs:
            assert parse_type(str(param.type))
        assert parse_type(str(entry.contract.output.type))


def test_only_area_500_touches_the_filesystem(registry: Registry):
    for entry in registry:
        outside = set(entry.contract.effects) - {"stdout"}
        assert not outside or entry.area == "500", entry.label


def test_effects_and_purity_agree(registry: Registry):
    for entry in registry:
        declared = bool(entry.contract.effects)
        assert declared == (entry.contract.purity == "effectful"), entry.label


def test_conformance_cases_are_well_formed(registry: Registry):
    for entry in registry:
        for case in entry.conformance:
            assert isinstance(case["args"], list), entry.label
            assert "id" in case


def test_schema_file_matches_the_loader(root):
    """The published schema and the hand-written loader must agree on required fields."""
    schema = json.loads((root / "phonebook" / "schema" / "entry.schema.json").read_text("utf-8"))
    assert set(schema["required"]) == {
        "address",
        "name",
        "summary",
        "keywords",
        "contract",
        "status",
        "since",
    }


class TestImmutabilityLedger:
    """The rule the whole design rests on, enforced rather than promised."""

    def test_ledger_holds(self, registry: Registry):
        assert registry.verify_frozen() == []

    def test_every_issued_contract_is_recorded(self, registry: Registry):
        ledger = registry.load_frozen()
        for entry in registry:
            key = f"{entry.address}@contract:{entry.contract.version}"
            assert key in ledger, f"{entry.label} was never frozen"
            assert ledger[key] == contract_hash(entry)

    def test_a_changed_contract_is_detected(self, registry: Registry, monkeypatch):
        """Silently widening a promise must fail, which is the entire point."""
        entry = registry.require("300-0000002")
        original = json.dumps(entry.raw["contract"], sort_keys=True)
        entry.raw["contract"]["errors"] = ["predicate_failure", "quietly_added"]
        try:
            problems = registry.verify_frozen()
            assert any("CHANGED without a version bump" in p for p in problems)
        finally:
            entry.raw["contract"].update(json.loads(original))
            entry.raw["contract"]["errors"] = ["predicate_failure"]
        assert registry.verify_frozen() == []

    def test_freeze_refuses_to_rewrite_history(self, registry: Registry):
        entry = registry.require("100-0000001")
        entry.raw["contract"]["errors"] = ["something_new"]
        try:
            with pytest.raises(Exception, match="refusing to freeze"):
                registry.freeze()
        finally:
            entry.raw["contract"]["errors"] = []


def test_area_of_rejects_nonsense():
    with pytest.raises(Exception):
        area_of("12-345")
