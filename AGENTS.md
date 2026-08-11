# AGENTS.md

Orientation for a coding agent working on this repository.

**Writing a `.phone` program is a different job** — read
[docs/WRITING-PHONE.md](docs/WRITING-PHONE.md) instead, or run `dial brief`.
This file is about changing the toolchain, the registry, and the runtimes.

---

## What this is

Phonebook is a semantic intermediate representation. Operations have permanent
numeric addresses (`300-0000002` is `FILTER`). A registry says what each address
*promises*; backend mapping tables say how each language *keeps* that promise. A
single `.phone` program can be interpreted, compiled to Python, or compiled to
Rust, and all three produce identical bytes.

That last sentence is the entire value proposition, and `scripts/demo.py` is the
test of it. If a change breaks it, the change is wrong.

**Resuming work?** [HANDOFF.md](HANDOFF.md) has the current state, what to pick
up next, and the mistakes that have already cost time. Read it first.

Open defects are recorded in [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md). Read
it before concluding you have found a new one.

## Setup

```bash
pip install -e ".[dev]"
```

The editable install from a clone is the **only** supported path today — a built
wheel contains no registry data and cannot run. See KI-1.

Without installing, put both packages on the path — the toolchain lives in
`src/` and the runtime in `runtime/python/`, which are separate roots:

```bash
PYTHONPATH="src:runtime/python" python -m phonebook.cli --help    # POSIX
$env:PYTHONPATH="src;runtime/python"                              # PowerShell
```

## The four commands that must pass

```bash
dial registry lint        # schema, backend coverage, and the immutability ledger
pytest -q                 # ~185 tests
python scripts/demo.py    # every example, three execution paths, identical bytes
dial conformance --backend rust
```

CI runs all four on Ubuntu and Windows. Run at least the first two before
claiming anything works.

## Invariants that will fail the build

**1. The immutability ledger.** `phonebook/frozen.json` holds a SHA-256 over
every issued contract — address, name, signature, effects, errors, *and the
semantic notes*. If you change any of those on an existing address, CI fails.

That is the system working, not a problem to route around. The fix is to bump
`contract.version` and run `dial registry freeze`. **Never delete
`frozen.json`, never hand-edit it, and never re-freeze to make a failure go
away.** See [CONTRIBUTING.md](CONTRIBUTING.md).

Editing a contract *note* counts. `ENTRIES` promising to sort by key is a note,
and it is load-bearing.

**2. Both backends implement every address.** Add an address and you owe an
implementation in `runtime/python/phonebook_rt/` *and*
`runtime/rust/phonebook_rt/`, plus an entry in both `backends/*/mappings.json`.
`dial registry lint` checks this.

**3. `inline` templates must be exactly equivalent to their runtime function.**
A mapping may carry an `inline` template used when generating source. It is a
readability feature and correctness must never depend on it. `ADD` deliberately
has no inline `+` in either backend: Python's would not overflow when the
contract says it must, and Rust's would panic or wrap by build profile. This is
the easiest place in the repo to introduce a silent semantic difference.

**4. `generated/` is committed and golden-tested.** `tests/test_backends.py`
asserts the emitted Rust matches what is checked in. After touching an emitter
or an example, regenerate with `python scripts/demo.py` and commit the diff —
the diff is the point, it is how emitter changes get reviewed.

**5. Conformance `.expected` files are committed.** `dial conformance --record`
overwrites them from a backend. Review that diff carefully; recording a wrong
answer makes the suite agree with a bug.

**6. The address table in the writing guide is generated.**
`docs/WRITING-PHONE.md` has a block between `BEGIN/END GENERATED ADDRESS TABLE`
markers. Refresh with `dial brief --write`; a test fails if it is stale.

## Layout

```
phonebook/areas/*.json    the registry — data, not code. 54 addresses.
phonebook/frozen.json     the immutability ledger. Machine-managed.
backends/*/mappings.json  address -> runtime function (+ optional inline template)
runtime/python/           one function per address
runtime/rust/             one function per address, written independently
src/phonebook/            parser, checker, resolver, interpreter, emitters, audit, cli
examples/                 .phone programs
generated/                committed emitter output — regenerate, do not hand-edit
tests/conformance/        .phone programs + committed .expected, run on all backends
experiments/              the agent-authoring study: tasks and their data
docs/                     SPEC, DESIGN-NOTES, AUDIT, WRITING-PHONE
```

## Design constraints you should not casually violate

**The v0 kernel is pure, immutable, and loop-free on purpose.** No mutation, no
loops, no aliasing. This is what lets one contract drive a garbage-collected
backend and a borrow-checked one without the contract mentioning memory. Adding
mutation is not a small change; it reopens the hardest problem in the design.
See [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) §1.

**There is one Python implementation, not two.** The interpreter and the
generated Python both call `phonebook_rt`, so they cannot drift. Rust is the
only independent implementation, which is what makes the conformance suite
evidence rather than theater. Do not give the interpreter its own copy of an
operation.

**Contracts pin behavior, not just types.** When Python and Rust would disagree,
the contract picks a winner and both bend to it: `DIV` truncates toward zero,
`MOD` takes the dividend's sign, `TO_TEXT` renders `true`/`false`, `LENGTH`
counts scalar values. Adding an address means asking where the languages differ
and writing that down in `contract.notes`.

**The two runtimes are deliberate counterparts.** Same function order, same doc
comment naming the address, same explicit algorithm where a library would have
hidden a difference — see the CSV state machine written twice. Keep them
readable side by side; that symmetry is how divergence gets noticed.

## Gotchas

- **Windows + OneDrive + cargo.** Build artifacts under a synced folder are slow
  and occasionally lock. `scripts/demo.py` sends `CARGO_TARGET_DIR` to the temp
  directory; set it yourself if you invoke cargo directly.
- **Line endings.** `.gitattributes` normalizes to LF. The `.expected` files are
  byte-compared across platforms; the harnesses normalize CRLF before diffing.
- **The `_pb` prefix is reserved** for generated identifiers. The checker
  rejects bindings that use it.
- **Trace output goes to stderr**, never stdout. A trace that changed a
  program's output would make the cross-backend comparison meaningless.

## Common jobs

| Job | Start at |
|---|---|
| Add an address | [CONTRIBUTING.md](CONTRIBUTING.md) — the process is deliberately heavy |
| Change how a language keeps a promise | `backends/<target>/mappings.json`, bump `impl` |
| Fix a checker or parser bug | `src/phonebook/{checker,parser}.py`, add a case to `tests/test_frontend.py` |
| Change generated code | `src/phonebook/emit/`, then `python scripts/demo.py` and commit `generated/` |
| Understand why something is the way it is | [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) |
| Pick up a known defect | [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md) |
