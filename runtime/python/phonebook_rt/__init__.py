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
