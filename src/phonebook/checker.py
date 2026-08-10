"""Contract checking: does this program actually keep the phonebook's promises?

Everything a backend needs to know about a program is decided here — resolved
types for every binding, which extension implements each callable argument, and
the full set of effects the program can have. Both emitters and the interpreter
consume the result, so they cannot disagree about what the program means.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import CheckError, Span
from .nodes import AddressRef, Arg, Call, Extension, Literal, Program, Ref, Selector
from .registry import LOCAL_AREA, RESERVED_AREAS, Entry, Registry, area_of
from .types import Substitution, Type, check_constraint, substitute, unify


@dataclass
class CheckedCall:
    call: Call
    name: str
    entry: Entry | None  # None for a call to a local extension
    extension: Extension | None
    arg_types: list[Type]
    output_type: Type
    effects: tuple[str, ...]

    @property
    def address(self) -> str:
        return self.call.address

    @property
    def is_local(self) -> bool:
        return self.extension is not None


@dataclass
class CheckedExtension:
    extension: Extension
    calls: list[CheckedCall]
    signature: Type
    bindings: dict[str, Type]


@dataclass
class CheckedProgram:
    program: Program
    registry: Registry
    body: list[CheckedCall]
    extensions: dict[str, CheckedExtension]
    bindings: dict[str, Type]
    effects: set[str] = field(default_factory=set)

    def all_calls(self):
        for checked in self.extensions.values():
            yield from checked.calls
        yield from self.body


def check(program: Program, registry: Registry) -> CheckedProgram:
    return _Checker(program, registry).run()


class _Checker:
    def __init__(self, program: Program, registry: Registry):
        self.program = program
        self.registry = registry
        self.effects: set[str] = set()
        self.ext_signatures: dict[str, Type] = {}

    # -- driver ----------------------------------------------------------

    def run(self) -> CheckedProgram:
        self.check_pins()
        for address, extension in self.program.extensions.items():
            self.ext_signatures[address] = Type(
                "callable", (*(t for _, t in extension.params), extension.result)
            )
        self.reject_recursion()

        by_name: dict[str, str] = {}
        for address, extension in self.program.extensions.items():
            clash = by_name.get(extension.name)
            if clash:
                raise CheckError(
                    f"two local extensions are both named {extension.name}: {clash} and {address}",
                    extension.span,
                    hint="names appear in audit reports and generated code, so they "
                    "must identify one thing",
                )
            by_name[extension.name] = address

        checked_exts: dict[str, CheckedExtension] = {}
        for address, extension in self.program.extensions.items():
            bindings = {name: t for name, t in extension.params}
            calls = [self.check_call(call, bindings) for call in extension.body]
            declared = bindings.get(extension.returns)
            if declared is None:
                raise CheckError(
                    f"ext {extension.name} returns {extension.returns!r}, which is not bound",
                    extension.span,
                    hint=f"bound here: {', '.join(sorted(bindings)) or 'nothing'}",
                )
            try:
                unify(extension.result, declared, {})
            except CheckError as exc:
                raise CheckError(
                    f"ext {extension.name} promises {extension.result} but returns {declared}: {exc}",
                    extension.span,
                ) from exc
            checked_exts[address] = CheckedExtension(
                extension=extension,
                calls=calls,
                signature=self.ext_signatures[address],
                bindings=bindings,
            )

        bindings: dict[str, Type] = {}
        body = [self.check_call(call, bindings) for call in self.program.body]

        unused = set(self.program.extensions) - self.used_extensions(checked_exts, body)
        if unused:
            raise CheckError(
                "unused local extension(s): " + ", ".join(sorted(unused)),
                hint="every 000 address must be reachable; unreachable local code is "
                "exactly what the audit model exists to prevent",
            )

        return CheckedProgram(
            program=self.program,
            registry=self.registry,
            body=body,
            extensions=checked_exts,
            bindings=bindings,
            effects=self.effects,
        )

    # -- structural checks -----------------------------------------------

    def check_pins(self) -> None:
        for address, selector in self.program.pins.items():
            entry = self.registry.get(address)
            if entry is None:
                raise CheckError(f"cannot pin {address}: no such address")
            self.check_selector(address, entry, selector, None)

    def check_selector(
        self, address: str, entry: Entry, selector: Selector, span: Span | None
    ) -> None:
        if selector.kind == "contract" and selector.value != entry.contract.version:
            raise CheckError(
                f"{address} is at contract v{entry.contract.version}, "
                f"but this asks for contract v{selector.value}",
                span,
                hint="a contract version that no longer exists cannot be satisfied; "
                "an address's meaning is fixed, so this is a genuine incompatibility",
            )

    def reject_recursion(self) -> None:
        """Extensions may call extensions, but not in a cycle.

        Rejecting cycles keeps every extension a plain function in every
        backend and guarantees termination without a totality checker.
        """
        graph = {
            address: [
                call.address
                for call in extension.body
                if area_of(call.address) == LOCAL_AREA
            ]
            + [
                arg.address
                for call in extension.body
                for arg in call.args
                if isinstance(arg, AddressRef) and area_of(arg.address) == LOCAL_AREA
            ]
            for address, extension in self.program.extensions.items()
        }
        state: dict[str, int] = {}

        def visit(node: str, trail: list[str]) -> None:
            if state.get(node) == 1:
                cycle = " -> ".join(trail + [node])
                raise CheckError(
                    f"local extensions form a cycle: {cycle}",
                    hint="recursion is not permitted in v0",
                )
            if state.get(node) == 2:
                return
            state[node] = 1
            for neighbour in graph.get(node, ()):
                if neighbour in graph:
                    visit(neighbour, trail + [node])
            state[node] = 2

        for address in graph:
            visit(address, [])

    def used_extensions(
        self, checked_exts: dict[str, CheckedExtension], body: list[CheckedCall]
    ) -> set[str]:
        used: set[str] = set()
        pools = [body] + [c.calls for c in checked_exts.values()]
        for pool in pools:
            for checked in pool:
                if area_of(checked.address) == LOCAL_AREA:
                    used.add(checked.address)
                for arg in checked.call.args:
                    if isinstance(arg, AddressRef) and area_of(arg.address) == LOCAL_AREA:
                        used.add(arg.address)
        return used

    # -- calls -----------------------------------------------------------

    def check_call(self, call: Call, bindings: dict[str, Type]) -> CheckedCall:
        area = area_of(call.address)
        if area in RESERVED_AREAS:
            raise CheckError(
                f"area {area} is reserved and has no addresses",
                call.span,
                hint="999 is the quarantine block; 700/800/900 are reserved for future use",
            )

        if area == LOCAL_AREA:
            return self.check_local_call(call, bindings)

        entry = self.registry.get(call.address)
        if entry is None:
            raise CheckError(
                f"no such address: {call.address}",
                call.span,
                hint="try `dial search \"<what you want>\"` to find the right one",
            )
        if entry.status == "withdrawn":
            raise CheckError(
                f"{entry.label} has been withdrawn"
                + (f", superseded by {entry.superseded_by}" if entry.superseded_by else ""),
                call.span,
            )
        self.check_selector(call.address, entry, call.selector, call.span)

        contract = entry.contract
        subs: Substitution = {}
        arg_types: list[Type] = []

        expected = contract.inputs
        if contract.variadic:
            if len(call.args) < 1:
                raise CheckError(
                    f"{entry.label} needs at least one argument", call.span
                )
            expected = tuple(contract.inputs[:-1]) + tuple(
                contract.inputs[-1] for _ in range(len(call.args) - len(contract.inputs) + 1)
            )
        if len(call.args) != len(expected):
            shown = ", ".join(f"{p.name}: {p.type}" for p in contract.inputs)
            raise CheckError(
                f"{entry.label} takes {len(expected)} argument(s), got {len(call.args)}",
                call.span,
                hint=f"signature: {entry.name}({shown})",
            )

        self.check_labels(call, entry, expected)

        for arg, param in zip(call.args, expected):
            actual = self.type_of(arg, bindings, param.type, call.span)
            try:
                unify(param.type, actual, subs)
            except CheckError as exc:
                raise CheckError(
                    f"{entry.label} argument {param.name!r}: {exc}", call.span
                ) from exc
            arg_types.append(actual)

        for var, kind in contract.constraints.items():
            try:
                check_constraint(var, kind, subs)
            except CheckError as exc:
                raise CheckError(f"{entry.label}: {exc}", call.span, hint=exc.hint) from exc

        output_type = substitute(contract.output.type, subs)
        if output_type.name != "unit":
            for var in _free_vars(output_type):
                raise CheckError(
                    f"{entry.label}: cannot infer type variable {var}",
                    call.span,
                    hint="annotate an argument or use a value whose type is already known",
                )

        self.bind_output(call, output_type, bindings, entry.label)
        self.effects.update(contract.effects)
        return CheckedCall(
            call=call,
            name=entry.name,
            entry=entry,
            extension=None,
            arg_types=arg_types,
            output_type=output_type,
            effects=contract.effects,
        )

    def check_local_call(self, call: Call, bindings: dict[str, Type]) -> CheckedCall:
        extension = self.program.extensions.get(call.address)
        if extension is None:
            raise CheckError(
                f"local extension {call.address} is called but never defined",
                call.span,
                hint="000 addresses only exist inside the file that declares them",
            )
        if len(call.args) != len(extension.params):
            raise CheckError(
                f"ext {extension.name} takes {len(extension.params)} argument(s), "
                f"got {len(call.args)}",
                call.span,
            )
        arg_types: list[Type] = []
        for arg, (param_name, param_type) in zip(call.args, extension.params):
            actual = self.type_of(arg, bindings, param_type, call.span)
            try:
                unify(param_type, actual, {})
            except CheckError as exc:
                raise CheckError(
                    f"ext {extension.name} parameter {param_name!r}: {exc}", call.span
                ) from exc
            arg_types.append(actual)

        self.bind_output(call, extension.result, bindings, f"ext {extension.name}")
        return CheckedCall(
            call=call,
            name=extension.name,
            entry=None,
            extension=extension,
            arg_types=arg_types,
            output_type=extension.result,
            effects=(),
        )

    def check_labels(self, call: Call, entry: Entry, expected) -> None:
        for index, arg in enumerate(call.args):
            label = getattr(arg, "label", None)
            if label is None:
                continue
            wanted = expected[index].name
            if label != wanted:
                known = ", ".join(p.name for p in entry.contract.inputs)
                raise CheckError(
                    f"{entry.label} argument {index + 1} is named {wanted!r}, not {label!r}",
                    call.span,
                    hint=f"parameters, in order: {known}",
                )

    def bind_output(
        self, call: Call, output_type: Type, bindings: dict[str, Type], label: str
    ) -> None:
        if call.output is None:
            if output_type.name != "unit":
                raise CheckError(
                    f"the result of {label} is discarded",
                    call.span,
                    hint="bind it with '-> name', or remove the call",
                )
            return
        if output_type.name == "unit":
            raise CheckError(
                f"{label} produces no value, so it cannot be bound to {call.output!r}",
                call.span,
            )
        if call.output in bindings:
            raise CheckError(
                f"{call.output!r} is already bound",
                call.span,
                hint="bindings are single-assignment; pick a new name",
            )
        if call.output.startswith("_pb"):
            raise CheckError(
                f"{call.output!r} uses the reserved '_pb' prefix",
                call.span,
                hint="generated code reserves it so emitted source can never "
                "collide with a name you chose",
            )
        bindings[call.output] = output_type

    # -- arguments -------------------------------------------------------

    def type_of(
        self, arg: Arg, bindings: dict[str, Type], expected: Type, span: Span
    ) -> Type:
        if isinstance(arg, Literal):
            return arg.type
        if isinstance(arg, Ref):
            known = bindings.get(arg.name)
            if known is None:
                raise CheckError(
                    f"{arg.name!r} is not bound",
                    span,
                    hint="values must be produced by an earlier line before they can be used",
                )
            return known
        if isinstance(arg, AddressRef):
            return self.callable_type(arg.address, span, expected)
        raise CheckError(f"unsupported argument {arg!r}", span)

    def callable_type(self, address: str, span: Span, expected: Type) -> Type:
        """An address used as a value is a callable, whatever it points at."""
        if area_of(address) == LOCAL_AREA:
            signature = self.ext_signatures.get(address)
            if signature is None:
                raise CheckError(
                    f"local extension {address} is used as a callable but never defined",
                    span,
                )
            return signature
        entry = self.registry.get(address)
        if entry is None:
            raise CheckError(f"no such address: {address}", span)
        if entry.contract.variadic:
            raise CheckError(
                f"{entry.label} is variadic and cannot be passed as a callable",
                span,
                hint="wrap it in a local 000 extension with a fixed arity",
            )
        params = tuple(p.type for p in entry.contract.inputs)
        return Type("callable", (*params, entry.contract.output.type))


def _free_vars(t: Type) -> set[str]:
    if t.is_var:
        return {t.name}
    out: set[str] = set()
    for arg in t.args:
        out |= _free_vars(arg)
    return out
