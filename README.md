# Phonebook

**A human-operable semantic layer above programming languages.**

Operations have permanent, phone-number-shaped addresses. A registry — the
phonebook — says what each address *promises*. Backend mapping tables say how
that promise is *kept*, in Python, in Rust, in whatever comes next.

```phone
500-0000001@["examples/data/notes.txt"]  -> text     # READ_TEXT_FILE
200-0000001@[text]                       -> lines    # SPLIT_LINES
300-0000002@[lines, 000-0000001]         -> kept     # FILTER
300-0000009@[kept]                       -> n        # COUNT
100-0000001@[n]                                      # PRINT
```

That program runs three ways from one source — interpreted, compiled to Python,
compiled to Rust — and all three produce the same bytes. You can check that
claim yourself in about a minute:

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

---

## Why numbers

The address is the identity. Everything else — implementation, library,
language, performance — is allowed to change underneath it.

```
563-4567980
├── contract v2      what this address promises
└── implementation v17   how that promise is kept today
```

When a library rewrites its API, the tokenized program does not change a digit.
Only the mapping changes:

```
500-0000003@contract:1
  implementation:12 → old_package.load_csv
  implementation:13 → new_package.Table.from_csv
```

And one rule holds the whole thing up:

> **An issued address may never silently acquire a different meaning.**

That is not a promise in a document. `phonebook/frozen.json` stores a SHA-256
over every issued contract, and CI fails if one changes without a version bump.
Bumping is the only sanctioned move — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Nobody can read a seven-digit number

Correct. You are not supposed to. You look them up, the way you always did:

```bash
$ dial search "count how many times each word appears"
300-0000012  COUNT_OCCURRENCES  Tally how many times each value appears
              COUNT_OCCURRENCES(sequence: list<T>) -> map<T,int>

$ dial show 300-0000013
300-0000013   ENTRIES
  List a map's key/value pairs, sorted by key
  ...
  semantics pinned by this contract:
    - SORTED BY KEY, ascending, always.
    - Python dicts iterate in insertion order and Rust BTreeMaps iterate in
      key order. Sorting here is what removes that difference from every
      program's output.

$ dial next --produces "list<text>"     # what can I dial with what I'm holding?
$ dial annotate examples/word_freq.phone   # the source with every name resolved
$ dial run examples/word_freq.phone --trace
```

The resolver shipped before the interpreter did, on purpose.

## One script, two languages

`dial emit` turns the program above into real source. Same registry, same
contracts, different target:

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

Same semantic route. Different syntactic realization.

### Where it gets interesting

"Same output" only survives because the contracts pin the places the two
languages would otherwise quietly disagree. Each of these is a decision recorded
in the registry, with a conformance test:

| The disagreement | What the contract says | Who has to bend |
|---|---|---|
| `-7 / 2` | truncate toward zero → `-3` | **Python** — cannot use `//`, which floors to `-4` |
| `-7 % 2` | sign of the dividend → `-1` | **Python** — cannot use `%`, which gives `1` |
| Printing a boolean | `true` / `false` | **Python** — `str(True)` is `"True"` |
| Length of `"héllo"` | 5 — Unicode scalar values | **Rust** — must go through `chars()`, not `len()` |
| Iterating a map | `ENTRIES` sorts by key | **Python** — dicts iterate by insertion; `BTreeMap` is already sorted |
| Sorting descending | stable; reverse the *comparison* | both, explicitly — reversing the result would break ties differently |

Neither language wins. The contract wins. That is the entire idea, reduced to
six rows.

## The part that surprised us

Because every global address has a frozen contract that declares its effects,
and because local `000` extensions are the **only** place user-defined behavior
can live, you can compute what a program does instead of reading it:

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
    2  SPLIT_LINES        [secrets] -> lines
    3  FILTER             [lines, 000-0000001] -> real
    4  MAP                [real, 000-0000002] -> tidied
    5  JOIN               [tidied, "\n"] -> blob
    6  WRITE_TEXT_FILE    ["examples/data/.cache/telemetry.dat", blob]

LOCAL EXTENSIONS — 2 to read by hand
  These are the only places this program can do something the
  phonebook has not already described. …

VERDICT  needs review: filesystem-read, filesystem-write; 2 local extension(s)
```

You do not need to know Python or Rust to see that this thing reads a
credentials file and writes it somewhere else under a different name. Renaming
variables cannot hide it. Nesting cannot hide it. The only place custom behavior
can hide is a `000` address, and every one of them is printed in full.

**What this does not claim:** that a local extension is *safe*. It claims the
review surface is small, enumerated, and cannot grow without showing up in this
report. That is a smaller claim than "secure", and it is one the architecture
actually supports. See [docs/AUDIT.md](docs/AUDIT.md).

## Try it

```bash
pip install -e .

dial registry list                          # the whole phonebook, 54 addresses
dial show FILTER --backends                 # one entry, and how each target keeps it
dial search "remove duplicates"
dial check    examples/word_freq.phone
dial run      examples/word_freq.phone --trace
dial emit     examples/word_freq.phone --target rust
dial audit    examples/audit_demo.phone --strict
dial conformance --backend rust             # the independent implementation

dial brief                                  # everything needed to write a program
python scripts/demo.py                      # the whole proof, one command
pytest                                      # 200+ tests, including the ledger
```

## An open question

Both ideation sessions claimed a closed, enumerable address space should be a
better generation target for a language model than recalled syntax — no
hallucinated APIs, verifiable before execution. Neither tested it.
[experiments/](experiments/) is that test: 20 tasks, a scoring harness, verified
reference solutions, and priors recorded in advance so they can be wrong in
public. No results yet.

## What is deliberately not here

v0 has no mutation, no loops, no objects, no concurrency, no floats, and no
network. Iteration exists only as `MAP` / `FILTER` / `REDUCE` / `SORT` /
`UNIQUE`, and every value is immutable.

That is not a to-do list. A pure, immutable, first-order kernel is precisely why
one contract can drive a garbage-collected backend and a borrow-checked one
without the contract having to describe ownership or lifetimes. Widening the
kernel is where this design gets genuinely hard, and pretending otherwise would
make the demo dishonest. [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md) records the
objections that shaped it, including the ones still unanswered.

Self-hosting — writing the compiler in its own addresses — is the north star and
is sketched in [docs/SPEC.md](docs/SPEC.md) §8. v0 does not chase it.

## Layout

```
phonebook/         the registry: 54 addresses, a JSON schema, the frozen ledger
backends/          how python and rust keep each contract
runtime/python/    one function per address  ← the interpreter calls these too
runtime/rust/      one function per address  ← the independent implementation
src/phonebook/     the toolchain: parser, checker, resolver, interpreter, emitters, audit
examples/          .phone programs
generated/         committed output of `dial emit`, so the diff is reviewable
tests/             unit tests plus a conformance suite written in .phone itself
experiments/       the agent-authoring study: 20 tasks, data, reference solutions
docs/              the spec, the design notes, the audit model, the writing guide
```

Two files are written for agents rather than people:
[AGENTS.md](AGENTS.md) orients a coding agent working *on* the repo, and
[docs/WRITING-PHONE.md](docs/WRITING-PHONE.md) — `dial brief` — is a
self-contained ~6k-token guide to writing *in* the language, with the address
table generated from the registry so it cannot drift.

## Provenance

Designed across two long red-teaming sessions with frontier models. The
transcripts are not published, but [docs/DESIGN-NOTES.md](docs/DESIGN-NOTES.md)
records which objection produced which decision — including the ones that
produced the pure-immutable kernel, the `000` local-extension block, and the
audit model, and the ones still unanswered.

MIT licensed.
