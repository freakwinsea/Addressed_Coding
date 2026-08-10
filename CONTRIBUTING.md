# Contributing

The interesting rules here are about the registry, not the code. Adding an
address is meant to feel expensive, because an address is permanent.

## The rule

> **An issued address may never silently acquire a different meaning.**

`phonebook/frozen.json` holds a SHA-256 over every issued contract — the
address, its name, and the full contract including the semantic notes. CI
recomputes them. If one changes, the build fails.

That covers more than signatures. `ENTRIES` promising to sort by key is a note,
not a type, and it is hashed with everything else. Changing a note *is* changing
the contract.

## Changing an existing address

| What you are doing | What to do |
|---|---|
| Faster, safer, a different library — identical observable behavior | add an **implementation** to `backends/<target>/mappings.json`, bump `impl` |
| Different inputs, output, effects, errors, or semantics | bump `contract.version` and `dial registry freeze` |
| Different behavior altogether | **issue a new address** and mark the old one `deprecated` with `superseded_by` |

There is no fourth option. `dial registry freeze` refuses to rewrite an existing
hash, and says so.

If you find yourself wanting to "just fix" a contract, that is the system
working. The fix is a version bump.

## Adding a new address

1. **Argue that it belongs.** v0 is 54 addresses across six areas. Anything that
   can be built out of existing addresses should be — that is what `000` local
   extensions are for. New global addresses are for capabilities that genuinely
   cannot be expressed.

2. **Pick the area.** `100` core, `200` text, `300` collections, `400` numbers,
   `500` I/O, `600` logic. `700`/`800`/`900` are reserved; `999` is quarantine;
   `000` is local-only and can never be registered. Take the next free line
   number in the area — never reuse one.

3. **Write the contract before the code.** In `phonebook/areas/<area>.json`:
   inputs, output, effects, errors, purity, determinism, and — the part that
   matters — `notes` pinning any behavior where two languages could plausibly
   differ. If you are not sure whether a note is needed, write it. Look at
   `400-0000004 DIV` for what a real one looks like.

4. **Add conformance cases.** Value-level cases go in the entry itself and run
   against the Python runtime. Anything involving a callable, a file, or an
   ordering promise gets a program in `tests/conformance/` with a committed
   `.expected` file, which runs through all three execution paths.

5. **Implement it in both backends.** `runtime/python/phonebook_rt/` and
   `runtime/rust/phonebook_rt/`, then map it in both `backends/*/mappings.json`.
   `dial registry lint` fails if either target is missing an address.

6. **Freeze and verify.**

   ```bash
   dial registry lint
   dial registry freeze
   pytest
   python scripts/demo.py
   ```

## Inline templates

A mapping may carry an `inline` template used when generating source instead of
a runtime call. Only add one when it is **exactly** equivalent to the runtime
function.

`400-0000001 ADD` has no inline `+` in either backend: Python's would not
overflow when the contract says it must, and Rust's would panic or wrap
depending on build profile. Readability is never worth a semantic difference,
and `inline` is the easiest place in this repo to introduce one by accident.

## Before the first release

The ledger was re-issued once during development, when a contract note changed
before `0.1.0` shipped. That is legitimate only while nothing has been published
and nobody's program depends on an address. After a release, the ledger is
append-only and the version bump is the only move. Do not delete
`frozen.json` to make a failure go away.

## Code

```bash
pip install -e ".[dev]"
pytest                          # 180+ tests
python scripts/demo.py          # the cross-backend proof
dial registry lint              # schema, backend coverage, and the ledger
```

Match the surrounding style. The Python runtime and the Rust runtime are
deliberately written as counterparts — same function order, same doc comment
naming the address, same explicit algorithms where a library would have hidden a
difference (see the CSV state machine in both). Keep them readable side by side;
that symmetry is how divergence gets noticed.
