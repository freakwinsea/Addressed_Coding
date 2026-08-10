"""Strip the answer key out of a clone before handing it to a model under study.

A full checkout contains worked solutions to all twenty tasks in
`experiments/reference/` and their exact outputs in `experiments/expected/`. A
model with the repository can simply read them, and any result collected that
way measures nothing.

Run this against the *model's* clone, never your own — scoring needs the key.

    python scripts/prepare_study_clone.py /path/to/agents/clone
    python scripts/prepare_study_clone.py /path/to/agents/clone --check

`--check` reports without deleting, so you can verify a clone is clean before
starting a run.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

#: Directories that give the answers away outright.
SECRET = [
    "experiments/reference",
    "experiments/expected",
]

#: Not secret, but it tests the answer key, so it fails once the key is gone.
#: A clone where `pytest` fails out of the box would send a model off repairing
#: a repository that is not broken.
DEPENDS_ON_KEY = [
    "tests/test_experiments.py",
]

#: Present in a real user's checkout, so they stay. Worth knowing they are
#: there: a model may legitimately learn the idiom from them, which is part of
#: the honest setup rather than a leak.
FAIR_GAME = [
    "examples",
    "tests/conformance",
    "generated",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clone", help="path to the clone the model will work in")
    parser.add_argument("--check", action="store_true", help="report without deleting")
    args = parser.parse_args()

    root = Path(args.clone).resolve()
    if not (root / "experiments").is_dir():
        print(f"{root} does not look like a Phonebook checkout", file=sys.stderr)
        return 2

    if root == Path(__file__).resolve().parent.parent:
        print(
            "refusing to run against this checkout — scoring needs the answer key.\n"
            "Point this at the model's clone instead.",
            file=sys.stderr,
        )
        return 2

    found = [name for name in SECRET if (root / name).exists()]

    if args.check:
        if found:
            print("NOT CLEAN — the model can read the answers:")
            for name in found:
                print(f"  {name}")
            return 1
        print("clean — no answer key present")
        return 0

    for name in found:
        shutil.rmtree(root / name)
        print(f"removed {name}  (answers)")
    for name in DEPENDS_ON_KEY:
        path = root / name
        if path.exists():
            path.unlink()
            print(f"removed {name}  (tests the answers)")
    if not found:
        print("no answer key present; the clone was already clean")

    print()
    print("left in place — a real user would have these too:")
    for name in FAIR_GAME:
        if (root / name).exists():
            print(f"  {name}")
    print()
    print("`pytest` should now pass in this clone. If it does not, that is a")
    print("real failure and not an artefact of the scrub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
