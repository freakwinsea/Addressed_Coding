"""Parser and checker: the errors matter as much as the successes.

A language whose whole pitch is legibility has to fail legibly.
"""

from __future__ import annotations

import pytest
from phonebook.checker import check
from phonebook.errors import CheckError, ParseError
from phonebook.parser import parse, split_top_level, strip_comment, unquote
from phonebook.errors import Span
from phonebook.registry import Registry

HEADER = "phonebook 0.1\n"


def build(source: str, registry: Registry):
    return check(parse(HEADER + source, "<test>"), registry)


def fails(source: str, registry: Registry, message: str):
    with pytest.raises((CheckError, ParseError), match=message):
        build(source, registry)


# --------------------------------------------------------------------------
# lexical
# --------------------------------------------------------------------------


def test_comments_stop_at_strings():
    assert strip_comment('200-0000002@[x, "#"] -> y  # note') == '200-0000002@[x, "#"] -> y  '


def test_split_respects_strings_and_brackets():
    assert split_top_level('a, "x,y", b') == ["a", ' "x,y"', " b"]
    assert split_top_level("entry: pair<text,int>") == ["entry: pair<text,int>"]


def test_escapes():
    span = Span("<test>", 1)
    assert unquote(r'"a\nb"', span) == "a\nb"
    assert unquote(r'"a\\b"', span) == "a\\b"
    with pytest.raises(ParseError, match="unknown escape"):
        unquote(r'"a\qb"', span)


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


def test_a_minimal_program_checks(registry):
    checked = build('100-0000001@["hi"]\n', registry)
    assert len(checked.body) == 1
    assert checked.effects == {"stdout"}


def test_version_selectors_parse(registry):
    checked = build('100-0000001@impl:1@["hi"]\n', registry)
    assert checked.body[0].call.selector.kind == "impl"


def test_pin_directive(registry):
    program = parse(HEADER + "pin 100-0000001 @impl:1\n100-0000001@[\"hi\"]\n", "<test>")
    assert program.pins["100-0000001"].value == 1


# --------------------------------------------------------------------------
# the errors that matter
# --------------------------------------------------------------------------


def test_unknown_address(registry):
    fails('100-9999999@["hi"]\n', registry, "no such address")


def test_quarantine_area_is_rejected(registry):
    fails('999-0000001@["hi"]\n', registry, "reserved")


def test_reserved_native_areas_are_rejected(registry):
    fails('800-0000001@["hi"]\n', registry, "reserved")


def test_wrong_arity(registry):
    fails('200-0000002@["a"]\n', registry, "takes 2 argument")


def test_type_mismatch(registry):
    fails("200-0000005@[42] -> x\n100-0000001@[x]\n", registry, "expected text, got int")


def test_unbound_reference(registry):
    fails("100-0000001@[nope]\n", registry, "not bound")


def test_single_assignment(registry):
    source = '500-0000001@["a"] -> x\n500-0000001@["b"] -> x\n100-0000001@[x]\n'
    fails(source, registry, "already bound")


def test_discarded_result_is_an_error(registry):
    fails('200-0000005@["  a  "]\n', registry, "result of .* is discarded")


def test_unit_result_cannot_be_bound(registry):
    fails('100-0000001@["hi"] -> nothing\n', registry, "produces no value")


def test_reserved_prefix(registry):
    fails('200-0000005@["a"] -> _pb_x\n100-0000001@[_pb_x]\n', registry, "reserved")


def test_local_extension_must_be_defined(registry):
    source = '300-0000001@["a"] -> items\n300-0000002@[items, 000-0000009] -> k\n100-0000002@[k]\n'
    fails(source, registry, "never defined")


def test_local_extensions_cannot_be_unreachable(registry):
    source = (
        "ext 000-0000001 UNUSED (x: text) -> text {\n"
        "  200-0000005@[x] -> y\n"
        "  return y\n"
        "}\n"
        '100-0000001@["hi"]\n'
    )
    fails(source, registry, "unused local extension")


def test_recursion_is_rejected(registry):
    source = (
        "ext 000-0000001 A (x: text) -> text {\n"
        "  000-0000002@[x] -> y\n"
        "  return y\n"
        "}\n"
        "ext 000-0000002 B (x: text) -> text {\n"
        "  000-0000001@[x] -> y\n"
        "  return y\n"
        "}\n"
        '300-0000001@["a"] -> items\n'
        "300-0000003@[items, 000-0000001] -> out\n"
        "100-0000002@[out]\n"
    )
    fails(source, registry, "cycle")


def test_duplicate_extension_names(registry):
    source = (
        "ext 000-0000001 SAME (x: text) -> text {\n  200-0000005@[x] -> y\n  return y\n}\n"
        "ext 000-0000002 SAME (x: text) -> text {\n  200-0000005@[x] -> y\n  return y\n}\n"
        '300-0000001@["a"] -> items\n'
        "300-0000003@[items, 000-0000001] -> a\n"
        "300-0000003@[a, 000-0000002] -> b\n"
        "100-0000002@[b]\n"
    )
    fails(source, registry, "both named SAME")


def test_extension_must_return_its_declared_type(registry):
    source = (
        "ext 000-0000001 BAD (x: text) -> int {\n"
        "  200-0000005@[x] -> y\n"
        "  return y\n"
        "}\n"
        '300-0000001@["a"] -> items\n'
        "300-0000003@[items, 000-0000001] -> out\n"
        "100-0000002@[out]\n"
    )
    fails(source, registry, "promises int but returns text")


def test_extensions_must_use_the_local_area(registry):
    fails(
        "ext 100-0000001 NOPE (x: text) -> text {\n  return x\n}\n",
        registry,
        "must use the 000 area code",
    )


def test_named_arguments_must_match_the_contract(registry):
    fails('200-0000002@[value="a", sep=","] -> x\n100-0000002@[x]\n', registry, "is named")


def test_constraints_are_enforced(registry):
    """SORT needs a comparable element type; a list of lists is not one."""
    source = (
        '300-0000001@["a"] -> inner\n'
        "300-0000001@[inner] -> nested\n"
        "300-0000005@[nested] -> sorted_nested\n"
        "300-0000009@[sorted_nested] -> n\n"
        "100-0000001@[n]\n"
    )
    fails(source, registry, "not comparable")


def test_contract_version_mismatch(registry):
    fails('100-0000001@contract:99@["hi"]\n', registry, "contract v")


# --------------------------------------------------------------------------
# the shipped examples
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["line_count", "word_freq", "records", "audit_demo"]
)
def test_examples_check(name, registry, root):
    from phonebook.parser import parse_file

    checked = check(parse_file(root / "examples" / f"{name}.phone"), registry)
    assert list(checked.all_calls())
