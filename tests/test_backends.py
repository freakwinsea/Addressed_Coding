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

EXAMPLES = ["line_count", "word_freq", "records", "audit_demo", "big_numbers", "money"]


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
        ("float", "f64"),
        ("list<float>", "Vec<f64>"),
        ("bigint", "rt::BigInt"),
        ("map<bigint,int>", "BTreeMap<rt::BigInt, i64>"),
        ("decimal", "rt::Decimal"),
        ("list<decimal>", "Vec<rt::Decimal>"),
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


# Each program should fault with the given code. The conformance suite compares
# stdout, so it cannot see a fault; this is where Rust's error paths are held to
# the contract. The Python runtime's are covered by the registry's own cases.
RUST_FAULTS = {
    # The smallest int64 has no literal of its own; SUB reaches it.
    "abs_min": ("400-0000002@[-9223372036854775807, 1] -> a\n"
                "400-0000010@[a] -> b\n100-0000001@[b]\n", "overflow"),
    "negate_min": ("400-0000002@[-9223372036854775807, 1] -> a\n"
                   "400-0000011@[a] -> b\n100-0000001@[b]\n", "overflow"),
    "pow_overflow": ("400-0000012@[2, 63] -> a\n100-0000001@[a]\n", "overflow"),
    "pow_huge_exponent": (
        "400-0000012@[10, 9223372036854775807] -> a\n100-0000001@[a]\n",
        "overflow",
    ),
    "pow_negative_exponent": ("400-0000012@[2, -1] -> a\n100-0000001@[a]\n", "negative_exponent"),
    "clamp_reversed": ("400-0000013@[5, 10, 0] -> a\n100-0000001@[a]\n", "invalid_range"),
    # 9 * 10^3999 has 4000 digits and is allowed; adding 10^3999 makes 4001.
    "add_big_ceiling": ("400-0000030@[10n, 3999] -> a\n400-0000027@[a, 9n] -> b\n"
                        "400-0000025@[a, b] -> c\n100-0000001@[c]\n", "overflow"),
    "mul_big_ceiling": ("400-0000030@[10n, 2000] -> a\n"
                        "400-0000027@[a, a] -> b\n100-0000001@[b]\n", "overflow"),
    "pow_big_ceiling": ("400-0000030@[10n, 4000] -> a\n100-0000001@[a]\n", "overflow"),
    "pow_big_huge_exponent": (
        "400-0000030@[2n, 9223372036854775807] -> a\n100-0000001@[a]\n",
        "overflow",
    ),
    "pow_big_negative_exponent": ("400-0000030@[2n, -1] -> a\n100-0000001@[a]\n",
                                  "negative_exponent"),
    "div_big_by_zero": ("400-0000028@[1n, 0n] -> a\n100-0000001@[a]\n", "division_by_zero"),
    "mod_big_by_zero": ("400-0000029@[1n, 0n] -> a\n100-0000001@[a]\n", "division_by_zero"),
    "big_to_int_overflow": ("400-0000024@[9223372036854775808n] -> a\n100-0000001@[a]\n",
                            "overflow"),
    "gcd_min_zero": ("400-0000002@[-9223372036854775807, 1] -> a\n"
                     "400-0000032@[a, 0] -> b\n100-0000001@[b]\n", "overflow"),
    "lcm_overflow": ("400-0000033@[9223372036854775807, 2] -> a\n100-0000001@[a]\n", "overflow"),
    "product_overflow_before_zero": (
        "300-0000001@[9223372036854775807, 2, 0] -> xs\n400-0000034@[xs] -> a\n100-0000001@[a]\n",
        "overflow",
    ),
    "dec_to_int_overflow": ("400-0000042@[-9223372036854775809.5d] -> a\n100-0000001@[a]\n",
                            "overflow"),
    "div_dec_by_zero": ("400-0000046@[1d, 0.00d, 2] -> a\n100-0000001@[a]\n",
                        "division_by_zero"),
    "div_dec_negative_places": ("400-0000046@[1d, 3d, -1] -> a\n100-0000001@[a]\n",
                                "invalid_places"),
    "round_dec_too_many_places": ("400-0000047@[1d, 1001] -> a\n100-0000001@[a]\n",
                                  "invalid_places"),
    # 0.1 has one place; a thousand-place value times it has 1001.
    "mul_dec_places_ceiling": ("400-0000047@[1d, 1000] -> a\n"
                               "400-0000045@[a, 0.1d] -> b\n100-0000001@[b]\n", "overflow"),
    # 10^3999 has 4000 digits; with one place, its coefficient has 4001.
    "round_dec_digits_ceiling": ("400-0000030@[10n, 3999] -> a\n400-0000041@[a] -> b\n"
                                 "400-0000047@[b, 1] -> c\n100-0000001@[c]\n", "overflow"),
    "add_dec_digits_ceiling": ("400-0000030@[10n, 3999] -> a\n400-0000041@[a] -> b\n"
                               "400-0000045@[b, 9d] -> c\n400-0000043@[b, c] -> d\n"
                               "100-0000001@[d]\n", "overflow"),
    "dec_to_float_overflow": ("400-0000030@[10n, 400] -> a\n400-0000041@[a] -> b\n"
                              "400-0000049@[b] -> c\n100-0000001@[c]\n", "overflow"),
}


def test_rust_faults_carry_the_contracted_code(has_cargo, registry, rust_backend, tmp_path):
    if not has_cargo:
        pytest.skip("cargo is not installed")
    import os

    from phonebook.conformance import RUST_PROJECT_TOML, child_env, repo_root

    runtime = (repo_root() / "runtime" / "rust" / "phonebook_rt").as_posix()
    project = tmp_path / "rust"
    (project / "src" / "bin").mkdir(parents=True)
    (project / "Cargo.toml").write_text(RUST_PROJECT_TOML.format(runtime=runtime), encoding="utf-8")
    for name, (body, _) in RUST_FAULTS.items():
        source = tmp_path / f"{name}.phone"
        source.write_text("phonebook 0.1\n\n" + body, encoding="utf-8")
        emitted = emit_rust(check(parse_file(source), registry), rust_backend)
        (project / "src" / "bin" / f"{name}.rs").write_text(emitted, encoding="utf-8")

    env = child_env()
    env.setdefault("CARGO_TARGET_DIR", str(tmp_path / "target"))
    built = subprocess.run(
        ["cargo", "build", "--quiet"], cwd=str(project), capture_output=True, text=True, env=env
    )
    assert built.returncode == 0, built.stderr

    for name, (_, code) in RUST_FAULTS.items():
        suffix = ".exe" if os.name == "nt" else ""
        executable = os.path.join(env["CARGO_TARGET_DIR"], "debug", name + suffix)
        result = subprocess.run([executable], capture_output=True, text=True)
        assert result.returncode == 1, (name, result.stdout, result.stderr)
        assert result.stdout == "", name
        assert result.stderr.startswith(f"fault: {code}"), (name, result.stderr)
