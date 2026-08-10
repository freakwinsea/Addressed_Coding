# Phonebook v0.1 — Language and Registry Specification

Phonebook is a **human-operable semantic intermediate representation**. Programs
are written as routed calls to permanent numeric addresses. A registry — the
phonebook — says what each address *promises*. Backend mapping tables say how
that promise is *kept* in a particular language.

```
.phone script  →  parse  →  check contracts  →  ┬─ interpret (Python runtime)
                                                 ├─ emit Python
                                                 └─ emit Rust
```

The address is the identity. Everything else — implementation, language,
library, performance — is allowed to change underneath it.

---

## 1. Addresses

```
AAA-NNNNNNN
│   │
│   └── line number, 7 digits, zero-padded
└────── area code, 3 digits — the package
```

Example: `300-0000002` is `FILTER`.

An address may carry a version selector:

| Form | Meaning |
|---|---|
| `300-0000002` | Newest implementation compatible with the entry's current contract |
| `300-0000002@contract:1` | Any certified implementation of contract version 1 |
| `300-0000002@impl:3` | Exactly implementation 3 |
| `300-0000002@latest` | Explicitly the newest — same as bare, but stated |

**Contract version** = what the address promises (inputs, output, effects,
errors, semantics). **Implementation version** = how a backend currently keeps
that promise.

Version arithmetic:

| Change | Response |
|---|---|
| Faster, safer, different library — identical observable behavior | increment **impl** |
| Different inputs, output, effects, or guarantees | increment **contract** |
| Different behavior altogether | **new address** |

### 1.1 The immutability rule

> **An issued address may never silently acquire a different meaning.**

This is the load-bearing rule of the whole system, and it is enforced
mechanically rather than socially. `phonebook/frozen.json` records a SHA-256
over each issued contract. `tests/test_immutability.py` recomputes them; CI
fails if an existing contract changed without a version bump. The only
sanctioned way to add to the ledger is `dial registry freeze`.

## 2. Area codes

| Code | Block | Status in v0 |
|---|---|---|
| `000` | **Local extensions (PBX).** Project-scoped, defined inside the script. Never global, never resolvable outside their file, always flagged by `dial audit`. | active |
| `100` | Core | 6 addresses |
| `200` | Text | 12 |
| `300` | Collections | 16 |
| `400` | Numbers | 9 |
| `500` | I/O — the only block that touches the filesystem | 4 |
| `600` | Logic and comparison | 7 |
| `700` | Reserved for future shared blocks | empty |
| `800` | Python-native escape hatch | reserved, empty |
| `900` | Rust-native escape hatch | reserved, empty |
| `999` | Quarantine — unregistered or withdrawn. The checker rejects it. | reserved |

54 global addresses in v0. That is the entire budget; adding one is meant to
feel expensive (see `CONTRIBUTING.md`).

`000` is the inverse of "dial 9 for an outside line": it is the local
directory, reachable only from inside the building. It is also the *only*
mechanism for user-defined behavior in the language, which is what makes
auditing tractable — see §7.

## 3. Types

```
int  bool  text  unit  list<T>  map<K,V>  pair<K,V>  callable(T,...)->R  any
```

Generic variables `T`, `K`, `V`, `A`, `R` are unified at check time. `unit` is
the result of an address that produces no value — it cannot be bound, and a
call that returns anything else must be bound. `any` matches anything without
binding, which is how `PRINT` and `TO_TEXT` accept every value. `float` and
`bytes` are reserved names with no v0 addresses.

Some contracts constrain a generic: `comparable` (orderable by `SORT` and
`LESS_THAN`) and `keyable` (usable as a map key or by `UNIQUE`). Both resolve to
`int`, `text`, `bool` in v0. The constraint is checked once the variable
resolves to a concrete type.

Backend representations:

| Phonebook | Python | Rust |
|---|---|---|
| `int` | `int` | `i64` |
| `bool` | `bool` | `bool` |
| `text` | `str` | `String` |
| `list<T>` | `list[T]` | `Vec<T>` |
| `map<K,V>` | `dict[K,V]` | `BTreeMap<K,V>` |
| `pair<K,V>` | `tuple[K,V]` | `(K, V)` |

## 4. Program form

Line-oriented. One call per line. Single static assignment: every `-> name`
binds exactly once and never changes.

```phone
phonebook 0.1
pin 500-0000001 @impl:1

ext 000-0000001 NOT_EMPTY (line: text) -> bool {
  200-0000005@[line]        -> trimmed    # TRIM
  600-0000007@[trimmed]     -> blank      # IS_EMPTY
  600-0000001@[blank]       -> result     # NOT
  return result
}

500-0000001@["examples/data/input.txt"] -> text    # READ_TEXT_FILE
200-0000001@[text]                      -> lines   # SPLIT_LINES
300-0000002@[lines, 000-0000001]        -> kept    # FILTER
300-0000009@[kept]                      -> n       # COUNT
100-0000001@[n]                                    # PRINT
```

**Grammar**

```
program     := header? directive* (extension | call)*
header      := "phonebook" VERSION
directive   := "pin" ADDRESS VERSIONSEL
extension   := "ext" LOCALADDR NAME "(" params? ")" "->" TYPE "{" call* return "}"
params      := NAME ":" TYPE ("," NAME ":" TYPE)*
return      := "return" NAME
call        := ADDRESS VERSIONSEL? "@[" args? "]" ("->" NAME)?
args        := arg ("," arg)*
arg         := (NAME "=")? (literal | NAME | ADDRESS)
literal     := STRING | INT | "true" | "false"
comment     := "#" .* EOL
```

**Rules**

- Bindings are immutable and must be defined before use in the main body.
- Every operation is pure except the declared-effect addresses in `500`.
- **No loops and no mutation.** Iteration exists only as `MAP`, `FILTER`,
  `REDUCE`, `SORT`, `SORT_BY`, `UNIQUE`. This is deliberate: it is what lets a
  single contract generate correct Python *and* correct Rust without the
  contract having to encode ownership or lifetimes.
- **Branching is an expression:** `SELECT[cond, a, b]`. Both arms are evaluated
  eagerly in v0. This is the one place v0 semantics differ from what a reader
  might assume, so it is stated rather than hidden.
- **Higher-order arguments are addresses, not lambdas.** `FILTER[lines,
  000-0000001]` passes a local extension by address. Each extension compiles to
  an ordinary `def` / `fn`.
- Extensions may call other extensions. Recursion is rejected by the checker, so
  every extension terminates without needing a totality argument, and each one
  compiles to a plain `def` / `fn`.
- Extension names must be unique within a file: they appear in audit reports and
  in generated code, so a name has to identify one thing.
- An unreachable local extension is an error. Unreferenced local code is exactly
  what the audit model exists to prevent.
- `LIST` needs at least one item — with none there is nothing to infer the
  element type from.
- Binding names beginning with `_pb` are reserved, so generated source can never
  collide with a name you chose.
- Escapes in string literals: `\n`, `\t`, `\r`, `\\`, `\"`.

## 5. Determinism rules

The claim "same script, two languages, identical output" only survives if the
contracts pin the places where Python and Rust would otherwise disagree. These
are contract-level decisions, not implementation details, and each has a
conformance test:

| Hazard | Contract |
|---|---|
| Map iteration order (`dict` insertion order vs. `BTreeMap` key order) | `ENTRIES` returns pairs **sorted by key** |
| Sort stability | `SORT` and `SORT_BY` are **stable** |
| Dedupe order | `UNIQUE` preserves **first-occurrence** order |
| Integer division of negatives (Python floors, Rust truncates) | `DIV` **truncates toward zero** |
| Remainder sign | `MOD` takes the **sign of the dividend** |
| String indexing (bytes vs. chars) | `LENGTH` and `SLICE` count **Unicode scalar values**; `SLICE` clamps out-of-range bounds instead of failing |
| Boolean rendering (`True` vs. `true`) | `TO_TEXT` renders `true` / `false` |

## 6. Registry entries

Each entry lives in `phonebook/areas/<area>.json` and validates against
`phonebook/schema/entry.schema.json`:

```json
{
  "address": "300-0000002",
  "name": "FILTER",
  "summary": "Retain values satisfying a predicate",
  "keywords": ["filter", "select", "where", "retain", "keep"],
  "contract": {
    "version": 1,
    "inputs": [
      { "name": "sequence",  "type": "list<T>" },
      { "name": "predicate", "type": "callable(T)->bool" }
    ],
    "output": { "name": "result", "type": "list<T>" },
    "effects": [],
    "errors": ["predicate_failure"],
    "purity": "pure",
    "determinism": "deterministic"
  },
  "examples": ["300-0000002@[lines, 000-0000001] -> kept"],
  "conformance": [
    { "id": "filter.basic", "args": [["a", "", "b"], "@nonempty"], "expect": ["a", "b"] }
  ],
  "status": "active",
  "since": "0.1.0"
}
```

Backend mappings live in `backends/<target>/mappings.json`:

```json
"300-0000002": {
  "contract": 1,
  "implementations": [
    {
      "impl": 1, "status": "active", "since": "0.1.0",
      "runtime": "phonebook_rt::collections::filter_seq",
      "inline": "{0}.into_iter().filter(|x| {1}(x)).collect::<Vec<_>>()"
    }
  ]
}
```

`runtime` is the function the interpreter calls and the emitter falls back to.
`inline` is an optional idiomatic template used by the emitter when present.
Correctness never depends on `inline`; readability of the generated source does.

## 7. Auditability

Because every global address has a frozen contract with declared effects, and
because `000` extensions are the only place user-defined behavior can live,
a program's intent cannot be hidden behind naming or nesting. `dial audit`
reports:

1. the resolved intent flow in plain English,
2. effects grouped by capability (filesystem-read, filesystem-write; `process`
   and `network` exist as categories with no v0 addresses),
3. every `000` extension with its full body — the complete manual-review
   surface,
4. any unpinned or `@latest` address.

What this does **not** claim: that a `000` extension is safe. It claims the
review surface is small, enumerated, and impossible to grow silently.

## 8. Bootstrap path (north star, not v0)

The long-term shape, recorded so v0 does not foreclose it:

```
compiler0 (Python, this repo)
   → compiler1.phone  written only in registered addresses
   → compiler0 compiles compiler1
   → compiler1 compiles itself → compiler2
   → compiler1 and compiler2 agree ⇒ self-hosting
```

That requires a semantic kernel covering parsing, syntax trees, and error
handling — well beyond the 54 addresses of v0. v0 deliberately does not chase
it.

## 9. Out of scope in v0

Mutation, loops, objects, concurrency, network and GUI addresses, the `800` and
`900` native blocks, floats, and self-hosting.
