"""The study's task set has to stay honest.

If a reference solution stops checking, or stops producing its expected output,
the corresponding task has quietly become unanswerable and any data collected
against it is noise. That should fail the build, not the experiment.
"""

from __future__ import annotations

import pytest
from phonebook.brief import guide_is_current, guide_path
from phonebook.checker import check
from phonebook.conformance import via_interpreter
from phonebook.parser import parse_file
from phonebook.registry import Registry

TASK_COUNT = 20


def reference_solutions(root):
    return sorted((root / "experiments" / "reference").glob("*.phone"))


def test_every_task_has_a_reference_solution(root):
    assert len(reference_solutions(root)) == TASK_COUNT


def test_every_task_has_an_expected_output(root):
    expected = sorted((root / "experiments" / "expected").glob("t*.out"))
    assert len(expected) == TASK_COUNT


def test_tasks_file_describes_every_task(root):
    text = (root / "experiments" / "TASKS.md").read_text(encoding="utf-8")
    for n in range(1, TASK_COUNT + 1):
        assert f"**t{n:02d}.**" in text, f"t{n:02d} is missing from TASKS.md"


@pytest.mark.parametrize("index", range(TASK_COUNT))
def test_reference_solution_checks_and_matches(index, registry: Registry, root, at_root):
    """Each reference solution must satisfy the contracts and produce its key."""
    path = reference_solutions(root)[index]
    task = path.stem[:3]

    check(parse_file(path), registry)  # raises if the contracts are not met

    expected = (root / "experiments" / "expected" / f"{task}.out").read_text(encoding="utf-8")
    assert via_interpreter(path) == expected.replace("\r\n", "\n")


def test_reference_solutions_are_not_reachable_from_the_task_sheet(root):
    """The answer key must not leak into what the model is handed."""
    tasks = (root / "experiments" / "TASKS.md").read_text(encoding="utf-8")
    assert "Do not give it `experiments/reference/`" in tasks
    for line in tasks.splitlines():
        assert "000-000" not in line, "TASKS.md must not contain worked addresses"


def test_writing_guide_covers_every_address(root, registry: Registry):
    """A model working only from the guide must be able to reach every address."""
    guide = guide_path(registry).read_text(encoding="utf-8")
    missing = [e.address for e in registry if e.address not in guide]
    assert missing == []


def test_writing_guide_table_is_current(registry: Registry):
    assert guide_is_current(registry), "run `dial brief --write`"
