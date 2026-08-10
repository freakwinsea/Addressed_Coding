"""The audit model: what it proves, and what it deliberately does not."""

from __future__ import annotations

from phonebook.audit import audit, render
from phonebook.checker import check
from phonebook.parser import parse, parse_file

HEADER = "phonebook 0.1\n"


def test_capabilities_are_computed_from_frozen_contracts(registry, root):
    checked = check(parse_file(root / "examples" / "audit_demo.phone"), registry)
    report = audit(checked)
    assert set(report.capabilities) == {"filesystem-read", "filesystem-write", "stdout"}
    assert report.sensitive == {"filesystem-read", "filesystem-write"}
    assert report.needs_review


def test_every_local_extension_is_listed_with_its_source(registry, root):
    checked = check(parse_file(root / "examples" / "audit_demo.phone"), registry)
    report = audit(checked)
    assert len(report.local_extensions) == 2
    text = render(report)
    assert "NOT_BLANK" in text and "TIDY" in text
    # The complete body must be quoted, not just the signature: the review
    # surface is only useful if it contains the thing you have to review.
    assert '200-0000008@[line, "a", "@"]' in text


def test_intent_flow_is_readable_without_reading_code(registry, root):
    checked = check(parse_file(root / "examples" / "audit_demo.phone"), registry)
    text = render(audit(checked))
    for name in ("READ_TEXT_FILE", "SPLIT_LINES", "FILTER", "MAP", "WRITE_TEXT_FILE"):
        assert name in text


def test_literals_never_break_the_report_layout(registry, root):
    """A newline inside a string must not reflow the intent table."""
    checked = check(parse_file(root / "examples" / "audit_demo.phone"), registry)
    text = render(audit(checked))
    intent = text.split("INTENT")[1].split("LOCAL EXTENSIONS")[0]
    assert '"\\n"' in intent
    for line in intent.splitlines():
        assert not line.startswith('"')


def test_a_pure_program_needs_no_review(registry):
    source = HEADER + '300-0000001@["a", "b"] -> items\n300-0000009@[items] -> n\n100-0000001@[n]\n'
    report = audit(check(parse(source, "<test>"), registry))
    assert not report.needs_review
    assert "no local code" in render(report)


def test_a_computed_path_is_flagged(registry):
    source = (
        HEADER
        + '500-0000001@["examples/data/notes.txt"] -> name\n'
        + "500-0000001@[name] -> body\n"
        + "100-0000001@[body]\n"
    )
    report = audit(check(parse(source, "<test>"), registry))
    kinds = {f.kind for f in report.findings}
    assert "dynamic-path" in kinds


def test_unpinned_addresses_are_reported(registry):
    source = HEADER + '100-0000001@["hi"]\n'
    report = audit(check(parse(source, "<test>"), registry))
    assert report.unpinned == ["100-0000001"]

    pinned = HEADER + 'pin 100-0000001 @impl:1\n100-0000001@["hi"]\n'
    assert audit(check(parse(pinned, "<test>"), registry)).unpinned == []


def test_audit_does_not_claim_local_code_is_safe(registry, root):
    """The report's honesty is part of its value; keep the wording checked."""
    checked = check(parse_file(root / "examples" / "audit_demo.phone"), registry)
    text = render(checked and audit(checked))
    assert "complete review surface" in text
    assert "safe" not in text.lower().replace("unsafe", "")
