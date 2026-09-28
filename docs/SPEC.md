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
| `400` | Numbers | 75 |
| `500` | I/O — the only block that touches the filesystem | 4 |
| `600` | Logic and comparison | 7 |
| `700` | Reserved for future shared blocks | empty |
| `800` | Python-native escape hatch | reserved, empty |
| `900` | Rust-native escape hatch | reserved, empty |
| `999` | Quarantine — unregistered or withdrawn. The checker rejects it. | reserved |

120 global addresses in v0. That is the entire budget; adding one is meant to
feel expensive (see `CONTRIBUTING.md`).

`000` is the inverse of "dial 9 for an outside line": it is the local
directory, reachable only from inside the building. It is also the *only*
mechanism for user-defined behavior in the language, which is what makes
auditing tractable — see §7.

## 3. Types

```
int  bigint  float  decimal  fraction  bool  text  unit  list<T>  map<K,V>  pair<K,V>  callable(T,...)->R  any
```

Generic variables `T`, `K`, `V`, `A`, `R` are unified at check time. `unit` is
the result of an address that produces no value — it cannot be bound, and a
call that returns anything else must be bound. `any` matches anything without
binding, which is how `PRINT` and `TO_TEXT` accept every value. `bytes` is a
reserved name with no v0 addresses.

Some contracts constrain a generic: `comparable` (orderable by `SORT` and
`LESS_THAN`), `keyable` (usable as a map key or by `UNIQUE`), and `numeric`
(accepted by the number comparisons in area 400). `comparable` is `int`,
`bigint`, `float`, `decimal`, `fraction`, `text`, `bool`; `keyable` is `int`,
`bigint`, `fraction`, `text`, `bool`; `numeric` is `int`, `bigint`, `float`, `decimal`, `fraction`. The
constraint is checked once the variable resolves to a concrete type.

`int` and `float` never mix. There is no implicit conversion: `ADD` takes two
`int`s, `ADD_FLOAT` takes two `float`s, and `TO_FLOAT` / `TO_INT` cross between
them. `bigint` is the same: `ADD_BIG` takes two `bigint`s, and `TO_BIG` /
`BIG_TO_INT` cross to and from `int`. `decimal` too: `ADD_DEC` takes two
`decimal`s, and `TO_DEC`, `BIG_TO_DEC`, `DEC_TO_INT`, `DEC_TO_FLOAT` and
`FLOAT_TO_DEC` cross over. `fraction` is its own type too: `ADD_FRACTION` takes
two fractions, `MAKE_FRACTION` builds one from two ints, and
`FRACTION_TO_FLOAT`, `FLOOR_FRACTION` and `ROUND_FRACTION` leave it.

### 3.1 Floats

A `float` is an IEEE 754 binary64 value. Python's `float` and Rust's `f64` are
both exactly that, and both get `+ - * /` from the same hardware rounding
(to nearest, ties to even). Everything *around* the arithmetic is where the two
languages differ, so the contracts pin it:

| Question | Contract |
|---|---|
| NaN and infinity | **They never exist.** A result too large to be finite is an `overflow` error. Dividing by zero, `0.0 / 0.0` included, is a `division_by_zero` error. `PARSE_FLOAT` rejects `nan`, `inf`, and anything too large, returning its fallback. A literal too large to be finite is a parse error. |
| Negative zero | **Zero has one sign.** Any result that would be `-0.0` is `0.0`, so it can never print as `-0.0` or behave differently from `0.0`. |
| Ordering | Numeric. With no NaN and one zero, the order is total, which is why `float` is `comparable`. |
| Equality and map keys | `float` is **not** `keyable`: equality on computed floats is a trap (`0.1 + 0.2` is not `0.3`), and Rust's `f64` cannot key a `BTreeMap`. So `EQUALS` does not take floats; `NUMBER_EQUALS` does, and is exact. For a computed float, `CLOSE_TO` asks whether two values are within a tolerance. |
| Rounding halves | `ROUND` sends halves **away from zero**: 2.5 is 3.0. Python's `round()` would say 2.0. It decides on the exact binary value, so 0.49999999999999994 is 0.0. |
| To an int | `TO_INT` **truncates toward zero** and is an `overflow` error outside the 64-bit range. Rust's `as i64` would saturate instead. |
| From an int | `TO_FLOAT` rounds to nearest, ties to even, which only matters past 2^53. |
| Reading text | `PARSE_FLOAT` accepts `[+-]digits[.digits][(e|E)[+-]digits]` after trimming, and nothing else: not `.5`, `5.`, `1_000`, `nan`, `inf`. Rust's parser would take `.5` and `inf`; Python's would take `1_000`. |
| Printing | See below. |

**How a float prints.** `TO_TEXT` (and so `PRINT`) writes the shortest decimal
digit string that reads back as the same float. When several strings of that
length do, it takes the one closest to the exact value, and when two are
equally close, the one ending in an even digit. With those digits
`d1 d2 ... dn` and decimal exponent `E` (value = `d1.d2...dn x 10^E`):

- if `-4 <= E < 16`, positional, always with a digit after the point:
  `1.0`, `-2.5`, `0.0001`, `123456789012345.6`;
- otherwise `d1`, then `.` and the rest of the digits if there are any, then
  `e`, a sign, and at least two exponent digits: `1e+16`, `1.5e-05`, `5e-324`.

That is exactly Python's `repr()` of a finite float. It is *not* Rust's
`Display`, which writes `1.0` as `1` and `1e16` as `10000000000000000`, and it
is not quite Rust's `{:e}` either, which breaks a tie between two shortest
candidates upward (`635057293855503.25` gives `...503.3`; the contract says
`...503.2`). Both runtimes take their digits from their host and apply the
layout by hand, and `tests/conformance/float_rendering.phone` holds the cases
where the hosts would otherwise disagree.

A float literal in a program is written the same way `PARSE_FLOAT` reads one,
without the leading `+`: `1.5`, `-0.25`, `2e10`, `6.02e23`.

### 3.2 Bigints

A `bigint` is an exact whole number of **at most 4000 decimal digits**. It never
rounds and never wraps. Python's `int` already is one. Rust's standard library
has nothing like it, so the Rust runtime carries its own, `phonebook_rt::BigInt`
(`runtime/rust/phonebook_rt/src/bigint.rs`): sign and magnitude, base-10^9
limbs, schoolbook algorithms, no dependencies.

| Question | Contract |
|---|---|
| How big | At most 4000 digits. Any result with more is an `overflow` error, and a literal with more is a parse error. Leading zeros do not count. |
| Why a ceiling at all | Without one, `POW_BIG(2, 2^62)` never finishes, and Python refuses to print an int of more than 4300 digits. 4000 is under that, so neither backend needs special settings. |
| Division | `DIV_BIG` truncates toward zero and `MOD_BIG` takes the dividend's sign, exactly as `DIV` and `MOD` do. |
| Powers | `POW_BIG` takes an `int` exponent and checks every step, so no intermediate grows past 8000 digits before an overflow is noticed. |
| Reading text | `PARSE_BIG` uses the `PARSE_INT` grammar: `[+-]?digits` after trimming. |
| Printing | Base 10, a leading `-` for negatives, no suffix: the same as `int`. |

A bigint literal is an integer with an `n` suffix, as in JavaScript: `12n`,
`-123456789012345678901234567890n`. `-0n` is `0n`.
`tests/conformance/bigint_random.phone` (written by
`scripts/gen_bigint_random.py`) holds seeded random operands for all five
arithmetic operations, so the Rust arithmetic is checked against Python's.

### 3.3 Decimals

A `decimal` is an exact base-10 number: a whole-number **coefficient** and a
**scale**, the count of digits after the point. `0.30` is (30, 2). It is for
amounts that must add up exactly, such as money: `0.10 + 0.20` is `0.30`, where
a float gives `0.30000000000000004`.

Neither backend uses a library for it. Python's `decimal` module rounds to a
context precision, has signed zeros, NaN and infinity, and prints in its own
layout, so pinning it to match Rust would be harder than writing the type out.
Each runtime carries its own, written side by side:
`runtime/python/phonebook_rt/decimal_.py` holds the coefficient in a Python
`int`, and `runtime/rust/phonebook_rt/src/decimal.rs` holds it in the Rust
runtime's `BigInt`.

| Question | Contract |
|---|---|
| How big | At most 4000 digits in the coefficient (the bigint ceiling), and at most 1000 of them after the point. Anything past either is an `overflow` error, and a literal past either is a parse error. |
| Places | Kept, never normalized away: `0.10 + 0.20` prints `0.30`. `ADD_DEC` and `SUB_DEC` give the larger scale of the two, `MUL_DEC` the sum of both. |
| Rounding | Only `DIV_DEC` and `ROUND_DEC` round, each to a number of places the program gives (0 to 1000, else `invalid_places`), and always **halves away from zero**, the same as `ROUND`. Not Python's `round()` or the `decimal` module's default, which go to even. |
| Equality and order | By value: `0.3` and `0.30` are equal and sort as ties. That is also why `decimal` is comparable but not keyable: a map could not say which of the two it kept. |
| Zero | Has one sign: `-0.00d` is `0.00`. |
| Floats | `DEC_TO_FLOAT` reads the decimal's text the way `PARSE_FLOAT` would. `FLOAT_TO_DEC` takes the float's shortest digits, the ones `TO_TEXT` prints, so `0.1` becomes `0.1` rather than the float's exact binary value. |
| Printing | Every digit, the point `scale` places from the right, at least one digit before it, no exponent, no suffix: `0.30`, `-0.05`, `12`. |

A decimal literal is digits, an optional fraction, and a `d` suffix: `19.99d`,
`-0.05d`, `3d`. `tests/conformance/decimal_random.phone` (written by
`scripts/gen_decimal_random.py`) holds seeded random operands for the
arithmetic, so each runtime's hand-written decimal is checked against the
other's.

### 3.4 Fractions

A `fraction` is an exact ratio of two 64-bit integers: `1/3` stays `1/3` and
`1/10 + 2/10` is exactly `3/10`. Neither host's own fraction type is used —
Python's `fractions.Fraction` grows without limit and Rust has none — so both
runtimes write the same small algorithm by hand, with no library.

| Question | Contract |
|---|---|
| Form | **Always lowest terms, denominator positive**, sign on the numerator. `MAKE_FRACTION(2, -4)` is `-1/2`; `0/5` is `0/1`. Every value has one form, so equality is exact. |
| Size | The working is exact (wider than 64 bits in both runtimes); only the lowest-terms result must fit, numerator and denominator each in a 64-bit signed integer. Otherwise it is an `overflow` error. |
| Zero | A zero denominator, or dividing by a zero fraction, is a `division_by_zero` error. |
| Ordering and keys | By exact value, never through a float. `fraction` is both `comparable` and `keyable`. |
| To a float | `FRACTION_TO_FLOAT` rounds the exact value once, to nearest, ties to even. Not `float(n) / float(d)`, which can round three times. |
| To an int | `FLOOR_FRACTION` goes toward negative infinity (`-7/2` is `-4`; Rust's `/` would give `-3`). `ROUND_FRACTION` sends halves away from zero, like `ROUND`. |
| Reading text | `PARSE_FRACTION` accepts `[+-]digits[/digits]` after trimming, and nothing else: not `1 / 3`, `1/-3`, `1.5`. Each part as written must fit in 64 bits; a zero denominator returns the fallback. |
| Printing | `TO_TEXT` writes `n/d` in lowest terms (`-1/3`), or just `n` when the denominator is 1 (`4/2` prints `2`). `PARSE_FRACTION` reads every such string back to the same fraction. |

There is no fraction literal; build one with `MAKE_FRACTION` or `PARSE_FRACTION`.

### 3.5 Printing with places

`FORMAT_FLOAT`, `FORMAT_DEC` and `FORMAT_FRACTION` print a number as text with
exactly `places` digits after the point (0 to 1000; no point at all when it is
0). All three round halves away from zero, as `ROUND` and `ROUND_DEC` do, and
none uses the host's formatter.

| | Rule |
|---|---|
| Floats | The digits `TO_TEXT` shows are rounded, never the binary value: `2.675` to 2 places is `2.68`. Python's `format()` and Rust's `{:.2}` both round the binary value half to even and give `2.67`. |
| Decimals | `ROUND_DEC` then `TO_TEXT`, without the 4000-digit ceiling. |
| Fractions | The exact value, rounded once, never via a float: `1/3` to 30 places is thirty `3`s. |
| Layout | Plain digits, never an exponent (`1e+20` to 1 place is `100000000000000000000.0`), and never a negative zero (`-0.001` to 2 places is `0.00`). |

Backend representations:

| Phonebook | Python | Rust |
|---|---|---|
| `int` | `int` | `i64` |
| `bigint` | `int` | `phonebook_rt::BigInt` |
| `decimal` | `phonebook_rt.decimal_.Decimal` | `phonebook_rt::Decimal` |
| `float` | `float` | `f64` |
| `fraction` | `phonebook_rt.numbers_.Fraction` | `phonebook_rt::numbers_::Fraction` |
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
literal     := STRING | INT | BIGINT | DECIMAL | FLOAT | "true" | "false"
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
| Float rendering (`1.0` vs. `1`, `1e+16` vs. `10000000000000000`) | `TO_TEXT` writes the shortest round-trip digits in Python's `repr` layout (§3.1) |
| Float NaN, infinity, negative zero | none of them exist (§3.1) |
| Rounding halves (Python to even, Rust away from zero) | `ROUND` sends halves **away from zero** |
| Float to int (Rust saturates) | `TO_INT` **truncates**, and out of range is an `overflow` error |
| Fractions (Python's grow without limit, Rust has none) | always lowest terms, 64-bit parts, `overflow` past that (§3.4) |

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
handling — well beyond the 120 addresses of v0. v0 deliberately does not chase
it.

## 9. Out of scope in v0

Mutation, loops, objects, concurrency, network and GUI addresses, the `800` and
`900` native blocks, arbitrary-precision decimals, and self-hosting.
