# Run 5 — the control arm, and the result that ends this task set

**Date:** 2026-08-10
**Protocol:** standalone control kit, Python, no extra context. Agentic — the
model could run its programs. Third model, no plan offered.
**Score:** 20/20 correct.

## The finding is a null result

| Arm | Model | Correct |
|---|---|---|
| `.phone` | run 3 | 20/20 |
| `.phone` | run 4 | 20/20 |
| Python | run 5 | 20/20 |

Three sound runs, three models, sixty programs, sixty correct results. **The
task set cannot detect a difference between the arms, and the study as designed
cannot answer the question it was built for.**

That is worth recording as clearly as a positive result would have been. What it
rules out is any claim of the form "models write `.phone` more reliably than
Python" *at this scale*. Twenty tasks that top out at folding a CSV column are
inside every model's competence in both languages.

## The bias I flagged did not materialise

Before this run, `experiments/README.md` recorded that t10 and t11 favoured the
treatment arm by roughly two tasks: truncating division and lowercase `true` are
free from `DIV` and `TO_TEXT`, and hand-written in Python. My stated prior was
19/20 with those two as the likely misses.

Both were correct:

```python
mean = int(sum(numbers) / len(numbers))          # int() truncates toward zero
print('true' if has_hash else 'false')
```

The task text stated both requirements and the model read them. The asymmetry
was real in principle and zero in effect — which is the useful kind of wrong
prediction, because it was written down first.

(The t10 solution routes through a float, so it would lose precision on very
large integers where `.phone`'s integer-only `DIV` could not. Correct here,
quietly fragile — the sort of thing no correctness score at this size detects.)

## Why Python was the wrong control for the actual claim

The claim from the ideation sessions was **no hallucinated APIs** — a closed,
enumerable address space beats an open surface the model has to recall.

Python's standard library is the surface models know *best*. Choosing it as the
control tested the claim where it is least likely to hold, and it did not hold.
A fair test of "fewer hallucinated APIs" needs a target with a genuinely
unfamiliar or shifting surface, which is exactly the case a 54-address registry
is supposed to help with. That study is harder to set up honestly and was not
attempted here.

## What did show a difference, in every run

Not generation — verification. Run 3's plan scored 19/20 and its delivery scored
20/20, and the single character between them was found by `dial check` before
anything executed. Nothing in the Python arm has an equivalent step; the
`checks` column read `n/a` for all twenty.

A five-minute probe, mutating a correct t08 in both languages and asking only
what each catches *before running*:

| single-point mutation | `dial check` | `python -c compile` |
|---|---|---|
| wrong operation (`SUM` → `MUL`) | **caught** | missed |
| swapped arguments | **caught** | missed |
| undefined name | **caught** | missed |

Three of three against zero of three. That is not a subtle effect, it has
enormous headroom, and it is the claim that survives contact with the evidence:
not that models generate `.phone` more accurately, but that a `.phone` mistake
is caught before it runs and a Python mistake is not.

## The next study

Mutation detection, not first-attempt correctness. Take known-correct programs
in both arms, inject realistic single-point errors, and measure what fraction
each arm rejects statically. It has the headroom this set lacked, it needs no
model runs to establish the baseline, and it measures the thing that actually
differs.

The current twenty tasks stay useful as a validity check — they prove the
address space is navigable by three different models — but they are finished as
a measuring instrument.
