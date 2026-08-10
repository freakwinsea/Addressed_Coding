"""Area 100 — core."""

from __future__ import annotations

import sys

from .faults import PhonebookFault


def to_text(value: object) -> str:
    """100-0000005 TO_TEXT — the one rendering rule for the whole language.

    Note `true` / `false`: Python would say `True`, but the contract says
    otherwise, and the contract wins. This single line is why a program's output
    is identical in Python and Rust rather than merely similar.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, tuple):
        return "(" + ", ".join(to_text(v) for v in value) + ")"
    if isinstance(value, list):
        return "[" + ", ".join(to_text(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{to_text(k)}: {to_text(v)}" for k, v in sorted(value.items()))
        return "{" + inner + "}"
    return str(value)


def print_value(value: object) -> None:
    """100-0000001 PRINT — always a single U+000A, on every platform."""
    sys.stdout.write(to_text(value) + "\n")


def print_lines(lines: list) -> None:
    """100-0000002 PRINT_LINES — an empty list writes nothing at all."""
    out = sys.stdout
    for line in lines:
        out.write(to_text(line) + "\n")


def select(condition: bool, when_true, when_false):
    """100-0000003 SELECT — eager: both arms are already-computed values."""
    return when_true if condition else when_false


def identity(value):
    """100-0000004 IDENTITY."""
    return value


def assert_(condition: bool, message: str) -> None:
    """100-0000006 ASSERT — failure goes to stderr so stdout stays comparable."""
    if not condition:
        raise PhonebookFault("assertion_failed", message)
