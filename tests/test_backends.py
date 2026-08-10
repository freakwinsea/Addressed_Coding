"""Code generation and the cross-backend agreement the project exists to test."""

from __future__ import annotations

import subprocess
import sys

import pytest
from phonebook.checker import check
from phonebook.conformance import cases, via_interpreter, via_python
from phonebook.emit.python import emit as emit_python
from phonebook.emit.rust import emit as emit_rust
from phonebook.emit.rust import rust_type
from phonebook.parser import parse_file
from phonebook.types import parse_type

EXAMPLES = ["line_count", "word_freq", "records", "audit_demo"]


def test_both_backends_cover_the_whole_registry(registry, python_backend, rust_backend):
    assert python_backend.audit_against(registry) == []
    assert rust_backend.audit_against(registry) == []


def test_python_runtime_symbols_all_resolve(registry, python_backend):
    from phonebook_rt import resolve

    for entry in registry:
        implementation = python_backend.resolve(entry.address, _latest())
        assert implementation.runtime is not None, entry.label
        assert callable(resolve(implementation.runtime))


def test_addresses_without_a_runtime_have_an_inline_template(registry, rust_backend):
    """A target may keep a contract entirely inline, but it must keep it somehow."""
    for entry in registry:
        implementation = rust_backend.resolve(entry.address, _latest())
        assert implementation.runtime or implementation.inline, entry.label


def _latest():
    from phonebook.nodes import LATEST

    return LATEST


@pytest.mark.parametrize(
    "phonebook_type,expected",
    [
        ("text", "String"),
        ("int", "i64"),
        ("list<text>", "Vec<String>"),
        ("map<text,int>", "BTreeMap<String, i64>"),
        ("pair<text,int>", "(String, i64)"),
        ("list<pair<text,int>>", "Vec<(String, i64)>"),
    ],
)
def test_rust_type_rendering(phonebook_type, expected):
    assert rust_type(parse_type(phonebook_type)) == expected


@pytest.mark.parametrize("name", EXAMPLES)
def test_generated_python_is_valid_and_stable(name, registry, python_backend, root, tmp_path):
    checked = check(parse_file(root / "examples" / f"{name}.phone"), registry)
    source = emit_python(checked, python_backend)
    compile(source, f"{name}.py", "exec")  # it must at least be Python
    assert emit_python(checked, python_backend) == source  # and deterministic


@pytest.mark.parametrize("name", EXAMPLES)
@pytest.mark.parametrize("emitter", ["python", "rust"])
def test_generated_source_names_its_origin_relative_to_the_repo(
    name, emitter, registry, python_backend, rust_backend, root
):
    """Generated files are committed and byte-compared, so no absolute paths.

    Regression guard: the emitters used to echo whatever path they were handed
    into the provenance banner. `scripts/demo.py` passes absolute paths, so the
    committed goldens embedded the generating machine's directory layout and the
    golden test could only pass on that one machine. The golden test cannot
    catch this by itself — it passes wherever the goldens were made.
    """
    emit = emit_python if emitter == "python" else emit_rust
    backend = python_backend if emitter == "python" else rust_backend
    source = emit(check(parse_file(root / "examples" / f"{name}.phone"), registry), backend)
    banner = source.splitlines()[0]

    assert f"examples/{name}.phone" in banner
    assert ":" not in banner.split("from")[-1], f"drive letter leaked into: {banner}"
    assert "\\" not in banner, f"backslash leaked into: {banner}"
    assert str(root) not in source, "the repository's own path must not appear"


@pytest.mark.parametrize("name", EXAMPLES)
def test_generated_rust_matches_the_committed_golden_file(name, registry, rust_backend, root):
    """Regenerating must not silently change what is committed under generated/."""
    checked = check(parse_file(root / "examples" / f"{name}.phone"), registry)
    golden = root / "generated" / "rust" / "src" / "bin" / f"{name}.rs"
    assert golden.exists(), "run `python scripts/demo.py` to regenerate"
    assert emit_rust(checked, rust_backend) == golden.read_text(encoding="utf-8")


@pytest.mark.parametrize("case", [c.stem for c in cases()])
def test_conformance_interpreter_and_python_agree(case, root, at_root, tmp_path):
    path = root / "tests" / "conformance" / f"{case}.phone"
    expected = (root / "tests" / "conformance" / f"{case}.expected").read_text("utf-8")
    expected = expected.replace("\r\n", "\n")
    assert via_interpreter(path) == expected
    assert via_python(path, tmp_path) == expected


def test_rust_conformance(has_cargo, root):
    """The one genuinely independent implementation in the project."""
    if not has_cargo:
        pytest.skip("cargo is not installed")
    result = subprocess.run(
        [sys.executable, "-m", "phonebook.cli", "conformance", "--backend", "rust"],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=_env(root),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _env(root):
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root / "runtime" / "python"), env.get("PYTHONPATH", "")]
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return env
