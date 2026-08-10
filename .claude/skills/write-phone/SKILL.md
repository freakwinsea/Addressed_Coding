---
name: write-phone
description: Write, debug, or review a .phone program — the Phonebook semantic IR where operations are numeric addresses like 300-0000002 rather than named functions. Use when the user asks for a program in .phone, mentions dialing an address, references a 7-digit operation address, asks to convert a script into .phone, or is working with files ending in .phone.
---

# Writing `.phone`

`.phone` programs route calls to numbered addresses from a fixed registry of 54
operations. You cannot write one from intuition about other languages — the
constraints are unusual and the address numbers are not guessable. Load the
reference first, every time.

## Step 1 — load the reference

Read **[docs/WRITING-PHONE.md](../../../docs/WRITING-PHONE.md)** in full. It is
~6k tokens and contains the syntax, the rules, the patterns, and the complete
address table with the semantics each contract pins.

Outside this repository, get the same content with:

```bash
dial brief
```

## Step 2 — find the addresses before writing

Do not guess an address number. Ever.

```bash
dial search "remove duplicates"        # description -> address
dial show 300-0000008                  # one address in full
dial next --produces "list<text>"      # what accepts what you're holding
```

## Step 3 — write it

Sketch the dataflow in plain names first — `read → split → filter → count →
print` — then find the address for each step and bind every intermediate value.
There are no nested expressions, so the sketch maps to lines one for one.

The constraints that trip people up:

- **No loops.** `MAP`, `FILTER`, `REDUCE`, `SORT`, `SORT_BY`, `UNIQUE` only.
- **No lambdas.** A callable argument is an address, so custom logic goes in a
  local `ext` in the `000` block and you pass its number.
- **No `if` statement.** `SELECT` is an expression over values you already have.
- **Single assignment.** Every name binds once.
- **Every result must be bound**, and addresses returning nothing must not be.
- **No floats.** Integers only.
- **Every `ext` must be used**, and none may recurse.

## Step 4 — check before claiming it works

```bash
dial check program.phone          # contracts, types, arity — fast, no execution
dial run   program.phone          # execute
dial run   program.phone --trace  # every call with names resolved, on stderr
```

`dial check` catches everything structural and its errors name the fix. Run it
after every edit. Never report a program as working without running it.

## Reviewing or auditing

```bash
dial annotate program.phone   # the source with every address resolved to a name
dial audit    program.phone   # capabilities, intent flow, and all local extensions
```

`dial audit` computes what a program *can* do from the frozen contracts, and
lists every `000` extension — the complete surface where custom behavior can
hide. It does not claim those extensions are safe; read them.

## When something cannot be expressed

The registry is 54 addresses and deliberately small. If a task seems to need
something absent, it is almost always buildable:

| Missing | Build it from |
|---|---|
| `ANY` / `ALL` | `FILTER` then `COUNT` then compare |
| `MAX` of a list | `SORT` then `REVERSE` then `FIRST`, or `REDUCE` with `MAX` |
| string concatenation | `LIST` then `JOIN` |
| a `for` loop | `MAP` or `REDUCE` |
| a lambda | a local `ext` |

Adding a new global address is a heavy, deliberate process
([CONTRIBUTING.md](../../../CONTRIBUTING.md)) and is almost never the right
answer to "my program needs this".
