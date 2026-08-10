"""What does this program actually do?

Two structural facts make this report possible, and neither is available in an
ordinary language:

1. Every global address has a frozen contract that declares its effects, so a
   program's capabilities can be computed rather than guessed at.
2. Local (000) extensions are the only place user-defined behavior can live, so
   the set of code a human must actually read is enumerable and short.

What this does not claim: that a local extension is safe. It claims the review
surface is small, complete, and cannot grow without showing up here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .checker import CheckedCall, CheckedProgram
from .nodes import AddressRef, Literal, Ref
from .registry import LOCAL_AREA, area_of

CAPABILITIES = [
    ("filesystem-read", "reads files"),
    ("filesystem-write", "writes files"),
    ("network", "talks to the network"),
    ("process", "starts processes"),
    ("stdout", "writes to the console"),
]

#: Capabilities that make a program more than pure computation plus console output.
SENSITIVE = {"filesystem-read", "filesystem-write", "network", "process"}


@dataclass
class Finding:
    kind: str
    detail: str


@dataclass
class Report:
    path: str
    capabilities: dict[str, list[CheckedCall]]
    flow: list[tuple[int, CheckedCall]]
    local_extensions: list
    unpinned: list[str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def sensitive(self) -> set[str]:
        return {c for c in self.capabilities if c in SENSITIVE}

    @property
    def needs_review(self) -> bool:
        return bool(self.local_extensions) or bool(self.sensitive)


def audit(checked: CheckedProgram) -> Report:
    capabilities: dict[str, list[CheckedCall]] = {}
    for call in checked.all_calls():
        for effect in call.effects:
            capabilities.setdefault(effect, []).append(call)

    flow = list(enumerate(checked.body, start=1))

    findings: list[Finding] = []
    for call in checked.all_calls():
        if "filesystem-read" in call.effects or "filesystem-write" in call.effects:
            first = call.call.args[0] if call.call.args else None
            if not isinstance(first, Literal):
                findings.append(
                    Finding(
                        "dynamic-path",
                        f"{call.address} {call.name} on line {call.call.span.line}: the path is "
                        f"computed at run time, not a literal",
                    )
                )

    for address, extension in checked.program.extensions.items():
        reach = [
            c.address
            for c in checked.extensions[address].calls
            if area_of(c.address) == LOCAL_AREA
        ]
        if reach:
            findings.append(
                Finding(
                    "nested-local",
                    f"{address} {extension.name} calls other local extensions: "
                    + ", ".join(sorted(set(reach))),
                )
            )

    unpinned = sorted(
        {
            call.address
            for call in checked.all_calls()
            if area_of(call.address) != LOCAL_AREA
            and call.call.selector.kind == "latest"
            and call.address not in checked.program.pins
        }
    )

    return Report(
        path=checked.program.path,
        capabilities=capabilities,
        flow=flow,
        local_extensions=[checked.extensions[a] for a in sorted(checked.program.extensions)],
        unpinned=unpinned,
        findings=findings,
    )


def render(report: Report, show_bodies: bool = True) -> str:
    out: list[str] = []
    out.append(f"AUDIT  {report.path.replace(chr(92), '/')}")
    out.append("")

    out.append("CAPABILITIES")
    for effect, phrase in CAPABILITIES:
        calls = report.capabilities.get(effect, [])
        if not calls:
            out.append(f"  {effect:<18} not used")
            continue
        out.append(f"  {effect:<18} {len(calls)} call(s) — {phrase}")
        for call in calls:
            out.append(f"      {call.address} {call.name}  {_args(call)}")
    out.append("")

    out.append("INTENT — what the program does, in order")
    for index, call in report.flow:
        target = f" -> {call.call.output}" if call.call.output else ""
        marker = "*" if call.is_local else " "
        out.append(f"  {index:>3}{marker} {call.name:<18} {_args(call)}{target}")
    if any(call.is_local for _, call in report.flow):
        out.append("      (* = a local extension, defined in this file)")
    out.append("")

    count = len(report.local_extensions)
    if count:
        out.append(f"LOCAL EXTENSIONS — {count} to read by hand")
        out.append("  These are the only places this program can do something the")
        out.append("  phonebook has not already described. Everything else is a")
        out.append("  frozen contract. This list is the complete review surface.")
        for checked_ext in report.local_extensions:
            extension = checked_ext.extension
            out.append("")
            out.append(f"  {extension.address}  {extension.name}   (line {extension.span.line})")
            if show_bodies:
                for line in extension.source:
                    out.append(f"      {line}")
    else:
        out.append("LOCAL EXTENSIONS — none")
        out.append("  Every operation in this program is a registered address with a")
        out.append("  frozen contract. There is no custom logic to review.")
    out.append("")

    if report.findings:
        out.append("NOTES")
        for finding in report.findings:
            out.append(f"  [{finding.kind}] {finding.detail}")
        out.append("")

    out.append("VERSION POLICY")
    if report.unpinned:
        out.append(
            f"  {len(report.unpinned)} address(es) resolve with @latest; "
            "behavior may change when an implementation is upgraded"
        )
        out.append("  " + ", ".join(report.unpinned))
    else:
        out.append("  every address is pinned")
    out.append("")

    if report.needs_review:
        parts = []
        if report.sensitive:
            parts.append(", ".join(sorted(report.sensitive)))
        if report.local_extensions:
            parts.append(f"{len(report.local_extensions)} local extension(s)")
        out.append("VERDICT  needs review: " + "; ".join(parts))
    else:
        out.append("VERDICT  pure computation and console output, no local code")
    return "\n".join(out)


def _args(call: CheckedCall) -> str:
    rendered = []
    for arg in call.call.args:
        if isinstance(arg, Literal):
            rendered.append(_literal(arg.value))
        elif isinstance(arg, Ref):
            rendered.append(arg.name)
        elif isinstance(arg, AddressRef):
            rendered.append(arg.address)
    return "[" + ", ".join(rendered) + "]"


def _literal(value: object) -> str:
    """Render a literal on one line — a report that reflows is a report nobody reads."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    return str(value)
