"""The parsed shape of a .phone program.

A program is a straight-line graph of calls plus a set of local extensions.
There is no expression nesting: every intermediate value has a name, which is
what makes an execution trace readable line-for-line against the source.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import Span
from .types import Type


@dataclass(frozen=True)
class Selector:
    """A version policy attached to one call site."""

    kind: str = "latest"  # latest | contract | impl
    value: int | None = None

    def __str__(self) -> str:
        return "@latest" if self.kind == "latest" else f"@{self.kind}:{self.value}"

    @property
    def is_pinned(self) -> bool:
        return self.kind == "impl"


LATEST = Selector()


@dataclass(frozen=True)
class Literal:
    value: object
    type: Type
    label: str | None = None


@dataclass(frozen=True)
class Ref:
    """A reference to an earlier binding, or to an extension parameter."""

    name: str
    label: str | None = None


@dataclass(frozen=True)
class AddressRef:
    """An address passed as a value — the language's only callable form."""

    address: str
    label: str | None = None


Arg = Literal | Ref | AddressRef


@dataclass
class Call:
    address: str
    selector: Selector
    args: list[Arg]
    output: str | None
    span: Span


@dataclass
class Extension:
    """A local (000) extension: the only place user-defined behavior can live."""

    address: str
    name: str
    params: list[tuple[str, Type]]
    result: Type
    body: list[Call]
    returns: str
    span: Span
    source: list[str] = field(default_factory=list)


@dataclass
class Program:
    path: str
    version: str | None
    pins: dict[str, Selector]
    extensions: dict[str, Extension]
    body: list[Call]
    lines: list[str] = field(default_factory=list)

    def calls(self):
        """Every call in the program, extensions first, then the main body."""
        for extension in self.extensions.values():
            yield from extension.body
        yield from self.body
