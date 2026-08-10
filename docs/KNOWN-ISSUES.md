# Known issues

Things that are wrong and not yet fixed, written down so they are not
rediscovered. Each entry says what breaks, how to see it, why it has not bitten
yet, and what "fixed" would mean.

---

## KI-1 — A built wheel contains no data, so `dial` cannot do anything

**Status:** open
**Severity:** blocks publishing to PyPI. Does not affect a cloned checkout.
**Found:** 2026-08-10, while writing the agent-facing docs.

### What is wrong

`pyproject.toml` declares only two package roots:

```toml
[tool.setuptools.packages.find]
where = ["src", "runtime/python"]
```

That picks up the Python modules and nothing else. Every directory the toolchain
reads at run time is *data*, lives outside those roots, and is therefore absent
from a built distribution:

| Missing from the wheel | Needed by |
|---|---|
| `phonebook/areas/*.json`, `phonebook/schema/`, `phonebook/frozen.json` | everything — this is the registry |
| `backends/python/mappings.json`, `backends/rust/mappings.json` | the resolver, so the interpreter and both emitters |
| `docs/WRITING-PHONE.md` | `dial brief` |
| `runtime/rust/phonebook_rt/` | compiling anything `dial emit --target rust` produces |
| `tests/conformance/` | `dial conformance` |
| `examples/` | the quickstart in the README |

A wheel built today contains 26 `.py` files and no data at all.

### Reproducing it

```bash
python -m build --wheel --outdir /tmp/w
python -m venv /tmp/v && /tmp/v/bin/pip install /tmp/w/*.whl
cd /tmp && /tmp/v/bin/dial registry list
```

```
registry error: could not locate the phonebook/ directory
```

Exit code 3. It fails loudly on the first command that needs data, rather than
producing a wrong answer — `default_root()` in `src/phonebook/registry.py` walks
up from `__file__` looking for `phonebook/areas`, does not find it, and raises.
That is the one good thing about this bug.

### Why it has not bitten

The documented install path is clone-then-`pip install -e .`, where the editable
install leaves the source tree in place and the upward walk finds everything.
CI, the demo harness, and the test suite all run from a checkout. Nothing has
ever consumed a real wheel.

### What fixing it involves

More than adding `package-data`, because two decisions come first.

**1. Where does the registry live?** The obvious move — ship the registry as
package data inside `src/phonebook/` — collides with the fact that the
repository already has a top-level `phonebook/` directory holding exactly that
data. Two different things would be called `phonebook`. Either the data moves
under the Python package and the top-level directory goes away, or the package
gets renamed, or the data ships as a separate distribution. This is a layout
decision, not a packaging tweak, and it should be made deliberately.

**2. Does the Rust runtime belong in a Python wheel?** `dial emit --target rust`
produces source that depends on the `phonebook_rt` crate. Shipping a crate
inside a Python package is possible but odd; publishing it to crates.io and
having the emitter reference it by version is the conventional answer, and it
would also make generated Rust usable outside a checkout.

**3. Path discovery has to stop walking the filesystem.** `default_root()` and
`default_backends_root()` in `registry.py` and `resolver.py` climb parent
directories. Installed data should be found with `importlib.resources` instead,
with the upward walk kept only as a development fallback.

### Acceptance

A wheel built from a clean checkout, installed into an empty virtualenv, run
from a directory that is not the repository:

```bash
dial registry list          # 54 addresses
dial show FILTER            # the entry, with both backends
dial brief                  # the writing guide
dial check some.phone       # contracts validate
dial run some.phone         # it executes
```

A test should build and install the wheel and assert those, or the bug will come
back the first time a data directory is added.

### Workaround until then

Clone the repository and `pip install -e .`. That is what the README says and it
works.
