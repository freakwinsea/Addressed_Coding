"""Executing a checked program by dialing each address in turn.

The interpreter resolves every call through the Python backend's mapping table
and invokes the runtime function it names. It does not contain a second copy of
any operation's behavior — that is the point.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from phonebook_rt import PhonebookFault, resolve as resolve_runtime

from .checker import CheckedCall, CheckedExtension, CheckedProgram
from .nodes import LATEST, AddressRef, Arg, Literal, Ref
from .resolver import Backend, selector_for


@dataclass
class Trace:
    """Resolved-name execution log.

    Written to stderr, never stdout: a trace must never change the bytes a
    program produces, or the cross-backend comparison would be meaningless.

    This is also the concrete answer to the "nobody can read 7-digit numbers"
    objection. You never read them raw — the tooling resolves them for you at
    every point where you would otherwise have to.
    """

    enabled: bool = False
    depth: int = 0

    def emit(self, line: str) -> None:
        if self.enabled:
            sys.stderr.write("  " * self.depth + line + "\n")


class Interpreter:
    def __init__(self, checked: CheckedProgram, backend: Backend, trace: Trace | None = None):
        self.checked = checked
        self.backend = backend
        self.trace = trace or Trace()
        self.pins = checked.program.pins

    # -- running ---------------------------------------------------------

    def run(self) -> dict[str, object]:
        bindings: dict[str, object] = {}
        for call in self.checked.body:
            self.execute(call, bindings)
        return bindings

    def execute(self, checked: CheckedCall, bindings: dict[str, object]) -> object:
        args = [self.value_of(arg, bindings) for arg in checked.call.args]

        if checked.is_local:
            assert checked.extension is not None
            self.trace.emit(self.render(checked, args))
            self.trace.depth += 1
            try:
                result = self.call_extension(checked.extension.address, args)
            finally:
                self.trace.depth -= 1
        else:
            implementation = self.backend.resolve(
                checked.address, selector_for(checked.address, checked.call.selector, self.pins)
            )
            function = resolve_runtime(implementation.runtime)
            self.trace.emit(self.render(checked, args))
            result = function(*args)

        if checked.call.output is not None:
            bindings[checked.call.output] = result
        return result

    def call_extension(self, address: str, args: list) -> object:
        checked_ext: CheckedExtension = self.checked.extensions[address]
        local: dict[str, object] = {
            name: value for (name, _), value in zip(checked_ext.extension.params, args)
        }
        for call in checked_ext.calls:
            self.execute(call, local)
        return local[checked_ext.extension.returns]

    # -- values ----------------------------------------------------------

    def value_of(self, arg: Arg, bindings: dict[str, object]) -> object:
        if isinstance(arg, Literal):
            return arg.value
        if isinstance(arg, Ref):
            return bindings[arg.name]
        if isinstance(arg, AddressRef):
            return self.callable_for(arg.address)
        raise PhonebookFault("unsupported_argument", repr(arg))

    def callable_for(self, address: str):
        """An address used as a value becomes an ordinary callable."""
        if address in self.checked.extensions:

            def invoke(*args):
                # Indent so a trace shows which calls happened inside the
                # predicate FILTER or MAP handed control to.
                self.trace.emit(f"{address} {self.name_of(address)}[{_previews(args)}]")
                self.trace.depth += 1
                try:
                    return self.call_extension(address, list(args))
                finally:
                    self.trace.depth -= 1

            return invoke
        implementation = self.backend.resolve(address, self.pins.get(address, LATEST))
        return resolve_runtime(implementation.runtime)

    # -- tracing ---------------------------------------------------------

    def name_of(self, address: str) -> str:
        checked_ext = self.checked.extensions.get(address)
        if checked_ext is not None:
            return checked_ext.extension.name
        entry = self.checked.registry.get(address)
        return entry.name if entry else "?"

    def render(self, checked: CheckedCall, args: list) -> str:
        target = f" -> {checked.call.output}" if checked.call.output else ""
        return f"{checked.address} {checked.name}[{_previews(args)}]{target}"


def _previews(args) -> str:
    return ", ".join(preview(a) for a in args)


def preview(value: object, limit: int = 48) -> str:
    """A short, readable form of a value for the trace."""
    if callable(value):
        return "<callable>"
    if isinstance(value, str):
        text = value if len(value) <= limit else value[:limit] + "…"
        return '"' + text.replace("\n", "\\n").replace("\t", "\\t") + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return f"<{type(value).__name__} of {len(value)}>"
    return str(value)


def run(checked: CheckedProgram, backend: Backend, trace: bool = False) -> dict[str, object]:
    return Interpreter(checked, backend, Trace(enabled=trace)).run()
