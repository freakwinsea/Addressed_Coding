# Run 4 — a different model, a different route, the same score

**Date:** 2026-08-10
**Protocol:** fresh scrubbed clone, patterns withheld, task sheet clean.
Agentic. Different model from run 3.
**Score:** 20/20 contracts, 20/20 correct.

## Not one file matches run 3

All twenty differ, and not cosmetically. The two models took materially
different routes through the same 54 addresses:

| | reference | run 3 | run 4 |
|---|---|---|---|
| uses of `REDUCE` | 1 | 0 | **4** |
| uses of `SORT_BY` | 1 | 1 | 0 |
| distinct addresses used | 35 | 33 | **37** |

Run 3 avoided the two-parameter fold entirely — the construct the task set was
built to stress, whose only worked example was in the withheld section. Run 4
reached for it four times, in places nothing suggested it.

**t09 is better than both the reference and run 3.** Finding a maximum by
folding requires seeding the accumulator, and run 4 seeded it from the data:

```phone
300-0000011@[nums, 0]                -> first      # FIRST
300-0000004@[nums, 000-0000002, first] -> largest   # REDUCE with MAX
```

A hardcoded `0` would silently return 0 for an all-negative list. The reference
and run 3 both sorted and took the head, which sidesteps the problem rather
than solving it. This is the textbook fold, correctly seeded.

**t11** derives `any` as a fold with `OR` over a mapped list of booleans,
seeded `false`. Run 3 used filter-then-count-then-compare, which is what the
withheld pattern would have suggested. Neither is wrong; only one of them was
ever written down.

**t13** folds with `SELECT` for the tie-break, keeping the accumulator when
lengths are equal — the same tie semantics the reference gets from a stable
`SORT_BY`, arrived at from the other direction.

It also declined a shortcut run 3 found: `MAX` and `OR` both have arities that
fit `REDUCE` directly, and run 4 wrapped them in local extensions anyway. Its
own plan said "reduces with MAX"; the implementation was more conservative than
the plan.

## What this run does and does not establish

**Does:** the address space admits more than one correct route, and more than
one model can find one. Forty programs, two models, zero overlap, forty correct
results. That is the strongest evidence so far that the registry is navigable
rather than merely navigable-by-whoever-wrote-it.

**Does not:** anything about the core claim. Both runs were agentic, so
`checks` at 20/20 partly measures the loop rather than first-attempt validity.
Run 4's plan was prose rather than code, so unlike run 3 there is no
plan-versus-delivery delta to isolate.

**And the instrument is now at its ceiling.** Two runs at 100% means these
twenty tasks cannot discriminate between models, and they certainly cannot
discriminate between languages. A competent model would likely score 20/20 on
the Python control arm too, and 20/20 against 20/20 says nothing at all.

The next thing worth doing is therefore not another run of this set. It is
either the control arm — which nobody has run, and which is the only way any of
these numbers acquires meaning — or a harder tier with genuine headroom.
