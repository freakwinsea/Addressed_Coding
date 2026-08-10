"""Strip the answer key out of a clone before handing it to a model under study.

A full checkout contains worked solutions to all twenty tasks in
`experiments/reference/` and their exact outputs in `experiments/expected/`. A
model with the repository can simply read them, and any result collected that
way measures nothing.

Deleting the files is not enough. Git history still has them, and
`git show HEAD:experiments/reference/t01_line_count.phone` brings the whole key
back — so `.git` goes too, unless you pass `--keep-git` and accept that.

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
#:
#: `runs/` is the one that is easy to forget: archiving a completed run commits
#: twenty working solutions to this exact task set, so every later clone ships
#: with a fuller answer key than `reference/` is. Archive runs, but never let a
#: model see them.
SECRET = [
    "experiments/reference",
    "experiments/expected",
    "experiments/runs",
]

#: Not secret, but it tests the answer key, so it fails once the key is gone.
#: A clone where `pytest` fails out of the box would send a model off repairing
#: a repository that is not broken.
DEPENDS_ON_KEY = [
    "tests/test_experiments.py",
]

#: The scorer needs the answer key, so in a scrubbed clone it can only fail.
#: Leaving it there tells a model that scoring is part of its job and that a
#: key exists somewhere it cannot reach — which is pressure to go looking.
#: Scoring is the experimenter's job and happens in the source repository.
NOT_THE_MODELS_JOB = [
    "scripts/score_attempts.py",
    "scripts/prepare_study_clone.py",
]

#: Anything a previous run left behind. A clone that already contains twenty
#: finished solutions will not get twenty new ones written — the work looks
#: done, so the model verifies instead of authoring, and the run is wasted.
PRIOR_RUN_ARTEFACTS = [
    "attempts",
    "experiments/out/errors.txt",
    "experiments/out/restock.csv",
    ".pytest_cache",
    "phonebook_lang.egg-info",
]

#: Present in a real user's checkout, so they stay. Worth knowing they are
#: there: a model may legitimately learn the idiom from them, which is part of
#: the honest setup rather than a leak.
FAIR_GAME = [
    "examples",
    "tests/conformance",
    "generated",
]


def _force_remove(func, path, _exc):
    """Git keeps pack files read-only, which Windows refuses to delete."""
    Path(path).chmod(0o700)
    func(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clone", help="path to the clone the model will work in")
    parser.add_argument("--check", action="store_true", help="report without deleting")
    parser.add_argument(
        "--keep-git",
        action="store_true",
        help="keep .git, leaving the answer key recoverable from history",
    )
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
    recoverable = (root / ".git").exists() and not args.keep_git
    stale = [name for name in PRIOR_RUN_ARTEFACTS if (root / name).exists()]
    scoring = [name for name in NOT_THE_MODELS_JOB if (root / name).exists()]

    if args.check:
        problems = found or recoverable or stale or scoring
        if problems:
            print("NOT READY:")
            for name in found:
                print(f"  {name}  — answers")
            if recoverable:
                print("  .git  — history still holds them: git show HEAD:<path>")
            for name in stale:
                print(f"  {name}  — left over from an earlier run")
            for name in scoring:
                print(f"  {name}  — scoring is not the model's job")
            return 1
        print("ready — no answer key, no earlier run, no scoring tools")
        return 0

    for name in found:
        shutil.rmtree(root / name)
        print(f"removed {name}  (answers)")
    for name in DEPENDS_ON_KEY:
        path = root / name
        if path.exists():
            path.unlink()
            print(f"removed {name}  (tests the answers)")
    for name in NOT_THE_MODELS_JOB:
        path = root / name
        if path.exists():
            path.unlink()
            print(f"removed {name}  (scoring is not the model's job)")
    for name in stale:
        path = root / name
        shutil.rmtree(path, onerror=_force_remove) if path.is_dir() else path.unlink()
        print(f"removed {name}  (left over from an earlier run)")
    if not found:
        print("no answer key present in the working tree")

    if (root / ".git").exists():
        if args.keep_git:
            print()
            print("WARNING: .git kept. The answer key is still recoverable with")
            print("         git show HEAD:experiments/reference/<file>")
        else:
            shutil.rmtree(root / ".git", onerror=_force_remove)
            print("removed .git  (history holds the answers too)")

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
