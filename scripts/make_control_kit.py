"""Assemble the control arm's working directory.

The control arm is the same twenty tasks in Python, given to a model with no
extra context, because it already knows Python. Without it the treatment arm's
score has nothing to be compared against: 20/20 in `.phone` is only interesting
next to a number from a language the model did not have to be taught.

    python scripts/make_control_kit.py /path/to/kit

The task descriptions are **derived** from experiments/TASKS.md rather than
copied by hand. Two sheets maintained separately would drift, and a drifted
control arm is worse than none — it would look like a comparison while
measuring two different things.

Only the preamble differs, and only where it has to:

    treatment   here is a language you have never seen, in 5k tokens
    control     you already know this one

Both arms get the same data, the same working directory layout, and the ability
to run their own programs. The kit deliberately contains no reference to
Phonebook, addresses, or a second arm.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_SHEET = ROOT / "experiments" / "TASKS.md"
DATA = ROOT / "experiments" / "data"

PREAMBLE = """# The 20 tasks

## Before you start

Write one file per task, named `t01.py` through `t20.py`, in a single
directory. Programs are run from this directory, so keep the data paths exactly
as they are written below.

Use the Python standard library only — no third-party packages.

Every task:

- reads from `experiments/data/`, with paths written relative to the directory
  you are working in, which is where the program will be run from;
- prints a single deterministic result to standard output;
- should print exactly what is asked for and nothing else: no labels, no
  explanatory text.

Run a program with `python t01.py` to check it.

---
"""


def task_body(sheet: str) -> str:
    """Everything from the first tier heading onward, verbatim."""
    marker = "\n## Tier 1"
    index = sheet.find(marker)
    if index == -1:
        raise SystemExit("could not find the tiers in TASKS.md")
    return sheet[index:].lstrip("\n")


def build(kit: Path) -> None:
    sheet = SOURCE_SHEET.read_text(encoding="utf-8")
    body = task_body(sheet)

    if ".phone" in body:
        raise SystemExit(
            "the task bodies mention .phone — the two arms would not be comparable.\n"
            "Fix experiments/TASKS.md so the tasks describe the work only."
        )

    kit.mkdir(parents=True, exist_ok=True)
    (kit / "TASKS.md").write_text(PREAMBLE + "\n" + body, encoding="utf-8", newline="\n")

    destination = kit / "experiments" / "data"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(DATA, destination)
    (kit / "experiments" / "out").mkdir(parents=True, exist_ok=True)
    (kit / "experiments" / "out" / ".gitkeep").write_text(
        "# Two of the tasks write here.\n", encoding="utf-8", newline="\n"
    )

    count = body.count("**t")
    print(f"control kit at {kit.as_posix()}")
    print(f"  TASKS.md            {count} tasks, derived from experiments/TASKS.md")
    print(f"  experiments/data/   {len(list(destination.iterdir()))} files")
    print(f"  experiments/out/    empty")
    print()
    print("Hand over the directory. Score the result from the source repository:")
    print(f"  python scripts/score_attempts.py {(kit / 'answers').as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit", help="directory to build the control arm in")
    args = parser.parse_args()
    kit = Path(args.kit).resolve()
    if kit == ROOT:
        print("refusing to build the kit on top of the repository", file=sys.stderr)
        return 2
    build(kit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
