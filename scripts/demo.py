"""The proof: one script, one registry, three execution paths, identical output.

For every example this runs the interpreter, the generated Python, and the
generated Rust, and compares the bytes each one writes to standard output. If
the table comes back all PASS, the claim this whole project exists to test is
empirically true and anyone can re-run it in one command.

    python scripts/demo.py [--no-rust] [--report demo_report.md]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
RUNTIME_PY = ROOT / "runtime" / "python"
RUST_PROJECT = ROOT / "generated" / "rust"

EXAMPLES = ["line_count", "word_freq", "records", "audit_demo"]

sys.path[:0] = [str(SRC), str(RUNTIME_PY)]

from phonebook.checker import check  # noqa: E402
from phonebook.emit.python import emit as emit_python  # noqa: E402
from phonebook.emit.rust import emit as emit_rust  # noqa: E402
from phonebook.parser import parse_file  # noqa: E402
from phonebook.registry import Registry  # noqa: E402
from phonebook.resolver import Backend  # noqa: E402

GREEN = "\033[32m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
DIM = "\033[2m" if sys.stdout.isatty() else ""
OFF = "\033[0m" if sys.stdout.isatty() else ""


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(RUNTIME_PY), env.get("PYTHONPATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def cargo_target_dir() -> str:
    """Keep build artifacts off a synced folder.

    OneDrive both slows cargo down and occasionally locks files mid-build, so
    the target directory goes to the system temp area unless the caller has
    already chosen one.
    """
    existing = os.environ.get("CARGO_TARGET_DIR")
    if existing:
        return existing
    return str(Path(tempfile.gettempdir()) / "phonebook-cargo-target")


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(),
        **kwargs,
    )


def interpret(name: str) -> str:
    result = run([sys.executable, "-m", "phonebook.cli", "run", f"examples/{name}.phone"])
    if result.returncode != 0:
        raise SystemExit(f"interpreter failed on {name}:\n{result.stderr}")
    return result.stdout


def python_output(name: str, registry: Registry, backend: Backend) -> str:
    checked = check(parse_file(ROOT / "examples" / f"{name}.phone"), registry)
    target = ROOT / "generated" / f"{name}.py"
    target.write_text(emit_python(checked, backend), encoding="utf-8", newline="\n")
    result = run([sys.executable, str(target)])
    if result.returncode != 0:
        raise SystemExit(f"generated Python failed on {name}:\n{result.stderr}")
    return result.stdout


def emit_all_rust(registry: Registry, backend: Backend) -> None:
    destination = RUST_PROJECT / "src" / "bin"
    destination.mkdir(parents=True, exist_ok=True)
    for name in EXAMPLES:
        checked = check(parse_file(ROOT / "examples" / f"{name}.phone"), registry)
        (destination / f"{name}.rs").write_text(
            emit_rust(checked, backend), encoding="utf-8", newline="\n"
        )


def build_rust() -> Path:
    target_dir = cargo_target_dir()
    env = child_env()
    env["CARGO_TARGET_DIR"] = target_dir
    result = subprocess.run(
        ["cargo", "build", "--quiet"],
        cwd=str(RUST_PROJECT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        raise SystemExit(f"cargo build failed:\n{result.stdout}\n{result.stderr}")
    return Path(target_dir) / "debug"


def rust_output(name: str, binaries: Path) -> str:
    executable = binaries / (name + (".exe" if os.name == "nt" else ""))
    result = run([str(executable)])
    if result.returncode != 0:
        raise SystemExit(f"generated Rust failed on {name}:\n{result.stderr}")
    return result.stdout


def normalize(text: str) -> str:
    """Compare line endings as content, not as platform noise."""
    return text.replace("\r\n", "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-rust", action="store_true", help="skip the Rust backend")
    parser.add_argument("--report", help="write a markdown report to this path")
    args = parser.parse_args()

    use_rust = not args.no_rust and shutil.which("cargo") is not None
    if not args.no_rust and not use_rust:
        print(f"{DIM}cargo not found — running without the Rust backend{OFF}\n")

    registry = Registry.load()
    python_backend = Backend.load("python")
    rust_backend = Backend.load("rust")

    binaries: Path | None = None
    if use_rust:
        emit_all_rust(registry, rust_backend)
        print(f"{DIM}building generated Rust…{OFF}")
        binaries = build_rust()

    print()
    header = f"{'example':<14} {'interpret':>10} {'python':>10} {'rust':>10}   verdict"
    print(header)
    print("-" * len(header))

    rows: list[tuple[str, str, bool]] = []
    failures = 0
    for name in EXAMPLES:
        reference = normalize(interpret(name))
        produced = normalize(python_output(name, registry, python_backend))
        results = {"interpret": reference, "python": produced}
        if binaries is not None:
            results["rust"] = normalize(rust_output(name, binaries))

        agree = all(value == reference for value in results.values())
        cells = []
        for column in ("interpret", "python", "rust"):
            if column not in results:
                cells.append(f"{'skip':>10}")
            elif results[column] == reference:
                cells.append(f"{GREEN}{'ok':>10}{OFF}")
            else:
                cells.append(f"{RED}{'DIFFERS':>10}{OFF}")
        verdict = f"{GREEN}PASS{OFF}" if agree else f"{RED}FAIL{OFF}"
        print(f"{name:<14} {' '.join(cells)}   {verdict}")

        if not agree:
            failures += 1
            for column, value in results.items():
                if value != reference:
                    print(f"    {column} produced:\n{value}")
                    print(f"    interpreter produced:\n{reference}")
        rows.append((name, reference, agree))

    print()
    paths = 3 if binaries is not None else 2
    if failures:
        print(f"{RED}{failures} example(s) disagree across backends{OFF}")
    else:
        print(
            f"{GREEN}all {len(EXAMPLES)} examples produced identical output "
            f"through {paths} independent paths{OFF}"
        )

    if args.report:
        write_report(Path(args.report), rows, binaries is not None)
        print(f"wrote {args.report}")
    return 1 if failures else 0


def write_report(path: Path, rows, with_rust: bool) -> None:
    lines = [
        "# Demo report",
        "",
        "Every example below was run three ways from a single `.phone` source:",
        "interpreted through the Python runtime, compiled to Python and executed,",
        "and compiled to Rust and executed. The output column is the bytes all",
        "paths produced — not a sample of one of them.",
        "",
        f"Rust backend: {'included' if with_rust else 'SKIPPED (cargo not found)'}",
        "",
    ]
    for name, output, agree in rows:
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"`examples/{name}.phone` — {'identical' if agree else 'DISAGREEMENT'}")
        lines.append("")
        lines.append("```")
        lines.append(output.rstrip("\n") or "(no output)")
        lines.append("```")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
