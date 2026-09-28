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


def test_int_literals_must_fit_in_64_bits(registry):
    fails("100-0000005@[9223372036854775808] -> t\n100-0000001@[t]\n", registry, "64-bit")
    fails("100-0000005@[-9223372036854775809] -> t\n100-0000001@[t]\n", registry, "64-bit")


def test_int_literals_at_the_64_bit_limits_are_accepted(registry):
    build("100-0000005@[9223372036854775807] -> t\n100-0000001@[t]\n", registry)
    build("100-0000005@[-9223372036854775808] -> t\n100-0000001@[t]\n", registry)


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


def test_float_literals(registry):
    checked = build("400-0000015@[1.5, -2e3] -> total\n100-0000001@[total]\n", registry)
    literals = [arg.value for arg in checked.body[0].call.args]
    assert literals == [1.5, -2000.0]
    assert all(type(value) is float for value in literals)


def test_float_literal_negative_zero_is_zero(registry):
    checked = build("400-0000015@[-0.0, 1.0] -> total\n100-0000001@[total]\n", registry)
    assert str(checked.body[0].call.args[0].value) == "0.0"


def test_float_literal_must_be_finite(registry):
    fails("400-0000015@[1e999, 1.0] -> total\n100-0000001@[total]\n", registry, "finite")


def test_int_and_float_do_not_mix(registry):
    fails("400-0000015@[1, 2.0] -> total\n100-0000001@[total]\n", registry, "expected float, got int")
    fails("400-0000001@[1, 2.0] -> total\n100-0000001@[total]\n", registry, "expected int, got float")


def test_floats_are_comparable_but_not_keyable(registry):
    build("300-0000001@[2.5, 1.0] -> xs\n300-0000005@[xs] -> ys\n100-0000001@[ys]\n", registry)
    fails(
        "300-0000001@[2.5, 1.0] -> xs\n300-0000008@[xs] -> ys\n100-0000001@[ys]\n",
        registry,
        "not keyable",
    )


def test_bigint_literals(registry):
    checked = build(
        "400-0000025@[123456789012345678901234567890n, -0n] -> total\n100-0000001@[total]\n",
        registry,
    )
    args = checked.body[0].call.args
    assert [arg.value for arg in args] == [123456789012345678901234567890, 0]
    assert all(arg.type.name == "bigint" for arg in args)


def test_bigint_literal_has_a_ceiling(registry):
    build(f"400-0000025@[{'9' * 4000}n, 1n] -> total\n100-0000001@[total]\n", registry)
    build(f"400-0000025@[-{'0' * 50}{'9' * 4000}n, 1n] -> total\n100-0000001@[total]\n", registry)
    fails(
        f"400-0000025@[1{'0' * 4000}n, 1n] -> total\n100-0000001@[total]\n",
        registry,
        "4001 digits",
    )


def test_int_and_bigint_do_not_mix(registry):
    fails("400-0000025@[1, 2n] -> total\n100-0000001@[total]\n", registry, "expected bigint, got int")
    fails("400-0000001@[1, 2n] -> total\n100-0000001@[total]\n", registry, "expected int, got bigint")


def test_bigints_are_comparable_and_keyable(registry):
    build("300-0000001@[2n, 1n] -> xs\n300-0000005@[xs] -> ys\n100-0000001@[ys]\n", registry)
    build("300-0000001@[2n, 1n] -> xs\n300-0000008@[xs] -> ys\n100-0000001@[ys]\n", registry)
    build("600-0000004@[2n, 1n] -> same\n100-0000001@[same]\n", registry)


def test_decimal_literals(registry):
    checked = build(
        "400-0000043@[0.10d, -0.00d] -> a\n400-0000043@[007.50d, -3d] -> b\n"
        "100-0000001@[a]\n100-0000001@[b]\n",
        registry,
    )
    args = checked.body[0].call.args + checked.body[1].call.args
    # Kept as canonical digits: places stay, leading zeros and the sign of zero go.
    assert [arg.value for arg in args] == ["0.10", "0.00", "7.50", "-3"]
    assert all(arg.type.name == "decimal" for arg in args)


def test_decimal_literal_has_ceilings(registry):
    build(f"400-0000043@[{'9' * 3000}.{'9' * 1000}d, 1d] -> a\n100-0000001@[a]\n", registry)
    fails(f"400-0000043@[{'9' * 3001}.{'9' * 1000}d, 1d] -> a\n100-0000001@[a]\n", registry,
          "4001 digits")
    fails(f"400-0000043@[0.{'0' * 1001}d, 1d] -> a\n100-0000001@[a]\n", registry,
          "1001 digits after the point")


def test_decimal_does_not_mix(registry):
    fails("400-0000043@[1d, 2] -> a\n100-0000001@[a]\n", registry, "expected decimal, got int")
    fails("400-0000043@[1d, 2.0] -> a\n100-0000001@[a]\n", registry, "expected decimal, got float")
    fails("400-0000015@[1.0, 2.0d] -> a\n100-0000001@[a]\n", registry, "expected float, got decimal")


def test_decimals_are_comparable_but_not_keyable(registry):
    build("300-0000001@[0.2d, 0.1d] -> xs\n300-0000005@[xs] -> ys\n100-0000001@[ys]\n", registry)
    build("600-0000005@[0.2d, 0.1d] -> less\n100-0000001@[less]\n", registry)
    fails("600-0000004@[0.2d, 0.20d] -> same\n100-0000001@[same]\n", registry, "keyable")
    fails("300-0000001@[0.2d, 0.1d] -> xs\n300-0000008@[xs] -> ys\n100-0000001@[ys]\n",
          registry, "keyable")


def test_number_comparisons_take_numbers_only(registry):
    """NUMBER_EQUALS takes ints and floats, never text, and never one of each."""
    build("400-0000060@[0.5, 0.5] -> same\n100-0000001@[same]\n", registry)
    build("400-0000064@[1, 2] -> order\n100-0000001@[order]\n", registry)
    fails('400-0000062@["a", "b"] -> le\n100-0000001@[le]\n', registry, "not numeric")
    fails("400-0000060@[1, 1.0] -> same\n100-0000001@[same]\n", registry, "expected int, got float")


def test_number_comparisons_take_the_exact_types_too(registry):
    """bigint, decimal and fraction are numeric; mixing two of them still fails."""
    build("400-0000060@[1n, 2n] -> same\n100-0000001@[same]\n", registry)
    build("400-0000064@[0.3d, 0.30d] -> order\n100-0000001@[order]\n", registry)
    build("400-0000080@[1, 3] -> third\n400-0000062@[third, third] -> le\n100-0000001@[le]\n",
          registry)
    fails("400-0000060@[1n, 1d] -> same\n100-0000001@[same]\n", registry, "expected bigint, got decimal")


def test_fractions_are_their_own_type(registry):
    build("400-0000080@[1, 3] -> third\n400-0000081@[third, third] -> both\n100-0000001@[both]\n", registry)
    fails("400-0000080@[1, 3] -> third\n400-0000001@[third, 1] -> x\n100-0000001@[x]\n", registry, "expected int, got fraction")
    fails("400-0000081@[1, 2] -> x\n100-0000001@[x]\n", registry, "expected fraction, got int")


def test_fractions_are_comparable_and_keyable(registry):
    build(
        "400-0000080@[1, 3] -> a\n400-0000080@[1, 2] -> b\n300-0000001@[a, b] -> xs\n"
        "300-0000005@[xs] -> ys\n300-0000008@[xs] -> zs\n600-0000004@[a, b] -> same\n"
        "100-0000001@[ys]\n100-0000001@[zs]\n100-0000001@[same]\n",
        registry,
    )


def test_contract_version_mismatch(registry):
    fails('100-0000001@contract:99@["hi"]\n', registry, "contract v")


# --------------------------------------------------------------------------
# the shipped examples
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["line_count", "word_freq", "records", "audit_demo", "big_numbers", "money"]
)
def test_examples_check(name, registry, root):
    from phonebook.parser import parse_file

    checked = check(parse_file(root / "examples" / f"{name}.phone"), registry)
    assert list(checked.all_calls())
