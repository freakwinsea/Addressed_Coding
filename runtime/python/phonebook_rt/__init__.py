"""The Python runtime: one function per phonebook address.

There is exactly one Python implementation of each address, and both the
interpreter and the generated Python call it. That is not an optimization — it
means `dial run` and `dial emit --target python` cannot drift apart, so the
only genuinely independent implementation in the project is the Rust one, which
is precisely what the conformance suite is there to test.
"""

from __future__ import annotations

import sys

from . import collections_, core, io_, logic_, numbers_, text
from .faults import PhonebookFault

__all__ = ["collections_", "core", "io_", "logic_", "numbers_", "text", "PhonebookFault", "call"]


def _use_lf_line_endings() -> None:
    """Make PRINT mean U+000A everywhere, including Windows.

    Python translates '\\n' to '\\r\\n' on Windows text streams by default,
    which would make the same program produce different bytes on different
    platforms. The contract for PRINT says one line feed, so the runtime
    enforces it at the stream rather than leaving it to each caller.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(newline="\n", encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - exotic streams
                pass


_use_lf_line_endings()


#: address -> runtime function, the table the interpreter and resolver share.
IMPLEMENTATIONS = {
    "100-0000001": core.print_value,
    "100-0000002": core.print_lines,
    "100-0000003": core.select,
    "100-0000004": core.identity,
    "100-0000005": core.to_text,
    "100-0000006": core.assert_,
    "200-0000001": text.split_lines,
    "200-0000002": text.split,
    "200-0000003": text.split_words,
    "200-0000004": text.join,
    "200-0000005": text.trim,
    "200-0000006": text.lowercase,
    "200-0000007": text.uppercase,
    "200-0000008": text.replace,
    "200-0000009": text.contains,
    "200-0000010": text.starts_with,
    "200-0000011": text.length,
    "200-0000012": text.slice_,
    "300-0000001": collections_.make_list,
    "300-0000002": collections_.filter_seq,
    "300-0000003": collections_.map_seq,
    "300-0000004": collections_.reduce_seq,
    "300-0000005": collections_.sort_seq,
    "300-0000006": collections_.sort_by,
    "300-0000007": collections_.reverse_seq,
    "300-0000008": collections_.unique,
    "300-0000009": collections_.count,
    "300-0000010": collections_.take,
    "300-0000011": collections_.first,
    "300-0000012": collections_.count_occurrences,
    "300-0000013": collections_.entries,
    "300-0000014": collections_.get,
    "300-0000015": collections_.pair_key,
    "300-0000016": collections_.pair_value,
    "400-0000001": numbers_.add,
    "400-0000002": numbers_.sub,
    "400-0000003": numbers_.mul,
    "400-0000004": numbers_.div,
    "400-0000005": numbers_.mod,
    "400-0000006": numbers_.min_,
    "400-0000007": numbers_.max_,
    "400-0000008": numbers_.sum_,
    "400-0000009": numbers_.parse_int,
    "400-0000010": numbers_.abs_,
    "400-0000011": numbers_.negate,
    "400-0000012": numbers_.pow_,
    "400-0000013": numbers_.clamp,
    "400-0000014": numbers_.sign,
    "400-0000015": numbers_.add_float,
    "400-0000016": numbers_.sub_float,
    "400-0000017": numbers_.mul_float,
    "400-0000018": numbers_.div_float,
    "400-0000019": numbers_.to_float,
    "400-0000020": numbers_.to_int,
    "400-0000021": numbers_.round_,
    "400-0000022": numbers_.parse_float,
    "400-0000023": numbers_.to_big,
    "400-0000024": numbers_.big_to_int,
    "400-0000025": numbers_.add_big,
    "400-0000026": numbers_.sub_big,
    "400-0000027": numbers_.mul_big,
    "400-0000028": numbers_.div_big,
    "400-0000029": numbers_.mod_big,
    "400-0000030": numbers_.pow_big,
    "400-0000031": numbers_.parse_big,
    "400-0000032": numbers_.gcd,
    "400-0000033": numbers_.lcm,
    "400-0000034": numbers_.product,
    "400-0000035": numbers_.is_even,
    "400-0000036": numbers_.is_odd,
    "400-0000040": numbers_.to_dec,
    "400-0000041": numbers_.big_to_dec,
    "400-0000042": numbers_.dec_to_int,
    "400-0000043": numbers_.add_dec,
    "400-0000044": numbers_.sub_dec,
    "400-0000045": numbers_.mul_dec,
    "400-0000046": numbers_.div_dec,
    "400-0000047": numbers_.round_dec,
    "400-0000048": numbers_.parse_dec,
    "400-0000049": numbers_.dec_to_float,
    "400-0000050": numbers_.float_to_dec,
    "400-0000060": numbers_.number_equals,
    "400-0000061": numbers_.number_not_equals,
    "400-0000062": numbers_.less_or_equal,
    "400-0000063": numbers_.greater_or_equal,
    "400-0000064": numbers_.compare,
    "400-0000065": numbers_.close_to,
    "400-0000080": numbers_.make_fraction,
    "400-0000081": numbers_.add_fraction,
    "400-0000082": numbers_.sub_fraction,
    "400-0000083": numbers_.mul_fraction,
    "400-0000084": numbers_.div_fraction,
    "400-0000085": numbers_.negate_fraction,
    "400-0000086": numbers_.abs_fraction,
    "400-0000087": numbers_.numerator,
    "400-0000088": numbers_.denominator,
    "400-0000089": numbers_.fraction_to_float,
    "400-0000090": numbers_.floor_fraction,
    "400-0000091": numbers_.round_fraction,
    "400-0000092": numbers_.parse_fraction,
    "400-0000100": numbers_.dec_to_big,
    "400-0000101": numbers_.big_to_float,
    "400-0000102": numbers_.float_to_big,
    "400-0000103": numbers_.dec_to_fraction,
    "400-0000104": numbers_.fraction_to_dec,
    "400-0000105": numbers_.big_to_fraction,
    "400-0000120": numbers_.format_float,
    "400-0000121": numbers_.format_dec,
    "400-0000122": numbers_.format_fraction,
    "400-0000140": numbers_.sqrt_,
    "400-0000141": numbers_.floor_,
    "400-0000142": numbers_.ceil_,
    "400-0000143": numbers_.mod_float,
    "400-0000144": numbers_.isqrt,
    "400-0000145": numbers_.isqrt_big,
    "400-0000146": numbers_.sqrt_dec,
    "400-0000147": numbers_.floor_dec,
    "400-0000148": numbers_.ceil_dec,
    "400-0000149": numbers_.mod_dec,
    "400-0000150": numbers_.ceil_fraction,
    "400-0000151": numbers_.mod_fraction,
    "400-0000200": numbers_.random_next,
    "400-0000201": numbers_.random_range,
    "400-0000202": numbers_.random_float,
    "400-0000203": numbers_.random_bool,
    "400-0000204": numbers_.random_ints,
    "400-0000205": numbers_.random_floats,
    "400-0000206": numbers_.shuffle,
    "400-0000207": numbers_.pick,
    "400-0000160": numbers_.bit_and,
    "400-0000161": numbers_.bit_or,
    "400-0000162": numbers_.bit_xor,
    "400-0000163": numbers_.bit_not,
    "400-0000164": numbers_.shift_left,
    "400-0000165": numbers_.shift_right,
    "400-0000166": numbers_.shift_right_unsigned,
    "400-0000167": numbers_.count_bits,
    "400-0000168": numbers_.to_base,
    "400-0000169": numbers_.parse_base,
    "400-0000170": numbers_.to_base_unsigned,
    "400-0000171": numbers_.parse_base_unsigned,
    "400-0000172": numbers_.big_to_base,
    "400-0000173": numbers_.parse_big_base,
    "400-0000180": numbers_.smallest,
    "400-0000181": numbers_.largest,
    "400-0000182": numbers_.sum_float,
    "400-0000183": numbers_.sum_big,
    "400-0000184": numbers_.sum_dec,
    "400-0000185": numbers_.sum_fraction,
    "400-0000186": numbers_.average,
    "400-0000187": numbers_.average_float,
    "400-0000188": numbers_.average_big,
    "400-0000189": numbers_.average_dec,
    "400-0000190": numbers_.average_fraction,
    "400-0000191": numbers_.median,
    "400-0000192": numbers_.median_float,
    "400-0000193": numbers_.median_big,
    "400-0000194": numbers_.median_dec,
    "400-0000195": numbers_.median_fraction,
    "500-0000001": io_.read_text_file,
    "500-0000002": io_.write_text_file,
    "500-0000003": io_.read_csv,
    "500-0000004": io_.write_csv,
    "600-0000001": logic_.not_,
    "600-0000002": logic_.and_,
    "600-0000003": logic_.or_,
    "600-0000004": logic_.equals,
    "600-0000005": logic_.less_than,
    "600-0000006": logic_.greater_than,
    "600-0000007": logic_.is_empty,
}


def call(address: str, *args):
    """Dial an address directly. Used by the interpreter and the test suite."""
    implementation = IMPLEMENTATIONS.get(address)
    if implementation is None:
        raise PhonebookFault("unimplemented", f"{address} has no Python implementation")
    return implementation(*args)


def resolve(dotted: str):
    """Look up a runtime function from a mapping table's `runtime` string."""
    module_name, _, function_name = dotted.rpartition(".")
    module = {
        "core": core,
        "text": text,
        "collections_": collections_,
        "numbers_": numbers_,
        "io_": io_,
        "logic_": logic_,
    }.get(module_name)
    if module is None:
        raise PhonebookFault("unimplemented", f"unknown runtime module {module_name!r}")
    function = getattr(module, function_name, None)
    if function is None:
        raise PhonebookFault("unimplemented", f"{dotted} does not exist")
    return function
