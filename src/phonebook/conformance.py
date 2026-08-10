"""The cross-backend conformance suite.

Each case in `tests/conformance/` is a .phone program with a committed
`.expected` file. A backend conforms when running the program through it
produces those exact bytes.

Expressing conformance as programs rather than as serialized call/response
fixtures means one suite covers every execution path without a separate harness
per language — and it means the suite is written in the language it tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .checker import check
from .parser import parse_file
from .registry import Registry, default_root
from .resolver import Backend

RUST_PROJECT_TOML = """\
[package]
name = "phonebook_conformance"
version = "0.1.0"
edition = "2021"
publish = false

[dependencies]
phonebook_rt = {{ path = "{runtime}" }}

[workspace]
"""


def repo_root() -> Path:
    return default_root().parent


def cases() -> list[Path]:
    return sorted((repo_root() / "tests" / "conformance").glob("*.phone"))


def expected_path(case: Path) -> Path:
    return case.with_suffix(".expected")


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def child_env() -> dict[str, str]:
    root = repo_root()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "runtime" / "python"), env.get("PYTHONPATH", "")]
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd or repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(),
    )


# --------------------------------------------------------------------------
# the three execution paths
# --------------------------------------------------------------------------


def via_interpreter(case: Path) -> str:
    import contextlib
    import io

    from .interpreter import Interpreter, Trace

    registry = Registry.load()
    checked = check(parse_file(case), registry)

    buffer = io.StringIO()
    # Cases name their data with repo-relative paths, so the working directory
    # is part of the contract they are written against.
    previous = Path.cwd()
    os.chdir(repo_root())
    try:
        with contextlib.redirect_stdout(buffer):
            Interpreter(checked, Backend.load("python"), Trace()).run()
    finally:
        os.chdir(previous)
    return normalize(buffer.getvalue())


def via_python(case: Path, workspace: Path) -> str:
    from .emit.python import emit

    registry = Registry.load()
    checked = check(parse_file(case), registry)
    target = workspace / (case.stem + ".py")
    target.write_text(emit(checked, Backend.load("python")), encoding="utf-8", newline="\n")
    result = _run([sys.executable, str(target)])
    if result.returncode != 0:
        raise RuntimeError(f"{case.name}: generated Python failed\n{result.stderr}")
    return normalize(result.stdout)


def build_rust(workspace: Path) -> Path:
    """Compile every case into a throwaway cargo project and return its bin dir."""
    from .emit.rust import emit

    root = repo_root()
    registry = Registry.load()
    backend = Backend.load("rust")
    runtime = (root / "runtime" / "rust" / "phonebook_rt").as_posix()

    project = workspace / "rust"
    (project / "src" / "bin").mkdir(parents=True, exist_ok=True)
    (project / "Cargo.toml").write_text(
        RUST_PROJECT_TOML.format(runtime=runtime), encoding="utf-8", newline="\n"
    )
    for case in cases():
        checked = check(parse_file(case), registry)
        (project / "src" / "bin" / f"{case.stem}.rs").write_text(
            emit(checked, backend), encoding="utf-8", newline="\n"
        )

    env = child_env()
    target_dir = env.get("CARGO_TARGET_DIR") or str(
        Path(tempfile.gettempdir()) / "phonebook-cargo-target"
    )
    env["CARGO_TARGET_DIR"] = target_dir
    result = subprocess.run(
        ["cargo", "build", "--quiet"],
        cwd=str(project),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cargo build failed\n{result.stdout}\n{result.stderr}")
    return Path(target_dir) / "debug"


def via_rust(case: Path, binaries: Path) -> str:
    executable = binaries / (case.stem + (".exe" if os.name == "nt" else ""))
    result = _run([str(executable)])
    if result.returncode != 0:
        raise RuntimeError(f"{case.name}: generated Rust failed\n{result.stderr}")
    return normalize(result.stdout)


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------


def run_suite(backend: str, verbose: bool = False, record: bool = False) -> int:
    found = cases()
    if not found:
        print("no conformance cases found", file=sys.stderr)
        return 1

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="phonebook-conf-") as tmp:
        workspace = Path(tmp)
        binaries = build_rust(workspace) if backend == "rust" else None

        for case in found:
            if backend == "interpreter":
                actual = via_interpreter(case)
            elif backend == "python":
                actual = via_python(case, workspace)
            else:
                assert binaries is not None
                actual = via_rust(case, binaries)

            target = expected_path(case)
            if record:
                target.write_text(actual, encoding="utf-8", newline="\n")
                print(f"recorded {target.name}")
                continue

            if not target.exists():
                failures.append(f"{case.name}: no .expected file")
                continue

            expected = normalize(target.read_text(encoding="utf-8"))
            if actual == expected:
                if verbose:
                    print(f"ok    {case.stem}")
            else:
                failures.append(case.name)
                print(f"FAIL  {case.stem}", file=sys.stderr)
                print(_diff(expected, actual), file=sys.stderr)

    if record:
        return 0
    if failures:
        print(f"\n{len(failures)} of {len(found)} cases failed on {backend}", file=sys.stderr)
        return 1
    print(f"ok  {len(found)} conformance cases pass on {backend}")
    return 0


def _diff(expected: str, actual: str) -> str:
    import difflib

    lines = difflib.unified_diff(
        expected.splitlines(),
        actual.splitlines(),
        fromfile="expected",
        tofile="actual",
        lineterm="",
    )
    return "\n".join(f"    {line}" for line in lines)
