# Phonebook

**A language where operations have permanent numeric addresses instead of names,
and a registry states what each address promises.**

The point of that is not the numbers. It is this: take a working program, inject
a single realistic mistake, and ask what gets rejected *before the program runs*.

| single-point mistake | Phonebook | Python (ruff + mypy) |
|---|---|---|
| swapped two arguments | **38/47** | 0/22 |
| dropped an argument | **50/51** | 0/2 |
| referenced a name that isn't bound | **111/111** | 14/20 |
| called the wrong operation † | **130/132** | 4/21 |
| **shared mutation classes** | **95%** | **31%** |

† The two arms express this differently — a mistyped address versus a
substituted builtin — so it is *excluded* from the bolded subtotal. Counting it
would read 97% against 27%, and that figure should not be quoted.

An open vocabulary makes wrong code look well-formed. `f(b, a)` is perfectly
valid Python when both are strings; `max` where you meant `sum` type-checks
fine. A closed vocabulary with declared contracts makes the same mistakes look
wrong, statically, in under a second.

Method, sample sizes, and the things this does *not* claim:
[experiments/MUTATION.md](experiments/MUTATION.md). Reproduce it with
`python scripts/mutation_study.py`.

---

## What a program looks like

```phone
500-0000001@["examples/data/notes.txt"]  -> text     # READ_TEXT_FILE
200-0000001@[text]                       -> lines    # SPLIT_LINES
300-0000002@[lines, 000-0000001]         -> kept     # FILTER
300-0000009@[kept]                       -> n        # COUNT
100-0000001@[n]                                      # PRINT
```

Every operation is an address. `300-0000002` is `FILTER`, permanently. The
registry — the phonebook — says what it takes, what it returns, what it may
fail with, and what it promises about ordering. The checker holds every call to
that.

You are not meant to memorize the numbers. You look them up, the way you always
did with a phonebook:

```bash
$ dial search "count how many times each word appears"
300-0000012  COUNT_OCCURRENCES  Tally how many times each value appears
              COUNT_OCCURRENCES(sequence: list<T>) -> map<T,int>

$ dial next --produces "list<text>"        # what can I dial with what I'm holding?
$ dial annotate program.phone              # the source with every name resolved
$ dial run program.phone --trace           # execution, with names
```

Those shipped before the interpreter did, on purpose.

## What we tested first, and it failed

Both ideation sessions behind this project claimed a closed address space would
be a better *generation* target for a language model — fewer hallucinated APIs.
[experiments/](experiments/) tested that, with priors written down in advance.

**The answer was no.** Two models writing `.phone` scored 20/20. A third writing
Python scored 20/20. Sixty programs, sixty correct, no detectable difference.
The tasks sit inside every model's competence in both languages, and Python's
standard library — the surface models know best — was the wrong control for a
claim about unfamiliar APIs.

Two earlier runs were void: the first because the guide's worked examples solved
most of the tasks, the second because the harness left the previous run's
answers lying around. Both are written up rather than deleted.

What differed in every run was verification, not generation. That is why the
number at the top of this page is about mistakes caught rather than programs
written, and why it is a much narrower claim than the one this project started
with.

## The address is the identity

Everything else — implementation, library, language, performance — is allowed to
change underneath it.

```
563-4567980
├── contract v2          what this address promises
└── implementation v17   how that promise is kept today
```

When a library rewrites its API, the program does not change a digit. Only the
mapping does:

```
500-0000003@contract:1
  implementation:12 → old_package.load_csv
  implementation:13 → new_package.Table.from_csv
```

One rule holds the whole thing up:

> **An issued address may never silently acquire a different meaning.**

That is not a promise in a document. `phonebook/frozen.json` stores a SHA-256
over every issued contract and CI fails if one changes without a version bump.
It caught a contract edit during development. See [CONTRIBUTING.md](CONTRIBUTING.md).

## One script, two languages

Because the registry describes meaning rather than syntax, the same program
compiles to either backend:

<table>
<tr><th>Generated Python</th><th>Generated Rust</th></tr>
<tr><td>

```python
def not_blank(line):
    trimmed = _pb_text.trim(line)
    blank = (trimmed == "")
    keep = (not blank)
    return keep


def main() -> None:
    text = _pb_io.read_text_file("…/notes.txt")
    lines = _pb_text.split_lines(text)
    kept = [_pb_x for _pb_x in lines
            if not_blank(_pb_x)]
    n = len(kept)
    _pb_core.print_value(n)
```

</td><td>

```rust
fn not_blank(line: &String) -> bool {
    let line: String = line.clone();
    let trimmed: String = rt::text::trim(&line);
    let blank: bool = trimmed.is_empty();
    let keep: bool = (!blank);
    keep
}

fn main() {
    let text: String = rt::io_::read_text_file(&"…/notes.txt".to_string());
    let lines: Vec<String> = rt::text::split_lines(&text);
    let kept: Vec<String> = lines.iter().cloned()
        .filter(|_pb_x| not_blank(_pb_x)).collect::<Vec<_>>();
    let n: i64 = (kept.len() as i64);
    rt::core::print_value(&n);
}
```

</td></tr>
</table>

Interpreted, compiled to Python, compiled to Rust — all three produce the same
bytes. Checkable in about a minute:

```bash
git clone <this repo> && cd phonebook && pip install -e . && python scripts/demo.py
```

```
example         interpret     python       rust   verdict
---------------------------------------------------------
line_count             ok         ok         ok   PASS
word_freq              ok         ok         ok   PASS
records                ok         ok         ok   PASS
audit_demo             ok         ok         ok   PASS

all 4 examples produced identical output through 3 independent paths
```

"Same output" only survives because the contracts pin the places the two
languages would otherwise quietly disagree — each a decision in the registry,
each with a conformance test:

| The disagreement | What the contract says | Who has to bend |
|---|---|---|
| `-7 / 2` | truncate toward zero → `-3` | **Python** — cannot use `//`, which floors to `-4` |
| `-7 % 2` | sign of the dividend → `-1` | **Python** — cannot use `%`, which gives `1` |
| Printing a boolean | `true` / `false` | **Python** — `str(True)` is `"True"` |
| Length of `"héllo"` | 5 — Unicode scalar values | **Rust** — must go through `chars()`, not `len()` |
| Iterating a map | `ENTRIES` sorts by key | **Python** — dicts iterate by insertion; `BTreeMap` is already sorted |
| Sorting descending | stable; reverse the *comparison* | both — reversing the result would break ties differently |

Neither language wins. The contract wins.

## You can compute what a program does

Every global address declares its effects, and local `000` extensions are the
only place user-defined behavior can live. So capabilities are computed, not
inferred from names:

```
$ dial audit examples/audit_demo.phone

CAPABILITIES
  filesystem-read    1 call(s) — reads files
      500-0000001 READ_TEXT_FILE  ["examples/data/credentials.txt"]
  filesystem-write   1 call(s) — writes files
      500-0000002 WRITE_TEXT_FILE  ["examples/data/.cache/telemetry.dat", blob]
  network            not used
  process            not used

INTENT — what the program does, in order
    1  READ_TEXT_FILE     ["examples/data/credentials.txt"] -> secrets
    ...
    6  WRITE_TEXT_FILE    ["examples/data/.cache/telemetry.dat", blob]

LOCAL EXTENSIONS — 2 to read by hand

VERDICT  needs review: filesystem-read, filesystem-write; 2 local extension(s)
```

You do not need to read Python or Rust to see that this reads a credentials file
and writes it elsewhere under a different name. Renaming cannot hide it; nesting
cannot hide it.

**It does not claim a local extension is safe.** It claims the review surface is
small, enumerated, and cannot grow without appearing in this report — a smaller
claim than "secure", and one the architecture actually supports.
[docs/AUDIT.md](docs/AUDIT.md).

## Try it

Clone first — an editable install from a checkout is the only supported path
today ([KI-1](docs/KNOWN-ISSUES.md)).

```bash
pip install -e .

dial registry list                   # the whole phonebook, 54 addresses
dial show FILTER --backends          # one entry, and how each target keeps it
dial search "remove duplicates"
dial check    examples/word_freq.phone
dial run      examples/word_freq.phone --trace
dial emit     examples/word_freq.phone --target rust
dial audit    examples/audit_demo.phone --strict
dial conformance --backend rust      # the independent implementation
dial brief                           # everything needed to write a program

python scripts/demo.py               # three backends, identical bytes
python scripts/mutation_study.py     # the number at the top of this page
pytest                               # 225 tests, including the ledger
```

## What is deliberately not here

v0 has no mutation, no loops, no objects, no concurrency, no floats, and no
network. Iteration exists only as `MAP` / `FILTER` / `REDUCE` / `SORT` /
`UNIQUE`, and every value is immutable.

That is not a to-do list. A pure, immutable, first-order kernel is precisely why
one contract can drive a garbage-collected backend and a borrow-checked one
without the contract describing ownership or lifetimes. Widening the kernel is
where this design gets genuinely hard, and pretending otherwise would make the
demo dishonest. [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) records the
objections that shaped it, including the ones still unanswered.

Self-hosting — writing the compiler in its own addresses — is the north star,
sketched in [docs/SPEC.md](docs/SPEC.md) §8. v0 does not chase it.

## Layout

```
phonebook/         the registry: 54 addresses, a JSON schema, the frozen ledger
backends/          how python and rust keep each contract
runtime/python/    one function per address  ← the interpreter calls these too
runtime/rust/      one function per address  ← the independent implementation
src/phonebook/     parser, checker, resolver, interpreter, emitters, audit
examples/          .phone programs
generated/         committed output of `dial emit`, so the diff is reviewable
tests/             unit tests plus a conformance suite written in .phone itself
experiments/       both studies: tasks, data, every run, including the void ones
docs/              the spec, the design notes, the audit model, the writing guide
```

Two files are written for agents rather than people: [AGENTS.md](AGENTS.md)
orients a coding agent working *on* the repo, and
[docs/WRITING-PHONE.md](docs/WRITING-PHONE.md) — `dial brief` — is a
self-contained ~6k-token guide to writing *in* the language, with the address
table generated from the registry so it cannot drift.

## Provenance

Designed across two long red-teaming sessions with frontier models. The
transcripts are not published, but [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md)
records which objection produced which decision — including the ones that
produced the pure-immutable kernel, the `000` local-extension block, and the
audit model, and the ones still unanswered.

Every experimental run is committed, including the two that were void and the
one that returned a null result. The claim at the top of this page is what
survived.

MIT licensed.
