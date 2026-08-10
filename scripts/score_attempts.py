"""Score a directory of model-written solutions against the task expectations.

    python scripts/score_attempts.py attempts/model-name/

The directory should contain one file per task, named for the task id — `t01.phone`
or `t01.py`, `t07.phone`, and so on. Anything else is ignored.

Each attempt is scored on three things, in order, because they fail differently
and the difference is the interesting part of the study:

    parses    the file is syntactically valid at all
    checks    it satisfies the contracts (.phone only — this stage has no
              equivalent in the control language, which is itself a finding)
    correct   running it produces exactly the expected stdout

A `.phone` attempt that fails `checks` never runs, so a model working in the
address space gets told precisely what is wrong before execution. That asymmetry
is the hypothesis under test, not a flaw in the scoring.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = ROOT / "experiments" / "expected"

sys.path[:0] = [str(ROOT / "src"), str(ROOT / "runtime" / "python")]

GREEN = "\033[32m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
YELLOW = "\033[33m" if sys.stdout.isatty() else ""
DIM = "\033[2m" if sys.stdout.isatty() else ""
OFF = "\033[0m" if sys.stdout.isatty() else ""

TASK_ID = re.compile(r"^(t\d{2})")


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT / "runtime" / "python"), env.get("PYTHONPATH", "")]
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(),
        timeout=timeout,
    )


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def first_diagnosis(stderr: str) -> str:
    """Pull the message out of `error: <path>:<line>: <message>`.

    The failure category is the whole point of the study, so the note column
    has to carry the diagnosis rather than a file path.
    """
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    if not lines:
        return "?"
    head = lines[0].removeprefix("error: ")
    stripped = re.sub(r"^.*?\.phone:\d+:\s*", "", head)
    return stripped or head


def expected_for(task: str) -> str | None:
    path = EXPECTED / f"{task}.out"
    return normalize(path.read_text(encoding="utf-8")) if path.exists() else None


def score_one(path: Path, task: str) -> dict:
    result = {
        "task": task,
        "file": path.name,
        "language": "phone" if path.suffix == ".phone" else "python",
        "parses": False,
        "checks": None,
        "correct": False,
        "error": "",
    }

    if path.suffix == ".phone":
        checked = run([sys.executable, "-m", "phonebook.cli", "check", str(path)])
        result["parses"] = "cannot read" not in checked.stderr and "malformed" not in checked.stderr
        result["checks"] = checked.returncode == 0
        if not result["checks"]:
            result["error"] = first_diagnosis(checked.stderr)
            result["stderr"] = checked.stderr.strip()
            return result
        result["parses"] = True
        executed = run([sys.executable, "-m", "phonebook.cli", "run", str(path)])
    else:
        compiled = run([sys.executable, "-c", f"compile(open(r'{path}').read(), 'x', 'exec')"])
        result["parses"] = compiled.returncode == 0
        if not result["parses"]:
            result["error"] = "SyntaxError"
            return result
        executed = run([sys.executable, str(path)])

    if executed.returncode != 0:
        result["error"] = (executed.stderr.strip().splitlines() or ["?"])[-1]
        return result

    wanted = expected_for(task)
    if wanted is None:
        result["error"] = "no expected output on file"
        return result
    result["correct"] = normalize(executed.stdout) == wanted
    if not result["correct"]:
        result["error"] = "output differs"
        result["got"] = normalize(executed.stdout)
        result["want"] = wanted
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", help="a directory of attempts, one file per task")
    parser.add_argument("--json", help="also write the raw results here")
    parser.add_argument("-v", "--verbose", action="store_true", help="show output diffs")
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"not a directory: {directory}", file=sys.stderr)
        return 2

    attempts: list[tuple[str, Path]] = []
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".phone", ".py"):
            continue
        match = TASK_ID.match(path.stem)
        if match:
            attempts.append((match.group(1), path))

    if not attempts:
        print(f"no t##.phone or t##.py files in {directory}", file=sys.stderr)
        return 2

    results = [score_one(path, task) for task, path in attempts]

    print()
    header = f"{'task':<6} {'parses':>7} {'checks':>7} {'correct':>8}   note"
    print(header)
    print("-" * max(len(header), 60))
    for r in results:
        checks = "n/a" if r["checks"] is None else ("ok" if r["checks"] else "no")
        cells = [
            f"{GREEN}{'ok':>7}{OFF}" if r["parses"] else f"{RED}{'no':>7}{OFF}",
            f"{GREEN}{checks:>7}{OFF}" if r["checks"] else f"{YELLOW}{checks:>7}{OFF}",
            f"{GREEN}{'ok':>8}{OFF}" if r["correct"] else f"{RED}{'no':>8}{OFF}",
        ]
        print(f"{r['task']:<6} {' '.join(cells)}   {DIM}{r['error'][:44]}{OFF}")
        if args.verbose and "got" in r:
            print(f"       want: {r['want']!r}")
            print(f"       got:  {r['got']!r}")

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    checked = sum(1 for r in results if r["checks"])
    phone = [r for r in results if r["language"] == "phone"]

    print()
    print(f"attempted   {total}")
    if phone:
        print(f"contracts   {checked}/{len(phone)} passed `dial check`")
    print(f"correct     {correct}/{total}  ({100 * correct // total}%)")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
