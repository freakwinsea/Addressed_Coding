"""Mutation detection: what does each arm reject before the program runs?

The first study asked whether models *write* `.phone` more reliably than Python
and got a null result — three models, sixty programs, sixty correct. The thing
that differed in every run was not generation but verification, so this measures
that instead, and it needs no model runs at all.

Method, which is standard mutation testing with one addition:

1. Take known-correct programs in both arms.
2. Apply single-point mutations of the same *classes* to each — the kinds of
   mistake the runs actually produced: a mistyped address, a swapped argument,
   a wrong operation, a stale name.
3. Discard **equivalent mutants**: if a mutation does not change what the
   program prints, failing to catch it is not a failure. This is the step that
   makes the numbers mean anything, and it costs a run of every mutant.
4. Of the mutants that *do* change behavior, ask what fraction each arm rejects
   **statically**, before execution.

Fairness matters more than the result here. `dial check` is compared against
Python's best realistic static tooling — `compile`, then ruff, then mypy —
because comparing a type checker to a syntax check would stack the deck and
prove nothing. Whatever is installed is used and reported.

    python scripts/mutation_study.py [--report FILE] [--verbose]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHONE_SOURCES = ROOT / "experiments" / "reference"
PYTHON_SOURCES = ROOT / "experiments" / "runs" / "run5-control-python"

ADDRESS = re.compile(r"\b([0-9]{3})-([0-9]{7})\b")
CALL_LINE = re.compile(r"^(\s*)([0-9]{3}-[0-9]{7})(@\[)(.*?)(\])(.*)$")

SEED = 20260810


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


@dataclass
class Mutant:
    arm: str
    program: str
    operator: str
    source: str
    detail: str
    caught_by: str = ""
    changed_behavior: bool | None = None
    equivalent: bool = False

    @property
    def caught(self) -> bool:
        return bool(self.caught_by)


@dataclass
class Arm:
    name: str
    tools: list[str] = field(default_factory=list)
    mutants: list[Mutant] = field(default_factory=list)


# --------------------------------------------------------------------------
# mutation operators
# --------------------------------------------------------------------------


def phone_mutants(name: str, source: str, rng: random.Random) -> list[Mutant]:
    """Single-point mutations of a .phone program."""
    out: list[Mutant] = []
    lines = source.splitlines()

    def emit(operator: str, index: int, replacement: str, detail: str) -> None:
        mutated = list(lines)
        mutated[index] = replacement
        out.append(Mutant("phone", name, operator, "\n".join(mutated) + "\n", detail))

    for i, line in enumerate(lines):
        match = CALL_LINE.match(line)
        if not match:
            continue
        indent, address, opener, args, closer, tail = match.groups()
        area, number = address.split("-")

        # A mistyped address — the mistake run 3 actually made.
        if not address.startswith("000-"):
            dropped = f"{area}-{number[:-1]}"
            emit("mistyped_address", i, f"{indent}{dropped}{opener}{args}{closer}{tail}",
                 f"{address} -> {dropped}")
            digits = list(number)
            pos = rng.randrange(len(digits))
            digits[pos] = str((int(digits[pos]) + 1) % 10)
            wrong = f"{area}-{''.join(digits)}"
            if wrong != address:
                emit("wrong_address", i, f"{indent}{wrong}{opener}{args}{closer}{tail}",
                     f"{address} -> {wrong}")

        parts = [a.strip() for a in args.split(",")]
        if len(parts) >= 2:
            swapped = list(parts)
            swapped[0], swapped[1] = swapped[1], swapped[0]
            emit("swapped_arguments", i,
                 f"{indent}{address}{opener}{', '.join(swapped)}{closer}{tail}",
                 f"args 1<->2 of {address}")
            emit("dropped_argument", i,
                 f"{indent}{address}{opener}{', '.join(parts[:-1])}{closer}{tail}",
                 f"dropped last arg of {address}")

        # A stale name: reference something that is never bound.
        for j, part in enumerate(parts):
            if re.fullmatch(r"[a-z_][a-z0-9_]*", part):
                renamed = list(parts)
                renamed[j] = part + "_x"
                emit("undefined_name", i,
                     f"{indent}{address}{opener}{', '.join(renamed)}{closer}{tail}",
                     f"{part} -> {part}_x")
                break
    return out


PY_OPERATIONS = {
    "sum": "max", "max": "min", "min": "max", "len": "sorted",
    "sorted": "reversed", "set": "list", "int": "float",
}


def python_mutants(name: str, source: str, rng: random.Random) -> list[Mutant]:
    """The same mutation classes, applied to a Python program via its AST."""
    out: list[Mutant] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out

    def emit(operator: str, node: ast.AST, replacement: str, detail: str) -> None:
        try:
            segment = ast.get_source_segment(source, node)
        except Exception:
            return
        if not segment or segment not in source:
            return
        out.append(
            Mutant("python", name, operator, source.replace(segment, replacement, 1), detail)
        )

    names = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            swap = PY_OPERATIONS.get(node.func.id)
            if swap:
                segment = ast.get_source_segment(source, node)
                if segment:
                    emit("wrong_operation", node,
                         segment.replace(node.func.id, swap, 1), f"{node.func.id} -> {swap}")
            if len(node.args) >= 2:
                segment = ast.get_source_segment(source, node)
                a = ast.get_source_segment(source, node.args[0])
                b = ast.get_source_segment(source, node.args[1])
                if segment and a and b and a != b:
                    swapped = segment.replace(a, "\x00", 1).replace(b, a, 1).replace("\x00", b, 1)
                    emit("swapped_arguments", node, swapped, f"args 1<->2 of {node.func.id}")
                emit("dropped_argument", node,
                     segment.replace(f", {b}", "", 1) if segment and b else "",
                     f"dropped arg of {node.func.id}")

    # A stale name, matching the .phone operator.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in names:
            if node.id in dir(__builtins__) or node.id in PY_OPERATIONS:
                continue
            emit("undefined_name", node, node.id + "_x", f"{node.id} -> {node.id}_x")
            break

    return [m for m in out if m.source.strip()]


# --------------------------------------------------------------------------
# checking and running
# --------------------------------------------------------------------------


def env() -> dict[str, str]:
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT / "runtime" / "python")]),
        PYTHONIOENCODING="utf-8",
    )


def shell(command: list[str], cwd: Path = ROOT, timeout: int = 60):
    return subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env(), timeout=timeout,
    )


def check_phone(path: Path) -> str:
    """`dial check` — contracts, types, arity, addresses. No execution."""
    result = shell([sys.executable, "-m", "phonebook.cli", "check", str(path)])
    return "dial check" if result.returncode != 0 else ""


def check_python(path: Path, tools: list[str]) -> str:
    """Python's best realistic static analysis, in increasing order of power."""
    result = shell([sys.executable, "-c", f"compile(open(r'{path}',encoding='utf-8').read(),'m','exec')"])
    if result.returncode != 0:
        return "compile"
    if "ruff" in tools:
        result = shell([sys.executable, "-m", "ruff", "check", "--no-cache",
                        "--select", "F,E9", str(path)])
        if result.returncode != 0:
            return "ruff"
    if "mypy" in tools:
        result = shell([sys.executable, "-m", "mypy", "--no-error-summary",
                        "--ignore-missing-imports", "--cache-dir", os.devnull, str(path)])
        if result.returncode != 0:
            return "mypy"
    return ""


def run_program(path: Path, arm: str) -> tuple[int, str]:
    try:
        if arm == "phone":
            r = shell([sys.executable, "-m", "phonebook.cli", "run", str(path)], timeout=30)
        else:
            r = shell([sys.executable, str(path)], timeout=30)
        return r.returncode, r.stdout.replace("\r\n", "\n")
    except subprocess.TimeoutExpired:
        return -1, "<timeout>"


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def load(arm: str) -> dict[str, str]:
    directory = PHONE_SOURCES if arm == "phone" else PYTHON_SOURCES
    pattern = "*.phone" if arm == "phone" else "t*.py"
    return {p.stem[:3]: p.read_text(encoding="utf-8") for p in sorted(directory.glob(pattern))}


def study(arm: str, tools: list[str], workspace: Path, verbose: bool) -> Arm:
    rng = random.Random(SEED)
    programs = load(arm)
    suffix = ".phone" if arm == "phone" else ".py"
    result = Arm(arm, tools)

    baselines: dict[str, tuple[int, str]] = {}
    for name, source in programs.items():
        path = workspace / f"base_{name}{suffix}"
        path.write_text(source, encoding="utf-8", newline="\n")
        baselines[name] = run_program(path, arm)

    generate = phone_mutants if arm == "phone" else python_mutants
    for name, source in programs.items():
        for mutant in generate(name, source, rng):
            path = workspace / f"m_{name}_{len(result.mutants)}{suffix}"
            path.write_text(mutant.source, encoding="utf-8", newline="\n")

            mutant.caught_by = (
                check_phone(path) if arm == "phone" else check_python(path, tools)
            )
            code, output = run_program(path, arm)
            base_code, base_output = baselines[name]
            mutant.changed_behavior = (code, output) != (base_code, base_output)
            mutant.equivalent = not mutant.changed_behavior
            result.mutants.append(mutant)
            if verbose:
                flag = "equiv " if mutant.equivalent else ("CAUGHT" if mutant.caught else "escaped")
                print(f"  {flag}  {name} {mutant.operator:<18} {mutant.detail}")
    return result


def report(arms: list[Arm]) -> str:
    lines: list[str] = []
    operators = sorted({m.operator for a in arms for m in a.mutants})

    lines.append("")
    lines.append("Static detection of behaviour-changing mutants")
    lines.append("")
    header = f"{'mutation':<20}" + "".join(f"{a.name:>18}" for a in arms)
    lines.append(header)
    lines.append("-" * len(header))
    for operator in operators:
        row = f"{operator:<20}"
        for arm in arms:
            live = [m for m in arm.mutants if m.operator == operator and not m.equivalent]
            if not live:
                row += f"{'—':>18}"
                continue
            caught = sum(1 for m in live if m.caught)
            row += f"{f'{caught}/{len(live)}':>18}"
        lines.append(row)
    lines.append("-" * len(header))

    # Operators only one arm can express (a mistyped address has no Python twin;
    # substituting a valid-but-wrong builtin has no .phone twin) inflate whichever
    # arm owns them. The shared subtotal is the comparison that means something.
    shared = {
        op
        for op in operators
        if all(any(m.operator == op and not m.equivalent for m in a.mutants) for a in arms)
    }

    for label, keep in (("SHARED OPERATORS", shared), ("all operators", set(operators))):
        row = f"{label:<20}"
        for arm in arms:
            live = [m for m in arm.mutants if not m.equivalent and m.operator in keep]
            caught = sum(1 for m in live if m.caught)
            pct = f"{100 * caught // len(live)}%" if live else "n/a"
            row += f"{f'{caught}/{len(live)}  {pct}':>18}"
        lines.append(row)
    lines.append("")
    lines.append(f"shared operators: {', '.join(sorted(shared)) or 'none'}")
    lines.append(
        "arm-specific:     "
        + ", ".join(sorted(set(operators) - shared))
        + "  (excluded from the shared subtotal)"
    )
    lines.append("")

    for arm in arms:
        equivalent = sum(1 for m in arm.mutants if m.equivalent)
        lines.append(
            f"{arm.name:<8} {len(arm.mutants)} mutants, {equivalent} equivalent (discarded), "
            f"tools: {', '.join(arm.tools) or 'compile only'}"
        )
        by_tool: dict[str, int] = {}
        for m in arm.mutants:
            if m.caught and not m.equivalent:
                by_tool[m.caught_by] = by_tool.get(m.caught_by, 0) + 1
        if by_tool:
            detail = ", ".join(f"{k}: {v}" for k, v in sorted(by_tool.items()))
            lines.append(f"{'':<8} caught by — {detail}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="write a markdown report here")
    parser.add_argument("--json", help="write raw results here")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    tools = [t for t in ("ruff", "mypy") if shutil.which(t) or _module(t)]
    print(f"python static tools available: {', '.join(tools) or 'none — compile only'}")

    arms: list[Arm] = []
    with tempfile.TemporaryDirectory(prefix="phonebook-mutation-") as tmp:
        workspace = Path(tmp)
        for arm in ("phone", "python"):
            print(f"mutating the {arm} arm…")
            arms.append(study(arm, tools, workspace, args.verbose))

    text = report(arms)
    print(text)

    if args.json:
        Path(args.json).write_text(
            json.dumps([[m.__dict__ for m in a.mutants] for a in arms], indent=2),
            encoding="utf-8",
        )
    if args.report:
        Path(args.report).write_text(
            "# Mutation detection\n\n```\n" + text + "\n```\n", encoding="utf-8", newline="\n"
        )
        print(f"\nwrote {args.report}")
    return 0


def _module(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


if __name__ == "__main__":
    raise SystemExit(main())
