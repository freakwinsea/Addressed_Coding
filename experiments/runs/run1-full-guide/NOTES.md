# Run 1 — invalid, kept for the record

**Date:** 2026-08-10
**Protocol:** scrubbed clone, agent given `experiments/TASKS.md` and the full
`docs/WRITING-PHONE.md`.
**Result:** 20/20 contracts, 20/20 correct.
**Status:** confounded. Do not cite this number.

## What happened

The agent read the guide, looked at the four data files, and wrote all twenty
programs in one pass without running anything. It then attempted to score them,
discovered the answer key had been stripped from its clone, and verified t01,
t19, and t20 by hand before reporting.

Scoring from the source repository afterwards: every program passes `dial check`
and produces byte-exact expected output, including t18, which was predicted to
be the hardest in the set.

## Why it does not count

`docs/WRITING-PHONE.md` §5 "Patterns you will need" contains eight worked
examples, and the guide and the tasks were written in the same sitting. Every
one of the eight maps onto tasks:

| Pattern in §5 | Tasks it solves |
|---|---|
| Filter a list — using the literal `"ERROR"` | t06, t07 |
| Transform a list — `AS_NUMBER` wrapping `PARSE_INT` | t08, t09, t10 |
| Pull a field out of a CSV row — `GET` with a fallback | t12, t16 |
| Biggest / smallest — `SORT_BY` descending then `FIRST` | t13, t17 |
| Total up a derived value — `REDUCE` with a two-parameter ext | t18 |
| Does anything match? — filter, count, compare | t11 |
| Build a string from parts — `LIST` then `JOIN` | t15 |
| Rank a tally — `COUNT_OCCURRENCES` → `ENTRIES` → `SORT_BY` | t14 |

The model was given the method and applied it. That is a measurement of recall
against an example the experimenter supplied, not of whether a closed address
space is a good generation target.

The solutions are structurally identical to `experiments/reference/` with
different identifier names — which is what convergence on a supplied pattern
looks like, and also what a small constrained language looks like. Run 1 cannot
distinguish those two explanations. That is the whole problem with it.

## What survives

Two claims the confound does not touch:

1. **All twenty tasks are expressible and navigable.** Nothing in the set was
   impossible, ambiguous, or awkward enough to defeat a model working from the
   docs. The task set itself is validated.
2. **`checks` was 20/20 on files written before anything was executed.** §5 gave
   away the *method*; it did not supply syntax, arity, types, or address
   numbers for tasks it does not cover. Twenty programs in a language invented
   last week, no compiler feedback, zero contract violations.

## What changed because of it

- `dial brief --minimal` withholds §5. Use it for every measured run.
- `scripts/score_attempts.py` now detects a scrubbed checkout and says so once,
  instead of reporting "no expected output" twenty times.
- `TASKS.md` tells the model to install into a virtualenv. This run's bare
  `pip install -e .` replaced the study author's own editable install, silently
  repointing their `dial` at the scrubbed clone.

## Rerun as

```bash
dial brief --minimal > /tmp/brief.md      # hand this over, not the full guide
python scripts/prepare_study_clone.py /path/to/clone
python scripts/score_attempts.py /path/to/clone/attempts
```
