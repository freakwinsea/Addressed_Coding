# Run 3 — the first result worth anything

**Date:** 2026-08-10
**Protocol:** scrubbed clone, worked patterns withheld from the guide, task
sheet free of meta. Agentic — the model had a checkout and could run `dial`.
**Score:** 20/20 contracts, 20/20 correct.
**As planned, before it ran anything:** 19/20.

## The number that matters

The model wrote a full plan before touching a file, and that plan is archived in
`as-planned/`. Scoring the plan as written gives 19/20. Scoring what it
delivered gives 20/20. Diffing the two, across all twenty programs:

```
t17  200-000001@[text]     ->  200-0000001@[text]
```

One character. Nineteen files went through untouched, and the twentieth was
fixed after `dial check` said:

```
t17.phone:9: cannot read a call from '200-000001@[text] -> lines'
```

That is the contract layer working as the feedback loop the design claims — an
error caught before execution, named precisely enough to fix without debugging.
It is a small demonstration, but it is a real one, and it is the first thing
this study has produced that is not an artefact of its own harness.

## Where it beat the reference solutions

Two of its programs are better than the ones in `experiments/reference/`.

**t02 passed a registered address as a callable.**

```phone
300-0000003@[lines, 200-0000007]  -> uppercased     # MAP over UPPERCASE
```

The reference uppercases the whole file before splitting. That an ordinary
address can be handed to `MAP` when its arity fits is stated once, in section 3
of the guide, and demonstrated nowhere. The model read the sentence and used it.

**t18 avoided the construct the task was built to test.** The two-parameter
`REDUCE` was the predicted failure point of the whole set, and the only worked
example of it lived in the section that was withheld. The model mapped each row
to a value and summed the list instead — simpler, correct, and it never needed
the thing it was supposed to struggle with. The prediction was wrong because it
assumed the reference solution's route was the only one.

Two smaller divergences: t12 compares `qty` as text against `"0"` rather than
parsing it, which works on this data and is more fragile on messier input; and
t19 appends a newline per line so the written file ends with one, which differs
from the reference's bytes but matches the task description at least as well.

## The caveat

`brief.md` was a tracked file in the repository — swept in by a `git add -A`
during run 2's cleanup — so it cloned into this study clone and sat at its root.
It contained the *old* withholding notice: "removed when this guide is used as a
measuring instrument". The worked patterns themselves were not in it, so no
solution leaked, but the model had a file at hand announcing that it was being
measured and that something had been kept from it.

Whether it opened that file is unknown.

**Assessment.** The correctness result stands: the method for these tasks was
not available anywhere in the clone, and the two places the model out-thought
the reference are not things a notice could have told it. What cannot be ruled
out is evaluation awareness. Treat 20/20 as sound and the behavioural reading —
that it planned first, then verified — as suggestive rather than clean.

## How it evaded four separate scans

`brief.md` was UTF-16, because PowerShell's `>` redirect writes UTF-16 on
Windows. Every leak scan run against the clone searched for ASCII byte
sequences. In a UTF-16 file the bytes are `w\0i\0t\0h\0`, so `grep withheld`
cannot match it and neither can `grep -I withheld`; the `-I` flag was not even
the problem. The one file that leaked was the one file the scanner could not
see, and the scanner reported clean.

Scanning was the wrong instrument. `tests/test_every_tracked_text_file_is_utf8`
now refuses to hold a non-UTF-8 tracked file at all, with a negative control
confirming it fails on a planted one. The file is deleted and gitignored.

That is the fifth leak of experimenter-facing material into subject-facing
material across three runs. Each was found by a different method, and none was
found by the check written after the previous one.
