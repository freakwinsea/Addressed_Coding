"""Reading .phone source into a program graph.

The language is line-oriented and has no nested expressions, so this is a
hand-written line parser rather than a lexer/parser pair. That is a deliberate
property of the notation, not a shortcut: one line is one call, which is what
lets `dial annotate` and `dial run --trace` line up with the source exactly.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from .errors import ParseError, Span
from .nodes import (
    AddressRef,
    Arg,
    Call,
    Extension,
    Literal,
    Program,
    Ref,
    Selector,
)
from .types import BIGINT, BOOL, DECIMAL, FLOAT, INT, TEXT, parse_type

ADDRESS = r"[0-9]{3}-[0-9]{7}"
SELECTOR = r"@(?:latest|contract:[0-9]+|impl:[0-9]+)"

CALL_RE = re.compile(
    rf"^(?P<address>{ADDRESS})(?P<selector>{SELECTOR})?@\[(?P<args>.*)\]"
    rf"(?:\s*->\s*(?P<output>[A-Za-z_][A-Za-z0-9_]*))?\s*$"
)
EXT_RE = re.compile(
    rf"^ext\s+(?P<address>{ADDRESS})\s+(?P<name>[A-Z][A-Z0-9_]*)\s*"
    rf"\((?P<params>.*?)\)\s*->\s*(?P<result>[^{{]+?)\s*\{{\s*$"
)
PIN_RE = re.compile(rf"^pin\s+(?P<address>{ADDRESS})\s+(?P<selector>{SELECTOR})\s*$")
HEADER_RE = re.compile(r"^phonebook\s+(?P<version>[0-9]+\.[0-9]+)\s*$")
RETURN_RE = re.compile(r"^return\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*$")
INT_RE = re.compile(r"^-?[0-9]+$")
#: An int may also be written in hex or binary, `0xff` or `0b1010`: a signed
#: value like any other int, so `0xffffffffffffffff` does not fit and -1 does.
BASED_INT_RE = re.compile(r"^-?0(?:[xX][0-9a-fA-F]+|[bB][01]+)$")
#: A bigint literal is an integer with an `n` suffix, as in JavaScript: `12n`.
BIGINT_RE = re.compile(r"^-?[0-9]+n$")
#: A decimal literal is digits, an optional fraction, and a `d` suffix: `0.10d`.
DECIMAL_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?d$")
#: Checked after INT_RE, so a float literal is a digit string with a fraction,
#: an exponent, or both. The same shape PARSE_FLOAT accepts, minus the "+".
FLOAT_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ADDRESS_RE = re.compile(rf"^{ADDRESS}$")

# `int` is a 64-bit signed integer on every backend (SPEC: Rust `i64`).
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
# `bigint` has no fixed width, but it does have a ceiling: at most 4000 decimal
# digits (SPEC §3.2). The same ceiling every bigint address enforces.
BIGINT_MAX_DIGITS = 4000
# `decimal` shares that ceiling for its digits, and has at most 1000 of them
# after the point (SPEC §3.3).
DECIMAL_MAX_SCALE = 1000


def parse_file(path: Path | str) -> Program:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), str(path))


def parse(source: str, filename: str = "<string>") -> Program:
    return _Parser(source, filename).run()


class _Parser:
    def __init__(self, source: str, filename: str):
        self.filename = filename
        self.raw_lines = source.splitlines()
        self.index = 0

    # -- helpers ---------------------------------------------------------

    def span(self, line_no: int) -> Span:
        text = self.raw_lines[line_no - 1] if 0 < line_no <= len(self.raw_lines) else ""
        return Span(self.filename, line_no, text)

    def fail(self, message: str, line_no: int) -> None:
        raise ParseError(message, self.span(line_no))

    def decimal_literal(self, text: str, line_no: int) -> str:
        """Check a decimal literal (without its `d`) against the ceilings and
        return it in canonical form: no leading zeros, and no sign on zero.

        The value stays text. Each backend builds its own decimal from it, so
        the toolchain never needs one of its own.
        """
        negative = text.startswith("-")
        whole, _, fraction = text.lstrip("-").partition(".")
        digits = (whole + fraction).lstrip("0")
        if len(digits) > BIGINT_MAX_DIGITS:
            self.fail(
                f"decimal literal has {len(digits)} digits; "
                f"the most a decimal can have is {BIGINT_MAX_DIGITS}",
                line_no,
            )
        if len(fraction) > DECIMAL_MAX_SCALE:
            self.fail(
                f"decimal literal has {len(fraction)} digits after the point; "
                f"the most a decimal can have is {DECIMAL_MAX_SCALE}",
                line_no,
            )
        whole = whole.lstrip("0") or "0"
        sign = "-" if negative and digits else ""
        return sign + whole + ("." + fraction if fraction else "")

    # -- driver ----------------------------------------------------------

    def run(self) -> Program:
        version: str | None = None
        pins: dict[str, Selector] = {}
        extensions: dict[str, Extension] = {}
        body: list[Call] = []
        seen_call = False

        while self.index < len(self.raw_lines):
            line_no = self.index + 1
            line = strip_comment(self.raw_lines[self.index]).strip()
            self.index += 1
            if not line:
                continue

            header = HEADER_RE.match(line)
            if header:
                if version is not None:
                    self.fail("duplicate 'phonebook' header", line_no)
                if seen_call or extensions or pins:
                    self.fail("the 'phonebook' header must come first", line_no)
                version = header.group("version")
                continue

            pin = PIN_RE.match(line)
            if pin:
                if seen_call:
                    self.fail("'pin' directives must appear before any call", line_no)
                address = pin.group("address")
                if address in pins:
                    self.fail(f"{address} is pinned twice", line_no)
                pins[address] = parse_selector(pin.group("selector"))
                continue

            if line.startswith("ext"):
                extension = self.parse_extension(line, line_no)
                if extension.address in extensions:
                    self.fail(f"local extension {extension.address} is defined twice", line_no)
                extensions[extension.address] = extension
                continue

            if line.startswith("return"):
                self.fail("'return' is only valid inside an ext block", line_no)

            body.append(self.parse_call(line, line_no))
            seen_call = True

        return Program(
            path=self.filename,
            version=version,
            pins=pins,
            extensions=extensions,
            body=body,
            lines=self.raw_lines,
        )

    # -- pieces ----------------------------------------------------------

    def parse_extension(self, line: str, line_no: int) -> Extension:
        match = EXT_RE.match(line)
        if not match:
            self.fail(
                "malformed ext header",
                line_no,
            )
        assert match  # for type checkers; fail() always raises

        address = match.group("address")
        if not address.startswith("000-"):
            raise ParseError(
                f"local extensions must use the 000 area code, got {address}",
                self.span(line_no),
            )

        params: list[tuple[str, str]] = []
        raw_params = match.group("params").strip()
        if raw_params:
            for chunk in split_top_level(raw_params):
                if ":" not in chunk:
                    self.fail(f"parameter {chunk.strip()!r} needs a type, e.g. 'line: text'", line_no)
                name, _, type_text = chunk.partition(":")
                params.append((name.strip(), type_text.strip()))

        try:
            typed_params = [(name, parse_type(t)) for name, t in params]
            result = parse_type(match.group("result"))
        except Exception as exc:
            raise ParseError(str(exc), self.span(line_no)) from exc

        body: list[Call] = []
        returns: str | None = None
        source = [self.raw_lines[line_no - 1]]

        while self.index < len(self.raw_lines):
            inner_no = self.index + 1
            raw = self.raw_lines[self.index]
            self.index += 1
            source.append(raw)
            inner = strip_comment(raw).strip()
            if not inner:
                continue
            if inner == "}":
                if returns is None:
                    self.fail(f"ext {address} has no 'return'", inner_no)
                return Extension(
                    address=address,
                    name=match.group("name"),
                    params=typed_params,
                    result=result,
                    body=body,
                    returns=returns,
                    span=self.span(line_no),
                    source=source,
                )
            ret = RETURN_RE.match(inner)
            if ret:
                if returns is not None:
                    self.fail("an ext may only return once", inner_no)
                returns = ret.group("name")
                continue
            if returns is not None:
                self.fail("no calls are allowed after 'return'", inner_no)
            body.append(self.parse_call(inner, inner_no))

        self.fail(f"ext {address} is never closed with '}}'", line_no)
        raise AssertionError("unreachable")

    def parse_call(self, line: str, line_no: int) -> Call:
        match = CALL_RE.match(line)
        if not match:
            hint = ""
            if "@[" not in line:
                hint = "a call looks like  300-0000009@[items] -> count"
            raise ParseError(
                f"cannot read a call from {line!r}" + (f"\n  hint: {hint}" if hint else ""),
                self.span(line_no),
            )
        args = [self.parse_arg(chunk, line_no) for chunk in split_top_level(match.group("args"))]
        return Call(
            address=match.group("address"),
            selector=parse_selector(match.group("selector")),
            args=args,
            output=match.group("output"),
            span=self.span(line_no),
        )

    def parse_arg(self, chunk: str, line_no: int) -> Arg:
        text = chunk.strip()
        label: str | None = None

        # A named argument, but only when the '=' is not inside a string.
        eq = find_top_level(text, "=")
        if eq is not None:
            candidate = text[:eq].strip()
            if NAME_RE.match(candidate):
                label = candidate
                text = text[eq + 1 :].strip()

        if not text:
            self.fail("empty argument", line_no)

        if text.startswith('"'):
            return Literal(unquote(text, self.span(line_no)), TEXT, label)
        if text in ("true", "false"):
            return Literal(text == "true", BOOL, label)
        if INT_RE.match(text):
            value = int(text)
            if value < INT64_MIN or value > INT64_MAX:
                self.fail(
                    f"integer literal {text} does not fit in a 64-bit signed integer "
                    f"({INT64_MIN} to {INT64_MAX})",
                    line_no,
                )
            return Literal(value, INT, label)
        if BASED_INT_RE.match(text):
            negative = text.startswith("-")
            digits = text.lstrip("-")
            value = int(digits[2:], 16 if digits[1] in "xX" else 2)
            value = -value if negative else value
            if value < INT64_MIN or value > INT64_MAX:
                self.fail(
                    f"integer literal {text} does not fit in a 64-bit signed integer "
                    f"({INT64_MIN} to {INT64_MAX})"
                    "\n  hint: a literal is a signed value, not a bit pattern; "
                    "PARSE_BASE_UNSIGNED (400-0000171) reads a pattern",
                    line_no,
                )
            return Literal(value, INT, label)
        if BIGINT_RE.match(text):
            digits = text[:-1].lstrip("-").lstrip("0")
            if len(digits) > BIGINT_MAX_DIGITS:
                self.fail(
                    f"bigint literal has {len(digits)} digits; "
                    f"the most a bigint can have is {BIGINT_MAX_DIGITS}",
                    line_no,
                )
            value = int(text[:-1])
            # Zero has one sign here too: -0n is 0n.
            return Literal(value, BIGINT, label)
        if DECIMAL_RE.match(text):
            return Literal(self.decimal_literal(text[:-1], line_no), DECIMAL, label)
        if FLOAT_RE.match(text):
            value = float(text)
            if not math.isfinite(value):
                self.fail(
                    f"float literal {text} is too large to be finite"
                    "\n  hint: floats are always finite; the largest is about 1.8e308",
                    line_no,
                )
            # Zero has one sign: -0.0 is written 0.0 everywhere else, so here too.
            return Literal(value if value != 0.0 else 0.0, FLOAT, label)
        if ADDRESS_RE.match(text):
            return AddressRef(text, label)
        if NAME_RE.match(text):
            return Ref(text, label)
        self.fail(f"cannot read argument {text!r}", line_no)
        raise AssertionError("unreachable")


# --------------------------------------------------------------------------
# lexical helpers
# --------------------------------------------------------------------------


def parse_selector(text: str | None) -> Selector:
    if not text or text == "@latest":
        return Selector()
    kind, _, value = text[1:].partition(":")
    return Selector(kind, int(value))


def strip_comment(line: str) -> str:
    """Drop a trailing `#` comment, ignoring `#` inside string literals."""
    out: list[str] = []
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == "#":
            break
        if char == '"':
            in_string = True
        out.append(char)
    return "".join(out)


OPENERS = {"<": ">", "(": ")", "[": "]"}
CLOSERS = set(OPENERS.values())


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on a separator that is outside strings and outside brackets.

    Bracket depth matters because parameter lists carry nested types:
    `entry: pair<text,int>` is one parameter, not two.
    """
    if not text.strip():
        return []
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    depth = 0
    for char in text:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current.append(char)
            continue
        if char in OPENERS:
            depth += 1
        elif char in CLOSERS:
            depth = max(0, depth - 1)
        elif char == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def find_top_level(text: str, char: str) -> int | None:
    in_string = False
    escaped = False
    for i, c in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c == char:
            return i
    return None


ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


def unquote(text: str, span: Span) -> str:
    if len(text) < 2 or not text.endswith('"'):
        raise ParseError(f"unterminated string literal: {text}", span)
    body = text[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        char = body[i]
        if char == "\\":
            if i + 1 >= len(body):
                raise ParseError("string ends with a dangling backslash", span)
            code = body[i + 1]
            if code not in ESCAPES:
                raise ParseError(
                    rf"unknown escape \{code} (valid: \n \t \r \\ \")", span
                )
            out.append(ESCAPES[code])
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)
