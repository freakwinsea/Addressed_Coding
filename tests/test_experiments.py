"""The study's task set has to stay honest.

If a reference solution stops checking, or stops producing its expected output,
the corresponding task has quietly become unanswerable and any data collected
against it is noise. That should fail the build, not the experiment.
"""

from __future__ import annotations

import re

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


def test_task_sheet_gives_no_answers_away(root):
    """The sheet the model reads must not contain any of the solution."""
    tasks = (root / "experiments" / "TASKS.md").read_text(encoding="utf-8")
    for number, line in enumerate(tasks.splitlines(), 1):
        assert "000-000" not in line, f"TASKS.md:{number} names a local extension"
        assert not re.search(r"\b[1-9]00-\d{7}\b", line), (
            f"TASKS.md:{number} names a registered address — the tasks describe "
            f"what to compute, never which address to dial"
        )


def test_task_sheet_warns_about_the_answer_key(root):
    """Whoever runs the study has to be told to strip reference/ and expected/."""
    tasks = (root / "experiments" / "TASKS.md").read_text(encoding="utf-8")
    assert "prepare_study_clone" in tasks
    assert "experiments/reference/" in tasks


def test_scrub_script_removes_everything_that_gives_answers(root):
    """Whatever the scrub script deletes must cover every directory with answers."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prepare_study_clone", root / "scripts" / "prepare_study_clone.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name in ("experiments/reference", "experiments/expected"):
        assert name in module.SECRET, f"{name} holds answers but is not scrubbed"


def test_writing_guide_covers_every_address(root, registry: Registry):
    """A model working only from the guide must be able to reach every address."""
    guide = guide_path(registry).read_text(encoding="utf-8")
    missing = [e.address for e in registry if e.address not in guide]
    assert missing == []


def test_writing_guide_table_is_current(registry: Registry):
    assert guide_is_current(registry), "run `dial brief --write`"
