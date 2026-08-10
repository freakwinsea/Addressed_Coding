"""Error types shared by every stage of the toolchain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Span:
    """Where in a source file something went wrong."""

    file: str
    line: int
    text: str = ""

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


class PhonebookError(Exception):
    """Base for every error the toolchain raises deliberately."""


class RegistryError(PhonebookError):
    """The registry itself is malformed or inconsistent."""


class ParseError(PhonebookError):
    def __init__(self, message: str, span: Span | None = None):
        self.span = span
        self.message = message
        super().__init__(f"{span}: {message}" if span else message)


class CheckError(PhonebookError):
    """A contract was not satisfied: unknown address, bad arity, type mismatch."""

    def __init__(self, message: str, span: Span | None = None, hint: str = ""):
        self.span = span
        self.message = message
        self.hint = hint
        rendered = f"{span}: {message}" if span else message
        if hint:
            rendered += f"\n  hint: {hint}"
        super().__init__(rendered)


class RuntimeFault(PhonebookError):
    """A declared contract error fired at run time.

    `code` is one of the strings in the entry's `contract.errors`, which is what
    makes runtime failures part of the contract rather than backend trivia.
    """

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)
