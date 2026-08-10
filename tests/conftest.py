"""Test fixtures. Puts the toolchain and the runtime on the path for a source checkout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "runtime" / "python")]

from phonebook.registry import Registry  # noqa: E402
from phonebook.resolver import Backend  # noqa: E402


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def registry() -> Registry:
    return Registry.load()


@pytest.fixture(scope="session")
def python_backend() -> Backend:
    return Backend.load("python")


@pytest.fixture(scope="session")
def rust_backend() -> Backend:
    return Backend.load("rust")


@pytest.fixture
def at_root(monkeypatch):
    """Programs name their data with repo-relative paths."""
    monkeypatch.chdir(ROOT)
    return ROOT


@pytest.fixture
def has_cargo() -> bool:
    import shutil

    return shutil.which("cargo") is not None
