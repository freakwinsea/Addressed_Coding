"""The v0 type language: parsing, unification, and constraint checking.

Deliberately tiny. The whole point of keeping it small is that every type has an
obvious representation in both backends, which is what lets one contract drive
Python and Rust codegen without encoding ownership or lifetimes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import CheckError

PRIMITIVES = {"int", "bool", "text", "unit", "any"}
CONTAINERS = {"list": 1, "map": 2, "pair": 2}

#: Types that can be ordered by SORT / LESS_THAN and friends.
COMPARABLE = {"int", "text", "bool"}
#: Types that can be a map key or deduplicated by UNIQUE.
KEYABLE = {"int", "text", "bool"}

_VAR = re.compile(r"^[A-Z][A-Z0-9]*$")


@dataclass(frozen=True)
class Type:
    """A type expression.

    `callable` stores its parameters and return together in `args`, with the
    return type last, so `callable(T)->bool` is Type("callable", (T, bool)).
    """

    name: str
    args: tuple["Type", ...] = field(default_factory=tuple)

    @property
    def is_var(self) -> bool:
        return _VAR.match(self.name) is not None and not self.args

    @property
    def is_callable(self) -> bool:
        return self.name == "callable"

    @property
    def params(self) -> tuple["Type", ...]:
        assert self.is_callable
        return self.args[:-1]

    @property
    def result(self) -> "Type":
        assert self.is_callable
        return self.args[-1]

    def __str__(self) -> str:
        if self.is_callable:
            inner = ",".join(str(p) for p in self.params)
            return f"callable({inner})->{self.result}"
        if self.args:
            return f"{self.name}<{','.join(str(a) for a in self.args)}>"
        return self.name


INT = Type("int")
BOOL = Type("bool")
TEXT = Type("text")
UNIT = Type("unit")
ANY = Type("any")


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def parse_type(source: str) -> Type:
    """Parse a type expression such as `list<pair<text,int>>`."""
    text = source.strip()
    parsed, rest = _parse(text)
    if rest.strip():
        raise CheckError(f"trailing text in type {source!r}: {rest!r}")
    return parsed


def _parse(text: str) -> tuple[Type, str]:
    text = text.lstrip()
    if text.startswith("callable"):
        rest = text[len("callable") :].lstrip()
        if not rest.startswith("("):
            raise CheckError(f"callable must be followed by '(' in {text!r}")
        rest = rest[1:]
        params: list[Type] = []
        rest = rest.lstrip()
        if rest.startswith(")"):
            rest = rest[1:]
        else:
            while True:
                param, rest = _parse(rest)
                params.append(param)
                rest = rest.lstrip()
                if rest.startswith(","):
                    rest = rest[1:]
                    continue
                if rest.startswith(")"):
                    rest = rest[1:]
                    break
                raise CheckError(f"expected ',' or ')' in callable params: {rest!r}")
        rest = rest.lstrip()
        if not rest.startswith("->"):
            raise CheckError(f"callable needs a '->' return type: {text!r}")
        ret, rest = _parse(rest[2:])
        return Type("callable", (*params, ret)), rest

    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text)
    if not match:
        raise CheckError(f"cannot read a type from {text!r}")
    name = match.group(0)
    rest = text[match.end() :]
    rest_stripped = rest.lstrip()

    if rest_stripped.startswith("<"):
        rest = rest_stripped[1:]
        args: list[Type] = []
        while True:
            arg, rest = _parse(rest)
            args.append(arg)
            rest = rest.lstrip()
            if rest.startswith(","):
                rest = rest[1:]
                continue
            if rest.startswith(">"):
                rest = rest[1:]
                break
            raise CheckError(f"expected ',' or '>' in type arguments: {rest!r}")
        arity = CONTAINERS.get(name)
        if arity is None:
            raise CheckError(f"unknown container type {name!r}")
        if len(args) != arity:
            raise CheckError(f"{name} takes {arity} type argument(s), got {len(args)}")
        return Type(name, tuple(args)), rest

    if name in CONTAINERS:
        raise CheckError(f"{name} needs type arguments, e.g. {name}<...>")
    if name not in PRIMITIVES and not _VAR.match(name):
        raise CheckError(f"unknown type {name!r}")
    return Type(name), rest


# --------------------------------------------------------------------------
# unification
# --------------------------------------------------------------------------

Substitution = dict[str, Type]


def substitute(t: Type, subs: Substitution) -> Type:
    """Replace bound generic variables with their resolved types."""
    if t.is_var:
        resolved = subs.get(t.name)
        return substitute(resolved, subs) if resolved is not None else t
    if not t.args:
        return t
    return Type(t.name, tuple(substitute(a, subs) for a in t.args))


def unify(declared: Type, actual: Type, subs: Substitution) -> Type:
    """Match an actual type against a declared one, binding generics in `subs`.

    Raises CheckError on mismatch. `any` matches anything without binding, which
    is how PRINT and TO_TEXT accept every value.
    """
    declared = substitute(declared, subs)
    actual = substitute(actual, subs)

    if declared.name == "any" or actual.name == "any":
        return actual if declared.name == "any" else declared

    if declared.is_var:
        subs[declared.name] = actual
        return actual
    if actual.is_var:
        subs[actual.name] = declared
        return declared

    if declared.name != actual.name or len(declared.args) != len(actual.args):
        raise CheckError(f"expected {declared}, got {actual}")

    resolved = tuple(unify(d, a, subs) for d, a in zip(declared.args, actual.args))
    return Type(declared.name, resolved)


def check_constraint(var: str, kind: str, subs: Substitution) -> None:
    """Enforce a `comparable` / `keyable` constraint once the variable resolves.

    Unresolved variables pass: nothing concrete has been chosen yet, so there is
    nothing to reject.
    """
    resolved = subs.get(var)
    if resolved is None:
        return
    resolved = substitute(resolved, subs)
    if resolved.is_var or resolved.name == "any":
        return
    allowed = COMPARABLE if kind == "comparable" else KEYABLE
    if resolved.name not in allowed:
        raise CheckError(
            f"{resolved} is not {kind}",
            hint=f"{kind} types in v0 are: {', '.join(sorted(allowed))}",
        )
