"""Reading .phone source into a program graph.

The language is line-oriented and has no nested expressions, so this is a
hand-written line parser rather than a lexer/parser pair. That is a deliberate
property of the notation, not a shortcut: one line is one call, which is what
lets `dial annotate` and `dial run --trace` line up with the source exactly.
"""

from __future__ import annotations

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
from .types import BOOL, INT, TEXT, parse_type

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
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ADDRESS_RE = re.compile(rf"^{ADDRESS}$")


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
            return Literal(int(text), INT, label)
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
