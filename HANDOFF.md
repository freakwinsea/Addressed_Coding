# Handoff

Working state and what to pick up next. Project documentation lives elsewhere —
[README.md](README.md) is the pitch, [AGENTS.md](AGENTS.md) orients an agent
working on the repo, [docs/SPEC.md](docs/SPEC.md) is the language. This file is
just "where we got to."

**Last updated:** 2026-08-11, at commit `f23dff2`.

---

## Where this is

Phonebook works end to end and is published at
`github.com/freakwinsea/Addressed_Coding`. Two studies have been run. The
authoring study returned a null result; the mutation study returned the finding
the README now leads with.

| | State |
|---|---|
| Language, toolchain, both runtimes | done, 225 tests passing |
| Dual-backend proof | `python scripts/demo.py` — 4 examples, 3 paths, identical bytes |
| Authoring study | **finished — null result.** 3 models, 60 programs, 60 correct, no difference between arms |
| Mutation study | **finished — 95% vs 31%** on shared operator classes |
| Published | yes, MIT, CI configured |
| Known defects | one: [KI-1](docs/KNOWN-ISSUES.md), a built wheel contains no registry data |

Everything must pass before any change is called done:

```bash
dial registry lint        # schema, backend coverage, immutability ledger
pytest -q                 # 225
python scripts/demo.py    # the cross-backend proof
dial conformance --backend rust
```

## What to pick up next

**1. Share the mutation result.** This is the highest-value move and nothing
blocks it. The finding is narrow, evidenced, reproducible in one command, and
strengthened rather than weakened by the null result sitting next to it.

Before posting anywhere, do the prior-art reading:

- **Unison** — the closest relative and the first comment you will get.
  Content-addressed code, definitions identified by hash. The distinction is
  real and worth having ready: Unison hashes the *implementation*, so a
  different implementation is a different identity; a Phonebook address is
  issued for the *contract*, and many implementations across many languages can
  satisfy it.
- **CORBA / COM interface GUIDs** — stable versioned contract identifiers, and
  instructive failure modes.
- **WebAssembly and LLVM IR** — why they do not cover this ground: both are
  machine-facing by design.

r/ProgrammingLanguages before Hacker News. That crowd will red-team properly,
and it is better to absorb the obvious objections at a few hundred views than a
few thousand.

**2. KI-1, if sharing draws people who try to `pip install`.** Not a packaging
tweak — the registry lives in a top-level `phonebook/` directory that collides
with the Python package name, so it is a layout decision first. Full write-up
with an acceptance test in [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md).

**3. More measurement, only if there is a question worth asking.** The 20-task
set is finished as an instrument — three models all scored 20/20. Extending it
means a genuinely harder tier: joins across two data sources, grouping and
aggregating in one pass, anything where the pure loop-free kernel starts to
bite. The mutation study is the one with headroom.

**4. Editor extension.** The DNS objection is answered by the CLI today
(`dial show`, `search`, `next`, `annotate`, `--trace`) but an editor would
answer it properly. Real value, moderate cost, no urgency.

**Not next: widening the kernel.** Mutation and loops are where the memory
chasm returns at full strength, and it would put the one clean story at risk.
[docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) §1.

## Working state on this machine

- The repo is installed **editable** from the checkout. `dial` anywhere resolves
  to this working copy.
- Study clones live outside the repo, in a sibling `phonebook-study/` directory,
  each with its own `.venv`. They are disposable — every program they produced
  is archived under `experiments/runs/`.
- `scripts/demo.py` sends `CARGO_TARGET_DIR` to the system temp directory,
  because cargo under OneDrive is slow and occasionally locks files.

## Things that have already bitten us

Recorded so they are not rediscovered. Each cost real time.

**`pip install -e .` inside a study clone hijacks the global install.** It
happened twice, silently repointing `dial` at a scrubbed clone. Study clones get
their own venv, and `experiments/TASKS.md` says so. If `dial` behaves strangely,
check `pip show phonebook-lang | grep Editable` first.

**Five separate leaks of experimenter-facing material into study clones**, each
found by a different method and none by the check written after the previous
one: the guide's worked patterns; the task sheet's note naming the answer key;
`experiments/README.md`'s per-task method table; the archived run 1 solutions;
and a stray UTF-16 `brief.md`. `prepare_study_clone.py --check` covers all five
now. Treat it as necessary, not sufficient.

**UTF-16 files are invisible to ASCII leak scans.** PowerShell's `>` redirect
writes UTF-16, so `grep pattern` and `grep -I pattern` both find nothing — the
`-I` flag was never the issue. A test now refuses to hold a non-UTF-8 tracked
file, and the clone check flags one by name.

**A `--check` predicate drifted from the thing it checked** and passed a clone
it should have rejected. Both now share one constant.

**Prose pinned in tests breaks on rewording.** A guard asserting an exact
sentence in `TASKS.md` failed when the sentence was legitimately improved.
Assert the substance.

## Do not

- **Delete `phonebook/frozen.json`, or re-freeze to silence a failure.** The
  complaint is the feature. A changed contract means bumping
  `contract.version`. The ledger was legitimately re-issued exactly once, before
  0.1.0 shipped, and that window is closed.
- **Hand-edit `generated/`.** Regenerate with `scripts/demo.py` and commit the
  diff; the diff is how emitter changes get reviewed.
- **Add an `inline` mapping template that is not exactly equivalent to its
  runtime function.** Easiest place in the repo to introduce a silent semantic
  difference. `ADD` has no inline `+` on purpose.
- **Quote 97% / 27% for the mutation study.** Use 95% / 31%, the shared-operator
  subtotal. The higher figure includes a class only one arm can express and is
  footnoted as such in both the README and
  [experiments/MUTATION.md](experiments/MUTATION.md).

## Open questions worth an opinion

- Is the mutation result strong enough to write up as a short post on its own,
  or does it want a second target language to generalize past "Python
  specifically"?
- Does the audit model deserve its own study? It is the other differentiated
  claim and nothing has measured it.
- Is self-hosting worth attempting at all, or is it better as a documented north
  star that keeps the design honest without consuming months?
