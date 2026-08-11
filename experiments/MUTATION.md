# Mutation detection

The authoring study returned a null result: three models, sixty programs, sixty
correct, no difference between arms. What differed in every run was not
generation but verification, so this measures that instead — and it needs no
model runs at all.

```bash
python scripts/mutation_study.py --report mutation_report.md
```

## Result

```
mutation                         phone            python
--------------------------------------------------------
dropped_argument                 50/51               0/2
mistyped_address               132/132                 —
swapped_arguments                38/47              0/22
undefined_name                 111/111             14/20
wrong_address                  130/132                 —
wrong_operation                      —              4/21
--------------------------------------------------------
SHARED OPERATORS          199/209  95%        14/44  31%
all operators             461/473  97%        18/65  27%
```

**95% against 31% on the operators both arms can express.** The headline figure
is 97% against 27%, but it should not be quoted: more than half the `.phone`
mutants are address mutations, which have no exact Python twin, and they are the
class `.phone` catches best. The shared subtotal is the number that means
something, and the gap survives the restriction.

## Method

Standard mutation testing, with the step that makes it honest:

1. Known-correct programs from both arms — `experiments/reference/` and the
   control arm's Python.
2. Single-point mutations of the same classes: a mistyped address, a swapped
   argument, a dropped argument, a stale name, a substituted operation. These
   are the mistakes the runs actually produced; run 3's only error was a
   mistyped address.
3. **Every mutant is executed and compared against the original.** Those that
   print the same thing are *equivalent* and are discarded — failing to catch a
   mutation that changes nothing is not a failure. This cost 567 program runs
   and removed 6 `.phone` mutants and 23 Python ones.
4. Of the mutants that do change behavior, what fraction does each arm reject
   **statically**, before execution?

**The control arm gets its best tools.** `dial check` is compared against
`compile`, then `ruff` (F and E9 rules), then `mypy` — not against a bare syntax
check, which would have proved nothing. Of Python's 14 catches, ruff found 14
and mypy 4; the tools carried it, and they still lost by three to one.

## Where the difference comes from

**`undefined_name`: 111/111 against 14/20.** Both arms do well; ruff is good at
this. The gap is the six Python cases where a renamed variable was still
plausibly defined at module scope.

**`swapped_arguments`: 38/47 against 0/22.** This is the interesting one. Python
cannot statically object to `f(b, a)` when both are strings — nothing is wrong
until it runs. `.phone` catches it whenever the two parameters have different
declared types, which the contract states. The nine `.phone` escapes are calls
whose arguments genuinely share a type, where no checker could know either.

**`wrong_address`: 130/132.** Change a digit and you usually land on an address
that does not exist, or one whose contract does not fit the arguments you are
holding. A closed, enumerable vocabulary means a wrong name is usually an
*invalid* name. Python's nearest equivalent, substituting one valid builtin for
another, is caught 4 times in 21 — because `max` where you meant `sum` is
perfectly well-typed.

That contrast is the whole finding in one line: **an open vocabulary makes wrong
code look well-formed; a closed one makes it look wrong.**

## What this does not claim

- **Not that `.phone` programs are more correct.** The authoring study says
  otherwise, and it is committed alongside this one.
- **Not that mutation classes appear equally often in real work.** The
  operators are applied uniformly to every eligible site. A model that mistypes
  addresses often and swaps arguments rarely would see a different practical
  benefit.
- **Not a language comparison.** It compares one checker against another arm's
  best available tooling on programs of about ten lines. Larger programs, richer
  Python type annotations, or a stricter mypy configuration would all move the
  Python number, probably upward.
- **Sample sizes are unequal** — 473 live `.phone` mutants against 65 Python.
  `.phone` programs have more mutable call sites per line. The per-operator
  ratios matter more than the totals, and `dropped_argument` at 0/2 is too small
  to read anything into.

The claim that survives is narrow and supported: **a mistake in a `.phone`
program is usually caught before it runs, and the same mistake in Python usually
is not.** That is a smaller claim than the one the ideation sessions made, and
unlike that one it has evidence.
