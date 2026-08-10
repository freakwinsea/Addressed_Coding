"""Generate Rust from a checked program.

Two rules keep the borrow checker out of the contracts:

* every runtime function takes `&T` and returns an owned value, so the emitter
  never has to reason about who owns what;
* each local extension shadows its parameters with owned clones on entry, so
  the body is written against plain values exactly like `main` is.

The result clones more than hand-written Rust would. That is the honest cost of
a registry that describes values rather than memory, and it is the reason the
same 54 addresses can drive a garbage-collected backend and a borrow-checked
one without either leaking into the other.
"""

from __future__ import annotations

import json

from ..checker import CheckedCall, CheckedProgram
from ..errors import CheckError
from ..nodes import LATEST, AddressRef, Arg, Literal, Ref
from ..registry import LOCAL_AREA, area_of
from ..resolver import Backend, selector_for
from ..types import Type
from .common import fill, header, identifier, snake

KEYWORDS = {
    "as", "break", "const", "continue", "crate", "dyn", "else", "enum", "extern",
    "false", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod",
    "move", "mut", "pub", "ref", "return", "self", "static", "struct", "super",
    "trait", "true", "type", "unsafe", "use", "where", "while", "async", "await",
    "box", "do", "final", "macro", "override", "priv", "typeof", "unsized",
    "virtual", "yield", "try", "main", "abstract", "become",
}


def emit(checked: CheckedProgram, backend: Backend) -> str:
    return _Emitter(checked, backend).run()


def rust_type(t: Type) -> str:
    """Render a phonebook type as a Rust type."""
    if t.name == "text":
        return "String"
    if t.name == "int":
        return "i64"
    if t.name == "bool":
        return "bool"
    if t.name == "unit":
        return "()"
    if t.name == "list":
        return f"Vec<{rust_type(t.args[0])}>"
    if t.name == "map":
        return f"BTreeMap<{rust_type(t.args[0])}, {rust_type(t.args[1])}>"
    if t.name == "pair":
        return f"({rust_type(t.args[0])}, {rust_type(t.args[1])})"
    raise CheckError(f"no Rust representation for type {t}")


class _Emitter:
    def __init__(self, checked: CheckedProgram, backend: Backend):
        self.checked = checked
        self.backend = backend
        self.pins = checked.program.pins
        self.ext_names: dict[str, str] = {
            address: snake(extension.name)
            for address, extension in checked.program.extensions.items()
        }

    def run(self) -> str:
        lines = header(self.checked, "rust", "//")
        lines.append(
            "#![allow(unused_imports, unused_variables, unused_parens, clippy::all)]"
        )
        lines.append("")
        lines.append("use phonebook_rt as rt;")
        lines.append("use std::collections::BTreeMap;")
        lines.append("")

        for address in sorted(self.checked.program.extensions):
            lines += self.emit_extension(address)
            lines.append("")

        lines.append("fn main() {")
        names: dict[str, str] = {}
        taken: set[str] = set(self.ext_names.values())
        for call in self.checked.body:
            lines.append("    " + self.emit_call(call, names, taken))
        lines.append("}")
        return "\n".join(lines) + "\n"

    # -- pieces ----------------------------------------------------------

    def emit_extension(self, address: str) -> list[str]:
        checked_ext = self.checked.extensions[address]
        extension = checked_ext.extension
        names: dict[str, str] = {}
        taken: set[str] = set(self.ext_names.values())

        params = []
        for param_name, param_type in extension.params:
            safe = identifier(param_name, taken, KEYWORDS)
            taken.add(safe)
            names[param_name] = safe
            params.append(f"{safe}: &{rust_type(param_type)}")

        lines = [
            f"/// {extension.address}  {extension.name}",
            "///",
            "/// A local extension: this is custom logic, not a registered address.",
            f"fn {self.ext_names[address]}({', '.join(params)}) -> {rust_type(extension.result)} {{",
        ]
        # Own the parameters up front so the body reads exactly like `main`.
        for param_name, param_type in extension.params:
            safe = names[param_name]
            lines.append(f"    let {safe}: {rust_type(param_type)} = {safe}.clone();")
        for call in checked_ext.calls:
            lines.append("    " + self.emit_call(call, names, taken))
        lines.append(f"    {names[extension.returns]}")
        lines.append("}")
        return lines

    def emit_call(self, checked: CheckedCall, names: dict[str, str], taken: set[str]) -> str:
        expression = self.render_expression(checked, names)
        if checked.call.output is None:
            return expression + ";"
        safe = identifier(checked.call.output, taken, KEYWORDS)
        taken.add(safe)
        names[checked.call.output] = safe
        return f"let {safe}: {rust_type(checked.output_type)} = {expression};"

    def render_expression(self, checked: CheckedCall, names: dict[str, str]) -> str:
        if checked.is_local:
            args = [self.render_arg(a, names, borrowed=True) for a in checked.call.args]
            return f"{self.ext_names[checked.address]}({', '.join(args)})"

        implementation = self.backend.resolve(
            checked.address, selector_for(checked.address, checked.call.selector, self.pins)
        )
        if implementation.inline:
            # An inline template receives bare expressions. The one variadic
            # address builds a vec! literal, whose elements must be owned.
            owned = checked.entry is not None and checked.entry.contract.variadic
            args = [
                self.render_arg(a, names, borrowed=False, clone=owned)
                for a in checked.call.args
            ]
            return fill(implementation.inline, args)

        if implementation.runtime is None:
            raise CheckError(
                f"{checked.address} has no Rust runtime function and no inline template"
            )
        args = [self.render_arg(a, names, borrowed=True) for a in checked.call.args]
        return f"rt::{implementation.runtime}({', '.join(args)})"

    def render_arg(
        self, arg: Arg, names: dict[str, str], borrowed: bool, clone: bool = False
    ) -> str:
        if isinstance(arg, AddressRef):
            # Callables are passed by name in either style.
            if area_of(arg.address) == LOCAL_AREA:
                return self.ext_names[arg.address]
            implementation = self.backend.resolve(arg.address, self.pins.get(arg.address, LATEST))
            if implementation.runtime is None:
                raise CheckError(f"{arg.address} cannot be passed as a Rust callable")
            return f"rt::{implementation.runtime}"

        if isinstance(arg, Literal):
            if isinstance(arg.value, bool):
                rendered = "true" if arg.value else "false"
            elif isinstance(arg.value, str):
                rendered = json.dumps(arg.value, ensure_ascii=False) + ".to_string()"
            else:
                rendered = str(arg.value)
        elif isinstance(arg, Ref):
            rendered = names[arg.name]
            if clone:
                rendered += ".clone()"
        else:
            raise TypeError(f"unsupported argument {arg!r}")

        return f"&{rendered}" if borrowed else rendered
