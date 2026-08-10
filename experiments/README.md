# The agent-authoring study

Both ideation sessions behind this project claimed that a closed, enumerable
address space is a better generation target for a language model than recalled
syntax: no hallucinated APIs, cheaper context, mechanically verifiable output.
Neither session tested it. This directory is the test.

## The question

> Given a compact specification in context, does a model produce a correct
> program more often in `.phone` than in a language it already knows?

That framing matters. A model has read millions of lines of Python and zero
lines of `.phone`, so the address space starts at an enormous disadvantage —
everything it knows has to come from the ~6k tokens of `dial brief`. If it wins
anyway, the reason is structural: a closed vocabulary it can look up beats an
open one it has to remember.

If it loses, that is worth knowing too, and it is cheap to find out.

## Method

**Arms.** Same 20 tasks, twice.

- **Treatment:** `.phone`, with `docs/WRITING-PHONE.md` in context.
- **Control:** Python, with no extra context — the model already knows it.

Python is the fair control rather than Rust. Rust would confound the result with
crate availability: `READ_CSV` is a registered address here, and in Rust it is a
dependency decision. Python's standard library has `csv`, so both arms have the
primitive and the comparison is about generation, not packaging.

**Measure three things, separately.** They fail differently, and the difference
is the finding:

| Stage | Meaning |
|---|---|
| `parses` | syntactically valid at all |
| `checks` | satisfies the contracts — `.phone` only |
| `correct` | run output matches exactly |

The `checks` column has no Python equivalent, and that asymmetry is the
hypothesis, not a scoring flaw. A `.phone` program that fails `dial check` never
runs, and the error names the fix. Note how often that happens: it is the
difference between a wrong answer and a *caught* wrong answer.

**Two protocols, and they measure different things.** Decide which one you are
running before you start, because the numbers are not comparable.

| | Model sees | Measures |
|---|---|---|
| **One-shot** | the guide and the tasks, as text. No repository, no tools. | first-attempt generation. `checks` failures are real failures. |
| **Agentic** | a checkout, so it can run `dial check`, `dial search`, `dial run` | whether the contract layer is a usable feedback loop. `checks` ends near 100% by construction; what matters is how many iterations it took and what it got wrong first. |

The agentic protocol is the more realistic setting and the more flattering one.
Do not report its `checks` column as if it were the one-shot number.

**No retries in the one-shot arm.** First-attempt validity is the number worth
having; retries measure the loop, not the language.

## Do not hand over the answer key

A full clone contains solutions to every task in `reference/` and their exact
outputs in `expected/`. Strip them from the model's checkout first:

```bash
python scripts/prepare_study_clone.py /path/to/the/models/clone
python scripts/prepare_study_clone.py /path/to/the/models/clone --check   # verify
```

Run it against the *model's* clone, never your own — scoring needs the key. The
script refuses to run against this checkout for that reason.

`examples/`, `generated/`, and `tests/conformance/` are left in place. A real
user of the language would have them, and a model that learns the idiom from
`examples/word_freq.phone` is doing something legitimate. Worth remembering when
reading results for t14, which is the task closest to a shipped example.

## Running it

```bash
# hand the model docs/WRITING-PHONE.md + experiments/TASKS.md,
# save its answers as t01.phone … t20.phone in one directory, then:
python scripts/score_attempts.py attempts/whichever-model/
python scripts/score_attempts.py attempts/whichever-model/ --json results.json -v
```

The scorer accepts `.phone` and `.py` in the same directory, so both arms can go
side by side.

Programs run from the repository root. `experiments/out/` exists because
`WRITE_TEXT_FILE` does not create directories, by contract.

## What is in here

```
TASKS.md      the 20 prompts — this is what the model gets
data/         the inputs
expected/     t01.out … t20.out, the exact stdout each task must produce
reference/    my solutions to all 20, verified
out/          scratch for tasks that write files
```

**`reference/` and `expected/` are the answer key. Do not put them in the
model's context.** Every reference solution passes `dial check` and produces its
`expected/` file, and `tests/test_experiments.py` keeps that true — so a task
that turns out to be unsolvable fails the build rather than quietly polluting
the data.

## What to watch for

The tasks were chosen to stress specific things, so a failure tells you where
the design leaks rather than just that it did:

| Tasks | Stresses |
|---|---|
| t01–t05 | can it find addresses at all, and does it bind every result |
| t06, t07, t11, t12 | does it reach for a local `ext` instead of a lambda |
| t08–t10 | `MAP` over an address that needs a second argument; truncating division |
| t13, t17 | no `MAX` primitive — sort and take the first |
| t14 | `map` → `ENTRIES` → `pair` → `PAIR_KEY`, and knowing `ENTRIES` is already sorted |
| t15 | `LIST` + `JOIN` instead of string concatenation |
| t18 | `REDUCE` with a **two-parameter** extension — the likeliest failure in the set |
| t19, t20 | effectful addresses, and `WRITE_CSV`'s explicit column list |

My priors, recorded before seeing any data so they can be wrong in public:
tier 1 near-perfect in both arms; the control ahead on t08–t10 where Python is
one-liner territory; `.phone` ahead on t12–t16 where the address table removes
the API-recall problem; and t18 the hardest in both. The most interesting
possible result is a high `checks`-failure rate with a low `correct`-failure
rate — that would mean the contract layer is catching errors the model would
otherwise have shipped, which is the actual claim worth making.
