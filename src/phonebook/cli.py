"""`dial` — the command line for the phonebook.

Half of these commands exist to answer the objection that nobody can read a
seven-digit number: `show`, `search`, `next`, and `annotate` are the directory
assistance that makes the numbers usable. They shipped before the interpreter
did, on purpose.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phonebook_rt import PhonebookFault

from . import __version__
from .audit import audit as run_audit
from .audit import render as render_audit
from .checker import check
from .errors import CheckError, ParseError, PhonebookError, RegistryError
from .parser import parse_file, strip_comment
from .registry import LOCAL_AREA, Registry, area_of, lint
from .resolver import Backend
from .search import Index, describe_signature, successors

TARGETS = ("python", "rust")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def load_program(path: str, registry: Registry):
    return check(parse_file(path), registry)


def wrap(text: str, width: int, indent: str) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(indent + current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(indent + current)
    return lines


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_run(args) -> int:
    registry = Registry.load()
    checked = load_program(args.file, registry)
    from .interpreter import run as interpret

    interpret(checked, Backend.load("python"), trace=args.trace)
    return 0


def cmd_check(args) -> int:
    registry = Registry.load()
    checked = load_program(args.file, registry)
    calls = sum(1 for _ in checked.all_calls())
    effects = ", ".join(sorted(checked.effects)) or "none"
    print(f"ok  {args.file}")
    print(f"    {calls} calls, {len(checked.extensions)} local extension(s)")
    print(f"    effects: {effects}")
    return 0


def cmd_show(args) -> int:
    registry = Registry.load()
    entry = registry.get(args.address) or registry.by_name.get(args.address.upper())
    if entry is None:
        print(f"no such address: {args.address}", file=sys.stderr)
        index = Index(registry)
        hits = index.search(args.address, limit=3)
        if hits:
            print("did you mean:", file=sys.stderr)
            for hit in hits:
                print(f"  {hit.entry.address}  {hit.entry.name}", file=sys.stderr)
        return 1

    contract = entry.contract
    print(f"{entry.address}   {entry.name}")
    print(f"  {entry.summary}")
    print()
    print(f"  signature   {describe_signature(entry)}")
    print(f"  contract    v{contract.version}   ({entry.status}, since {entry.since})")
    print(f"  purity      {contract.purity}, {contract.determinism}")
    print(f"  effects     {', '.join(contract.effects) or 'none'}")
    print(f"  errors      {', '.join(contract.errors) or 'none'}")
    if contract.constraints:
        shown = ", ".join(f"{k} must be {v}" for k, v in contract.constraints.items())
        print(f"  constraints {shown}")
    if entry.description:
        print()
        for line in wrap(entry.description, 72, "  "):
            print(line)
    if contract.notes:
        print()
        print("  semantics pinned by this contract:")
        for note in contract.notes:
            for i, line in enumerate(wrap(note, 68, "")):
                print(f"    {'- ' if i == 0 else '  '}{line}")
    if entry.examples:
        print()
        print("  example")
        for example in entry.examples:
            print(f"    {example}")

    if args.backends:
        print()
        for target in TARGETS:
            try:
                backend = Backend.load(target)
            except CheckError:
                continue
            for impl in backend.implementations(entry.address):
                print(f"  {target:<7} impl:{impl.impl}  {impl.runtime}")
                if impl.inline:
                    print(f"          {'':<9} inline: {impl.inline}")
    return 0


def cmd_search(args) -> int:
    registry = Registry.load()
    hits = Index(registry).search(args.query, limit=args.limit)
    if not hits:
        print("nothing matched", file=sys.stderr)
        return 1
    for hit in hits:
        print(f"{hit.entry.address}  {hit.entry.name:<18} {hit.entry.summary}")
        print(f"{'':<12}  {describe_signature(hit.entry)}")
    return 0


def cmd_next(args) -> int:
    registry = Registry.load()
    found = successors(registry, args.produces, limit=args.limit)
    if not found:
        print(f"nothing accepts {args.produces} as its first argument", file=sys.stderr)
        return 1
    print(f"holding a {args.produces}, you can dial:")
    for entry in found:
        print(f"  {entry.address}  {entry.name:<18} {describe_signature(entry)}")
    return 0


def cmd_annotate(args) -> int:
    registry = Registry.load()
    program = parse_file(args.file)
    check(program, registry)  # annotate only makes sense for a valid program

    names: dict[int, str] = {}
    for call in program.calls():
        if area_of(call.address) == LOCAL_AREA:
            extension = program.extensions.get(call.address)
            names[call.span.line] = f"{extension.name} (local)" if extension else "?"
        else:
            entry = registry.get(call.address)
            names[call.span.line] = entry.name if entry else "?"
    for extension in program.extensions.values():
        names[extension.span.line] = f"defines {extension.name}"

    width = max((len(strip_comment(line).rstrip()) for line in program.lines), default=0)
    for number, line in enumerate(program.lines, start=1):
        bare = strip_comment(line).rstrip()
        name = names.get(number)
        if name:
            print(f"{number:>4}  {bare.ljust(width)}   {name}")
        else:
            print(f"{number:>4}  {line.rstrip()}")
    return 0


def cmd_audit(args) -> int:
    registry = Registry.load()
    checked = load_program(args.file, registry)
    report = run_audit(checked)
    print(render_audit(report, show_bodies=not args.no_bodies))
    if args.strict and report.needs_review:
        sys.stdout.flush()
        print(file=sys.stderr)
        print("strict: this program needs human review before it is trusted", file=sys.stderr)
        return 1
    return 0


def cmd_emit(args) -> int:
    registry = Registry.load()
    checked = load_program(args.file, registry)
    backend = Backend.load(args.target)

    if args.target == "python":
        from .emit.python import emit
    else:
        from .emit.rust import emit

    source = emit(checked, backend)
    if args.output:
        destination = Path(args.output)
        if destination.is_dir():
            suffix = ".py" if args.target == "python" else ".rs"
            destination = destination / (Path(args.file).stem + suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8", newline="\n")
        print(f"wrote {destination.as_posix()}")
    else:
        sys.stdout.write(source)
    return 0


def cmd_registry(args) -> int:
    registry = Registry.load()
    if args.action == "lint":
        problems = lint(registry)
        for target in TARGETS:
            try:
                problems += Backend.load(target).audit_against(registry)
            except CheckError as exc:
                problems.append(str(exc))
        problems += registry.verify_frozen()
        if problems:
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print(f"\n{len(problems)} problem(s)", file=sys.stderr)
            return 1
        print(f"ok  {len(registry)} addresses, both backends complete, ledger holds")
        return 0

    if args.action == "freeze":
        added, unchanged = registry.freeze()
        print(f"ledger: {added} newly issued, {unchanged} already recorded")
        return 0

    if args.action == "list":
        for area, entries in sorted(registry.areas().items()):
            print(f"{area}  ({len(entries)})")
            for entry in entries:
                print(f"  {entry.address}  {entry.name:<18} {entry.summary}")
        return 0
    return 1


def cmd_brief(args) -> int:
    """Print (or refresh) everything a newcomer needs to write a program."""
    from .brief import cheatsheet, guide_path, render_guide

    registry = Registry.load()
    if args.table_only:
        sys.stdout.write(cheatsheet(registry, notes=not args.no_notes))
        return 0

    refreshed = render_guide(registry)
    path = guide_path(registry)
    if args.write:
        if path.read_text(encoding="utf-8") == refreshed:
            print(f"{path.name} is already current")
            return 0
        path.write_text(refreshed, encoding="utf-8", newline="\n")
        print(f"refreshed the address table in {path.as_posix()}")
        return 0
    sys.stdout.write(refreshed)
    return 0


def cmd_conformance(args) -> int:
    from .conformance import run_suite

    return run_suite(args.backend, verbose=args.verbose, record=args.record)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dial",
        description="Route a program through the phonebook.",
    )
    parser.add_argument("--version", action="version", version=f"phonebook {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="interpret a .phone program")
    p.add_argument("file")
    p.add_argument("--trace", action="store_true", help="log resolved names to stderr")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check", help="validate contracts without running anything")
    p.add_argument("file")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("emit", help="generate source for a backend")
    p.add_argument("file")
    p.add_argument("--target", choices=TARGETS, required=True)
    p.add_argument("-o", "--output", help="file or directory to write to")
    p.set_defaults(func=cmd_emit)

    p = sub.add_parser("show", help="directory assistance for one address")
    p.add_argument("address", help="an address, or a name like FILTER")
    p.add_argument("--backends", action="store_true", help="also show how each backend keeps it")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("search", help="find an address by describing what you want")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=5)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("next", help="what can be dialed with the value you are holding")
    p.add_argument("--produces", required=True, help="a type, e.g. 'list<text>'")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("annotate", help="show a program with every address resolved")
    p.add_argument("file")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("audit", help="report what a program can actually do")
    p.add_argument("file")
    p.add_argument("--strict", action="store_true", help="exit non-zero if review is needed")
    p.add_argument("--no-bodies", action="store_true", help="omit local extension source")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser(
        "brief",
        help="print everything needed to write a .phone program — paste this into a model",
    )
    p.add_argument("--table-only", action="store_true", help="just the address table")
    p.add_argument("--no-notes", action="store_true", help="omit the pinned-semantics notes")
    p.add_argument(
        "--write",
        action="store_true",
        help="refresh the generated table inside docs/WRITING-PHONE.md",
    )
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("conformance", help="run the cross-backend conformance suite")
    p.add_argument("--backend", choices=TARGETS + ("interpreter",), default="interpreter")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument(
        "--record",
        action="store_true",
        help="overwrite the .expected files from this backend (review the diff before committing)",
    )
    p.set_defaults(func=cmd_conformance)

    p = sub.add_parser("registry", help="inspect and maintain the phonebook itself")
    p.add_argument("action", choices=("lint", "freeze", "list"))
    p.set_defaults(func=cmd_registry)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ParseError, CheckError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RegistryError as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 3
    except PhonebookFault as exc:
        print(f"fault: {exc}", file=sys.stderr)
        return 4
    except PhonebookError as exc:  # pragma: no cover - defensive
        print(f"error: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
