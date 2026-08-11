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

## Results so far

| Run | Setup | Contracts | Correct | Verdict |
|---|---|---|---|---|
| 1 | full guide, patterns visible | 20/20 | 20/20 | void — the guide solved the tasks |
| 2 | patterns withheld | — | — | void — no work produced, see run 1 notes |
| 3 | patterns withheld, task sheet cleaned | 20/20 | **20/20** | sound, with a caveat |
| 4 | as run 3, different model | 20/20 | **20/20** | sound |

**The instrument is at its ceiling.** Two sound runs at 100% means these twenty
tasks cannot discriminate between models, and cannot possibly discriminate
between languages — a competent model would very likely score 20/20 on the
Python control arm as well, and 20/20 against 20/20 measures nothing.

What run 4 did establish is worth having anyway: it shares **no file** with run
3, uses `REDUCE` four times where run 3 used it zero, and its `t09` is more
correct than the reference — it seeds the fold from the data instead of
hardcoding an initial value that would break on all-negative input. Two models,
forty programs, no overlap, forty correct results. The address space admits more
than one route and more than one model can find one.

Neither of those is the claim under test. Before another run of this set, the
study needs the control arm — which nobody has run — or a harder tier.

Run 3's real finding is not the 20. It planned every program before running
anything, and that plan scores **19/20**: one address typed with six digits
instead of seven. `dial check` named it, the model fixed it, and nothing else
changed across twenty files. The gap between 19 and 20 is one character, and it
is the only measurement here that is about the language rather than the harness.

Run 3 also beat the reference solutions twice — passing a registered address
straight to `MAP`, and sidestepping the two-parameter `REDUCE` that the task set
was built to stress. Details in `runs/run3-patterns-withheld/NOTES.md`,
including the caveat: a stray UTF-16 file in the clone told it that something
had been withheld for measurement, though not what.

## Run 1 was invalid. Read this before trusting a number.

The first run scored **20/20 correct, 20/20 contracts**, in one pass, without
iterating. It does not mean what it looks like.

`docs/WRITING-PHONE.md` §5 is eight worked patterns — *filter a list*, *fold a
total*, *rank a tally* — and the guide and the task set were written in the same
sitting. All eight map onto tasks. §5's filter example even uses the literal
`"ERROR"`, which is t06. The model was handed the method and applied it. That
measures recall of a supplied example, not use of the language.

**Use `dial brief --minimal` for any measured run.** It withholds §5 and keeps
everything else — syntax, rules, constraints, and the full address table. §5
stays in the guide for real users, where a worked example is exactly what you
want; it just cannot also be the measuring instrument.

Two things from run 1 do survive, because the confound does not reach them:

- **All 20 tasks are expressible, and a model can find its way around the
  address space.** Nothing was impossible or awkward enough to defeat it.
- **`checks` was 20/20 on files written before anything was run.** The patterns
  gave away the method, not the syntax, the arity, or the types.

## Method

**Arms.** Same 20 tasks, twice.

- **Treatment:** `.phone`, with `dial brief --minimal` in context.
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

## Keep the task sheet free of meta

`TASKS.md` is the one file from this directory the model reads, and it must
describe the work and nothing else. It previously carried a note explaining that
worked solutions live in `experiments/reference/`, that their outputs live in
`experiments/expected/`, and that both had been stripped from the model's clone.

That is almost certainly what sent run 2 outside its sandbox. The answer key was
hidden and the model was handed a note saying so — a puzzle with a stated
solution just out of reach, addressed to something whose job was to be correct.

Nothing in `TASKS.md` should mention a study, an experimenter, scoring, an
answer key, or what the model has or has not seen before. `tests/test_experiments.py`
enforces that against a vocabulary list, because this is the third time
experimenter-facing prose has leaked into subject-facing material and it will
not be the last time it is attempted.

Setup instructions belong here instead.

## Do not hand over the answer key

A full clone contains solutions to every task in `reference/` and their exact
outputs in `expected/`. Strip them from the model's checkout first:

```bash
python scripts/prepare_study_clone.py /path/to/the/models/clone
python scripts/prepare_study_clone.py /path/to/the/models/clone --check   # verify
```

Deleting the files is not sufficient on its own —
`git show HEAD:experiments/reference/t01_line_count.phone` brings the whole key
back — so the script removes `.git` as well. Update the clone to the commit you
want *before* scrubbing it, because afterwards you cannot pull.

Run it against the *model's* clone, never your own — scoring needs the key. The
script refuses to run against this checkout for that reason.

`examples/`, `generated/`, and `tests/conformance/` are left in place. A real
user of the language would have them, and a model that learns the idiom from
`examples/word_freq.phone` is doing something legitimate. Worth remembering when
reading results for t14, which is the task closest to a shipped example.

## A bias in the expected outputs, stated up front

The tasks encode two of Phonebook's contract decisions. t10 requires division
that truncates toward zero; t11 requires the words `true` and `false` in
lowercase. Both are stated explicitly in the task text, so neither arm is being
ambushed — but the treatment arm gets them from `DIV` and `TO_TEXT` for free,
while the control arm has to notice the requirement and implement it. Python's
`//` floors and `str(True)` is `"True"`.

That is a real asymmetry favouring the treatment arm, worth roughly two tasks.
It was discovered by hand-writing the control solutions for a smoke test, not
by reasoning about it in advance. If the arms come out close, subtract it before
concluding anything.

## Running the control arm

```bash
python scripts/make_control_kit.py /path/to/control-kit
```

That produces a standalone directory: the same twenty tasks with a Python
preamble, the same data, the same layout. The sheet is *derived* from
`TASKS.md` rather than written separately — two hand-maintained sheets would
drift, and a drifted control arm looks like a comparison while measuring two
different things. `tests/test_experiments.py` asserts they stay identical and
that the control sheet never mentions Phonebook, addresses, or a second arm.

Give the model the directory. Score with the same harness; the `checks` column
reports `n/a`, which is the asymmetry under test rather than missing data.

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
