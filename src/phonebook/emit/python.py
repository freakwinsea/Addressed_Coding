"""Generate Python from a checked program.

The generated file calls the same `phonebook_rt` functions the interpreter
calls, so `dial run` and the emitted program cannot disagree. Where a mapping
table offers an `inline` template that is exactly equivalent, it is used instead
— that is a readability choice, and correctness never depends on it.
"""

from __future__ import annotations

import json
import keyword

from ..checker import CheckedCall, CheckedProgram
from ..nodes import AddressRef, Arg, Literal, Ref
from ..registry import LOCAL_AREA, area_of
from ..resolver import Backend, selector_for
from .common import fill, header, identifier, snake

MODULES = ["collections_", "core", "io_", "logic_", "numbers_", "text"]
KEYWORDS = set(keyword.kwlist) | {"main", "print", "len", "sorted", "list", "dict", "min", "max"}


def emit(checked: CheckedProgram, backend: Backend) -> str:
    return _Emitter(checked, backend).run()


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
        lines = header(self.checked, "python", "#")
        lines.append("from phonebook_rt import (")
        for module in MODULES:
            lines.append(f"    {module} as _pb_{module.rstrip('_')},")
        lines.append(")")
        lines.append("")
        lines.append("")

        for address in sorted(self.checked.program.extensions):
            lines += self.emit_extension(address)
            lines.append("")
            lines.append("")

        lines.append("def main() -> None:")
        names: dict[str, str] = {}
        taken: set[str] = set(self.ext_names.values())
        body = [self.emit_call(call, names, taken) for call in self.checked.body]
        lines += ["    " + line for line in body] or ["    pass"]
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    main()")
        return "\n".join(lines) + "\n"

    # -- pieces ----------------------------------------------------------

    def emit_extension(self, address: str) -> list[str]:
        checked_ext = self.checked.extensions[address]
        extension = checked_ext.extension
        names: dict[str, str] = {}
        taken: set[str] = set(self.ext_names.values())
        params = []
        for param_name, _ in extension.params:
            safe = identifier(param_name, taken, KEYWORDS)
            taken.add(safe)
            names[param_name] = safe
            params.append(safe)

        lines = [f"def {self.ext_names[address]}({', '.join(params)}):"]
        lines.append(f'    """{extension.address}  {extension.name}')
        lines.append("")
        lines.append("    A local extension: this is custom logic, not a registered address.")
        lines.append('    """')
        for call in checked_ext.calls:
            lines.append("    " + self.emit_call(call, names, taken))
        lines.append(f"    return {names[extension.returns]}")
        return lines

    def emit_call(self, checked: CheckedCall, names: dict[str, str], taken: set[str]) -> str:
        args = [self.render_arg(arg, names) for arg in checked.call.args]
        expression = self.render_expression(checked, args)
        if checked.call.output is None:
            return expression
        safe = identifier(checked.call.output, taken, KEYWORDS)
        taken.add(safe)
        names[checked.call.output] = safe
        return f"{safe} = {expression}"

    def render_expression(self, checked: CheckedCall, args: list[str]) -> str:
        if checked.is_local:
            return f"{self.ext_names[checked.address]}({', '.join(args)})"
        implementation = self.backend.resolve(
            checked.address, selector_for(checked.address, checked.call.selector, self.pins)
        )
        if implementation.inline:
            return fill(implementation.inline, args)
        return f"{self.runtime_ref(implementation.runtime)}({', '.join(args)})"

    def render_arg(self, arg: Arg, names: dict[str, str]) -> str:
        if isinstance(arg, Literal):
            if isinstance(arg.value, bool):
                return "True" if arg.value else "False"
            if isinstance(arg.value, str):
                return json.dumps(arg.value, ensure_ascii=False)
            return str(arg.value)
        if isinstance(arg, Ref):
            return names[arg.name]
        if isinstance(arg, AddressRef):
            if area_of(arg.address) == LOCAL_AREA:
                return self.ext_names[arg.address]
            implementation = self.backend.resolve(
                arg.address, self.pins.get(arg.address) or _latest()
            )
            return self.runtime_ref(implementation.runtime)
        raise TypeError(f"unsupported argument {arg!r}")

    @staticmethod
    def runtime_ref(dotted: str) -> str:
        module, _, function = dotted.rpartition(".")
        return f"_pb_{module.rstrip('_')}.{function}"


def _latest():
    from ..nodes import LATEST

    return LATEST
