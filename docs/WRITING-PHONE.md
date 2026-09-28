# Writing `.phone`

Everything you need to write a correct program. Self-contained on purpose: paste
the whole file into a model's context, or read it top to bottom yourself.

Regenerate the address table with `dial brief --write`. Print this whole file
with `dial brief`.

---

## 1. What a program is

A straight-line list of calls to numbered addresses. Each call takes arguments
and optionally binds its result to a name. There are no nested expressions —
every intermediate value has a name.

```phone
phonebook 0.1

500-0000001@["notes.txt"]  -> text     # READ_TEXT_FILE
200-0000001@[text]         -> lines    # SPLIT_LINES
300-0000009@[lines]        -> n        # COUNT
100-0000001@[n]                        # PRINT
```

Call syntax:

```
ADDRESS@[arg, arg, ...] -> name
ADDRESS@[arg, arg, ...]              # when the address returns nothing
```

- `# ` starts a comment, to end of line.
- The `phonebook 0.1` header goes first. It is optional but conventional.
- Literals: `"text"`, `42`, `-7`, `1.5`, `-2e3`, `true`, `false`. Escapes: `\n \t \r \\ \"`.
- Arguments may be named: `@[sequence=lines, predicate=000-0000001]`. The names
  must match the contract, in order.

## 2. The seven rules that matter

**1. Single assignment.** Every `-> name` binds exactly once. You cannot rebind
a name, and there are no variables to update.

```phone
200-0000005@[a] -> b       # fine
200-0000006@[b] -> b       # ERROR: 'b' is already bound
```

**2. Bind every result, or the call is an error.** If an address returns a
value, you must capture it. This catches typos rather than silently discarding
work.

```phone
200-0000005@["  x  "]           # ERROR: the result of TRIM is discarded
200-0000005@["  x  "] -> t      # fine
```

Addresses that return nothing (`PRINT`, `WRITE_TEXT_FILE`, `ASSERT`) must *not*
be bound.

**3. Define before use.** A name must be bound by an earlier line.

**4. There are no loops.** None. Iteration is only ever `MAP`, `FILTER`,
`REDUCE`, `SORT`, `SORT_BY`, `UNIQUE`. If you catch yourself wanting a `for`,
you want `MAP` or `REDUCE`.

**5. There are no lambdas.** A function argument is an *address*. In practice
that means you write a local extension and pass its number:

```phone
ext 000-0000001 NOT_BLANK (line: text) -> bool {
  200-0000005@[line]    -> trimmed
  600-0000007@[trimmed] -> blank
  600-0000001@[blank]   -> keep
  return keep
}

300-0000002@[lines, 000-0000001] -> kept    # FILTER
```

**6. There is no `if` statement.** `SELECT` (100-0000003) is an expression that
picks between two values you already have. Both are computed either way.

**7. Nothing mutates.** Every operation returns a new value.

## 3. Local extensions (the `000` block)

`000` is the local area code — extensions defined inside your file, invisible
outside it. They are the only place custom behavior can exist.

```
ext 000-000000N NAME (param: type, ...) -> type {
  ...calls, using the params as bound names...
  return name
}
```

- Number them `000-0000001`, `000-0000002`, … in your file. Any unused number
  works; they are file-local.
- Names must be `SCREAMING_SNAKE_CASE` and unique within the file.
- Exactly one `return`, and it must be the last statement.
- The body follows all the same rules — single assignment, no loops.
- An extension may call another extension, but **not recursively**.
- **Every extension must be used.** An unreferenced one is an error.

Extensions exist mostly to be passed to higher-order addresses. The arity has to
match what the address wants:

| Address | Wants | So write an ext taking |
|---|---|---|
| `FILTER` | `callable(T)->bool` | one param, returns `bool` |
| `MAP` | `callable(T)->R` | one param, returns anything |
| `SORT_BY` | `callable(T)->K` | one param, returns `int`/`bigint`/`float`/`decimal`/`text`/`bool` |
| `SORT_BY` | `callable(T)->K` | one param, returns `int`/`float`/`fraction`/`text`/`bool` |
| `REDUCE` | `callable(A,T)->A` | **two** params: accumulator first, item second |

You can also pass a registered address directly when its shape already fits —
but most useful ones take extra arguments (`GET` takes three), so an extension
is the normal answer.

## 4. Types

```
int   bigint   float   decimal   bool   text   unit
int   float   fraction   bool   text   unit
list<T>   map<K,V>   pair<K,V>   callable(T,...)->R   any
```

- `unit` means "returns nothing" — do not bind it.
- `pair<K,V>` comes from `ENTRIES`; take it apart with `PAIR_KEY` / `PAIR_VALUE`.
- `map<K,V>` comes from `READ_CSV` (one map per row) and `COUNT_OCCURRENCES`.
- Generic variables (`T`, `K`, `V`, `A`, `R`) are resolved from your arguments.
- Some addresses require a *comparable* or *keyable* type. Comparable is `int`,
  `bigint`, `float`, `decimal`, `text`, or `bool`; keyable is the same without
  `float` and `decimal`. You cannot sort a list of lists, and you cannot use a
  float or a decimal as a map key or in `EQUALS`.
  `float`, `fraction`, `text`, or `bool`; keyable is the same without `float`.
  You cannot sort a list of lists, and you cannot use a float as a map key or
  in `EQUALS`.
- **`int` and `float` never mix.** `ADD` is for ints and `ADD_FLOAT` for floats;
  write `2.0`, not `2`, where a float is wanted. Cross with `TO_FLOAT` and
  `TO_INT` (which truncates; use `ROUND` first for nearest).
- Floats are always finite. Dividing by zero is an error, not infinity.
- **`bigint` is for whole numbers too big for `int`** (past about 9.2e18), up
  to 4000 digits. Write it with an `n`: `12n`. It has its own addresses
  (`ADD_BIG`, `MUL_BIG`, `POW_BIG`, ...) and never mixes with `int`; cross with
  `TO_BIG` and `BIG_TO_INT`.
- **`decimal` is for exact amounts with a point**, such as money: `0.10d` plus
  `0.20d` is exactly `0.30`. Write it with a `d`: `19.99d`, `-0.05d`, `3d`. It
  keeps its places (`0.30`, not `0.3`) and has its own addresses (`ADD_DEC`,
  `MUL_DEC`, `ROUND_DEC`, ...). `DIV_DEC` and `ROUND_DEC` take the number of
  places to keep and round halves away from zero. Cross with `TO_DEC`,
  `BIG_TO_DEC`, `DEC_TO_INT`, `DEC_TO_FLOAT` and `FLOAT_TO_DEC`.
  For money, whole cents in an `int` are still the exact choice.
- **`fraction` is exact**: `1/3` stays `1/3`. There is no fraction literal;
  build one with `MAKE_FRACTION@[1, 3]` or `PARSE_FRACTION`. It is its own
  type, so use `ADD_FRACTION` rather than `ADD`, and leave it with
  `FRACTION_TO_FLOAT`, `FLOOR_FRACTION` or `ROUND_FRACTION`. It prints as
  `1/3`, or `2` when whole. Parts past 64 bits are an `overflow` error.

## 5. Patterns you will need

**Filter a list**

```phone
ext 000-0000001 IS_ERROR (line: text) -> bool {
  200-0000009@[line, "ERROR"] -> found      # CONTAINS
  return found
}
300-0000002@[lines, 000-0000001] -> errors
```

**Transform a list** — an ext wrapping an address that needs extra arguments

```phone
ext 000-0000002 AS_NUMBER (cell: text) -> int {
  400-0000009@[cell, 0] -> value            # PARSE_INT, 0 if unparseable
  return value
}
300-0000003@[cells, 000-0000002] -> numbers
```

**Pull a field out of a CSV row**

```phone
ext 000-0000003 NAME_OF (row: map<text,text>) -> text {
  300-0000014@[row, "name", "?"] -> name    # GET, "?" if absent
  return name
}
```

**Biggest / smallest** — sort, then take the first

```phone
ext 000-0000004 SIZE_OF (word: text) -> int {
  200-0000011@[word] -> n                   # LENGTH
  return n
}
300-0000006@[words, 000-0000004, true] -> longest_first   # SORT_BY descending
300-0000011@[longest_first, ""]        -> longest         # FIRST, "" if empty
```

**Total up a derived value** — `REDUCE` with a two-parameter extension

```phone
ext 000-0000005 ADD_LENGTH (running: int, word: text) -> int {
  200-0000011@[word]          -> n
  400-0000001@[running, n]    -> total      # ADD
  return total
}
300-0000004@[words, 000-0000005, 0] -> characters          # REDUCE, starts at 0
```

**Does anything match?** — there is no `ANY`; filter and count

```phone
300-0000002@[lines, 000-0000001] -> hits
300-0000009@[hits]               -> n
600-0000006@[n, 0]               -> found   # GREATER_THAN
100-0000001@[found]
```

**Build a string from parts**

```phone
300-0000001@[name, count_text] -> parts     # LIST is variadic, needs ≥1 item
200-0000004@[parts, ": "]      -> line      # JOIN
```

**Rank a tally** — the full `map` → `pair` → sorted-list route

```phone
ext 000-0000006 TALLY_OF (entry: pair<text,int>) -> int {
  300-0000016@[entry] -> n                  # PAIR_VALUE
  return n
}
300-0000012@[words]                      -> tallies   # COUNT_OCCURRENCES -> map
300-0000013@[tallies]                    -> pairs     # ENTRIES -> sorted by key
300-0000006@[pairs, 000-0000006, true]   -> ranked    # SORT_BY count, descending
300-0000010@[ranked, 5]                  -> top       # TAKE
```

## 6. Mistakes to avoid

| Mistake | What to do instead |
|---|---|
| Writing a loop | `MAP` / `FILTER` / `REDUCE` |
| Writing a lambda or inline predicate | define an `ext`, pass its address |
| Nesting calls: `300-0000009@[200-0000001@[t]]` | bind the inner result to a name first |
| Rebinding a name | pick a new name |
| Leaving a result unbound | bind it, or delete the call |
| Binding the result of `PRINT` | `PRINT` returns nothing |
| Using `IS_EMPTY` on a list | it takes `text`; use `COUNT` and compare to 0 |
| Expecting `PARSE_INT` to fail | it takes a fallback and always succeeds |
| Mixing `int` and `float` | convert with `TO_FLOAT` / `TO_INT` |
| Mixing `int` and `bigint` | convert with `TO_BIG` / `BIG_TO_INT`; write big literals as `12n` |
| Money as `float` | use `decimal`: write `19.99d`, add with `ADD_DEC`, round with `ROUND_DEC` |
| Writing `1/3` as a literal | `MAKE_FRACTION@[1, 3] -> third` |
| Comparing floats with `EQUALS` | not allowed; use `LESS_THAN` / `GREATER_THAN` |
| An `ext` you never call | delete it, or use it |
| Recursion | not allowed |
| Making up an address | check the table below; if it is not there, build it from what is |

## 7. Check your work

```bash
dial check  program.phone        # contracts, types, arity — no execution
dial run    program.phone        # execute it
dial run    program.phone --trace  # every call, with names resolved
dial search "what you want"      # find an address by description
dial show   300-0000002          # one address in full
```

`dial check` is fast and catches everything structural. Run it before anything
else.

---

## 8. Every address

Effects are shown in `[brackets]`. Lines beginning `!` are semantics pinned by
the contract — behavior you cannot guess from the signature, usually because two
backend languages would otherwise disagree. Read those.

<!-- BEGIN GENERATED ADDRESS TABLE -->

### 100 — Core

```
100-0000001  PRINT(value: any)  [stdout]
             Write a value to standard output followed by a newline
             ! The line terminator is a single U+000A, never CRLF, on every
               platform.
             ! Rendering follows TO_TEXT exactly, including 'true'/'false'
               for booleans.

100-0000002  PRINT_LINES(lines: list<text>)  [stdout]
             Write each item of a text list on its own line
             ! An empty list produces no output at all, not a blank line.

100-0000003  SELECT(condition: bool, when_true: T, when_false: T) -> T
             Choose between two values based on a condition
             ! EAGER: both arms are already-bound values, so both have been
               computed. There is no short-circuit and no lazy branch in v0.

100-0000004  IDENTITY(value: T) -> T
             Return the value unchanged

100-0000005  TO_TEXT(value: any) -> text
             Render any value as text
             ! bool renders as 'true' or 'false' (lowercase) in every
               backend. Python's native 'True' is explicitly NOT the
               contract.
             ! int renders in base 10 with a leading '-' for negatives.
             ! text renders as itself, unquoted.
             ! list renders as '[a, b, c]' with each element rendered by this
               same rule.
             ! pair renders as '(k, v)'.
             ! float renders as the shortest decimal digit string that reads
               back as the same float. If several strings of that length do,
               it is the closest to the float's exact value, and if two are
               equally close, the one whose last digit is even:
               635057293855503.25 renders as '635057293855503.2'. With those
               digits d1 d2 ... dn and exponent E, so that the value is
               d1.d2...dn x 10^E: when -4 <= E < 16 it is written
               positionally with at least one digit after the point ('1.0',
               '0.0001', '123.45'); otherwise as d1, then '.' and the
               remaining digits if any, then 'e', a sign, and at least two
               exponent digits ('1e+16', '1.5e-05').
             ! That is exactly Python's repr() for a finite float, and NOT
               Rust's Display, which writes 1e16 as '10000000000000000' and
               1.0 as '1'. There is no '-0.0', 'nan' or 'inf' to render:
               floats are finite and zero has one sign.
             ! bigint renders exactly as int does: base 10 with a leading '-'
               for negatives, and no suffix, so 12n renders as '12'.
             ! decimal renders every digit it has, with the point as many
               digits from the right as its places and at least one digit
               before it, and no suffix: 0.30d renders as '0.30', -0.05d as
               '-0.05', and 12d as '12'. Never an exponent, and never '-0'.
             ! fraction renders in lowest terms as numerator, '/',
               denominator, with any '-' on the numerator: '1/3', '-5/2'. A
               whole fraction renders as its numerator alone: 4/2 renders as
               '2'.

100-0000006  ASSERT(condition: bool, message: text)
             Fail with a message unless a condition holds
             ! The failure message is written to standard error, not standard
               output, so it never pollutes a program's comparable output.
             errors: assertion_failed
```

### 200 — Text

```
200-0000001  SPLIT_LINES(value: text) -> list<text>
             Split text into lines
             ! Splits on U+000A. A CR immediately preceding the LF is
               removed, so CRLF and LF files produce identical results.
             ! Exactly one trailing newline is absorbed: 'a
b
' yields
               ['a','b'], while 'a
b

' yields ['a','b',''].
             ! Empty input yields an empty list, not [''].

200-0000002  SPLIT(value: text, separator: text) -> list<text>
             Split text on a separator
             ! An empty separator is an error, not a character-wise split.
             ! Splitting '' on any separator yields [''].
             errors: empty_separator

200-0000003  SPLIT_WORDS(value: text) -> list<text>
             Split text into whitespace-separated words
             ! Whitespace is space, tab, line feed, carriage return, form
               feed, and vertical tab. Unicode-only spaces are NOT separators
               in contract v1.
             ! Whitespace-only input yields an empty list.

200-0000004  JOIN(parts: list<text>, separator: text) -> text
             Concatenate a list of text with a separator
             ! An empty list joins to empty text. A one-element list joins to
               that element.

200-0000005  TRIM(value: text) -> text
             Remove leading and trailing whitespace
             ! Trims the same whitespace set as SPLIT_WORDS: space, tab, LF,
               CR, FF, VT.

200-0000006  LOWERCASE(value: text) -> text
             Lowercase ASCII letters, leaving all other characters untouched
             ! ASCII ONLY. 'Ä' stays 'Ä' and 'İ' stays 'İ' in contract v1.
             ! A full-Unicode variant would be a new contract version, not a
               change to this one.

200-0000007  UPPERCASE(value: text) -> text
             Uppercase ASCII letters, leaving all other characters untouched
             ! ASCII ONLY, mirroring LOWERCASE (200-0000006). 'ß' does not
               become 'SS'.

200-0000008  REPLACE(value: text, find: text, replace_with: text) -> text
             Replace every occurrence of one substring with another
             ! Matches are non-overlapping and taken left to right;
               replacements are never rescanned.
             ! An empty 'find' is an error rather than an insertion between
               every character.
             errors: empty_find

200-0000009  CONTAINS(haystack: text, needle: text) -> bool
             Report whether text contains a substring
             ! Every text contains the empty string.

200-0000010  STARTS_WITH(value: text, prefix: text) -> bool
             Report whether text begins with a prefix

200-0000011  LENGTH(value: text) -> int
             Count the characters in text
             ! Unicode scalar values. 'é' as a single code point is 1; as 'e'
               plus a combining accent it is 2.

200-0000012  SLICE(value: text, start: int, end: int) -> text
             Extract a character range from text
             ! Character indices, matching LENGTH (200-0000011).
             ! Bounds are clamped to [0, LENGTH]; negative indices clamp to 0
               and do NOT count from the end.
             ! If end <= start the result is empty text. Out-of-range is
               never an error.
```

### 300 — Collections

```
300-0000001  LIST(items: T...) -> list<T>
             Build a list from the given values
             ! Variadic. All items must unify to a single element type.
             ! At least one item is required in v0: with no items there is
               nothing to infer the element type from.

300-0000002  FILTER(sequence: list<T>, predicate: callable(T)->bool) -> list<T>
             Retain values satisfying a predicate
             ! Relative order of kept elements is preserved.
             ! The predicate is applied to every element exactly once, left
               to right.
             errors: predicate_failure

300-0000003  MAP(sequence: list<T>, transform: callable(T)->R) -> list<R>
             Transform every value in a list
             ! Applied left to right, exactly once per element. Length is
               preserved.
             errors: transform_failure

300-0000004  REDUCE(sequence: list<T>, combine: callable(A,T)->A, initial: A) -> A
             Fold a list into a single value from the left
             ! LEFT fold, always. An empty list returns the initial value
               untouched.
             errors: combine_failure

300-0000005  SORT(sequence: list<T>) -> list<T>
             Sort a list into ascending order
             ! STABLE.
             ! int sorts numerically; text sorts by Unicode scalar value,
               which is not locale-aware and is identical in every backend.
             ! bool sorts false before true.
             ! float sorts numerically. Every float is finite and there is no
               negative zero, so the order is total.
             ! bigint sorts numerically.
             ! decimal sorts numerically, by value: 0.3 and 0.30 are equal,
               so they keep their original order.
             ! fraction sorts numerically by exact value: 1/3 before 1/2.

300-0000006  SORT_BY(sequence: list<T>, key: callable(T)->K, descending: bool) -> list<T>
             Sort a list by a derived key
             ! STABLE in both directions: elements with equal keys keep their
               original relative order even when descending is true.
             ! Descending sorts by reversed key comparison, NOT by reversing
               the sorted list, which would break stability.
             errors: key_failure

300-0000007  REVERSE(sequence: list<T>) -> list<T>
             Reverse the order of a list

300-0000008  UNIQUE(sequence: list<T>) -> list<T>
             Remove duplicate values, keeping the first of each
             ! FIRST-OCCURRENCE order is preserved. This is not a sorted set
               and does not reorder anything.

300-0000009  COUNT(sequence: list<T>) -> int
             Count the items in a list

300-0000010  TAKE(sequence: list<T>, n: int) -> list<T>
             Keep the first n items of a list
             ! n is clamped: larger than the list returns the whole list,
               negative returns an empty list. Never an error.

300-0000011  FIRST(sequence: list<T>, fallback: T) -> T
             Take the first item, or a fallback when the list is empty
             ! Never fails. An empty list returns the fallback.

300-0000012  COUNT_OCCURRENCES(sequence: list<T>) -> map<T,int>
             Tally how many times each value appears
             ! The result is a map, which has no inherent order. Use ENTRIES
               (300-0000013) to get a deterministically ordered view.

300-0000013  ENTRIES(mapping: map<K,V>) -> list<pair<K,V>>
             List a map's key/value pairs, sorted by key
             ! SORTED BY KEY, ascending, always.
             ! Python dicts iterate in insertion order and Rust BTreeMaps
               iterate in key order. Sorting here is what removes that
               difference from every program's output.

300-0000014  GET(mapping: map<K,V>, key: K, fallback: V) -> V
             Look up a key in a map, or a fallback when absent
             ! Never fails. A missing key returns the fallback.

300-0000015  PAIR_KEY(value: pair<K,V>) -> K
             Take the key half of a pair

300-0000016  PAIR_VALUE(value: pair<K,V>) -> V
             Take the value half of a pair
```

### 400 — Numbers

```
400-0000001  ADD(a: int, b: int) -> int
             Add two integers
             ! Integers are 64-bit signed. Overflow is an error, not a wrap
               and not a promotion to arbitrary precision.
             errors: overflow

400-0000002  SUB(a: int, b: int) -> int
             Subtract the second integer from the first
             errors: overflow

400-0000003  MUL(a: int, b: int) -> int
             Multiply two integers
             errors: overflow

400-0000004  DIV(a: int, b: int) -> int
             Divide two integers, truncating toward zero
             ! TRUNCATES TOWARD ZERO: -7 / 2 is -3, not -4.
             ! A Python backend must NOT use // here. This is the clearest
               example in the registry of a contract overriding a host
               language's default.
             errors: division_by_zero, overflow

400-0000005  MOD(a: int, b: int) -> int
             Remainder of integer division, taking the sign of the dividend
             ! SIGN OF THE DIVIDEND: -7 mod 2 is -1, not 1.
             ! Consistent with DIV (400-0000004) so that a == DIV(a,b)*b +
               MOD(a,b).
             errors: division_by_zero

400-0000006  MIN(a: int, b: int) -> int
             The smaller of two integers

400-0000007  MAX(a: int, b: int) -> int
             The larger of two integers

400-0000008  SUM(values: list<int>) -> int
             Add up a list of integers
             ! An empty list sums to 0.
             ! Summed left to right.
             errors: overflow

400-0000009  PARSE_INT(value: text, fallback: int) -> int
             Read an integer from text, or a fallback when it is not one
             ! Never fails; unparseable text returns the fallback.
             ! Accepts optional leading '-' or '+' then ASCII digits, with
               surrounding whitespace trimmed first. Underscores, other digit
               systems, and other bases are rejected.

400-0000010  ABS(a: int) -> int
             The distance of an integer from zero
             ! The absolute value of the smallest 64-bit integer does not
               fit, so ABS(-9223372036854775808) is an overflow error.
               Python's abs would quietly return a bigger number; Rust's abs
               would panic or wrap by build profile.
             errors: overflow

400-0000011  NEGATE(a: int) -> int
             Flip the sign of an integer
             ! NEGATE(-9223372036854775808) is an overflow error, for the
               same reason as ABS (400-0000010).
             ! NEGATE(0) is 0; there is no negative zero.
             errors: overflow

400-0000012  POW(base: int, exponent: int) -> int
             Raise an integer to a whole-number power
             ! POW(x, 0) is 1 for every x, including POW(0, 0).
             ! A negative exponent is an error, not a fraction: v0 has no
               floating point.
             ! Overflow is an error whenever the true result does not fit in
               64 bits. POW(-2, 63) is -9223372036854775808 and fits; POW(2,
               63) does not.
             ! A backend must not raise overflow for a result that fits, and
               must not build a huge intermediate before noticing one that
               does not.
             errors: negative_exponent, overflow

400-0000013  CLAMP(value: int, low: int, high: int) -> int
             Hold an integer inside a range, both ends included
             ! Arguments are value, low, high, in that order.
             ! Both ends are included: CLAMP(value, low, high) is low when
               value < low, high when value > high, and value otherwise.
             ! low greater than high is an invalid_range error. low equal to
               high is allowed and always returns that number. Rust's clamp
               would panic here; Python has no clamp.
             errors: invalid_range

400-0000014  SIGN(a: int) -> int
             Whether an integer is negative, zero, or positive
             ! Returns exactly -1, 0, or 1. Never fails.

400-0000015  ADD_FLOAT(a: float, b: float) -> float
             Add two floats
             ! float is IEEE 754 binary64. The result is the exact sum
               rounded to nearest, ties to even, which every backend gets
               from its hardware.
             ! FINITE ONLY: a result too large to be finite is an overflow
               error. NaN and infinity never exist as values.
             ! NO NEGATIVE ZERO: a result of -0.0 is 0.0.
             errors: overflow

400-0000016  SUB_FLOAT(a: float, b: float) -> float
             Subtract the second float from the first
             ! Rounded to nearest, ties to even. A result too large to be
               finite is an overflow error.
             ! NO NEGATIVE ZERO: 0.0 - 0.0 is 0.0, and so is any other
               difference that would be -0.0.
             errors: overflow

400-0000017  MUL_FLOAT(a: float, b: float) -> float
             Multiply two floats
             ! Rounded to nearest, ties to even. A result too large to be
               finite is an overflow error; a result too small to represent
               is 0.0.
             ! NO NEGATIVE ZERO: -2.0 * 0.0 is 0.0.
             errors: overflow

400-0000018  DIV_FLOAT(a: float, b: float) -> float
             Divide one float by another
             ! Rounded to nearest, ties to even.
             ! DIVIDING BY ZERO IS AN ERROR, including 0.0 / 0.0. IEEE 754
               would give infinity or NaN; this contract never produces
               either.
             ! A quotient too large to be finite is an overflow error. One
               too small to represent is 0.0, never -0.0.
             errors: division_by_zero, overflow

400-0000019  TO_FLOAT(value: int) -> float
             Convert an integer to a float
             ! Exact for every integer whose magnitude is at most 2^53.
               Larger integers round to the nearest float, ties to even:
               9007199254740993 becomes 9007199254740992.0.

400-0000020  TO_INT(value: float) -> int
             Convert a float to an integer, truncating toward zero
             ! TRUNCATES TOWARD ZERO: 2.9 is 2 and -2.9 is -2.
             ! A value whose truncation does not fit a 64-bit signed integer
               is an overflow error. It never saturates, which is what Rust's
               `as i64` would do.
             errors: overflow

400-0000021  ROUND(value: float) -> float
             Round a float to the nearest whole number, halves away from zero
             ! HALVES AWAY FROM ZERO: 2.5 is 3.0 and -2.5 is -3.0. A Python
               backend must NOT use round(), which would give 2.
             ! Decided on the exact binary value, never on its printed
               digits: 0.49999999999999994 is 0.0, because it is below one
               half.
             ! The result is a float. Use TO_INT (400-0000020) to get an int.
               NO NEGATIVE ZERO: -0.4 rounds to 0.0.

400-0000022  PARSE_FLOAT(value: text, fallback: float) -> float
             Read a float from text, or a fallback when it is not one
             ! Never fails; unparseable text returns the fallback.
             ! Accepts, after trimming surrounding whitespace: an optional
               '+' or '-', one or more ASCII digits, optionally '.' and one
               or more digits, optionally 'e' or 'E', an optional sign, and
               one or more digits. So '3', '-0.5' and '1.5e3' parse; '.5',
               '5.', '1_000', 'nan', 'inf' and 'infinity' do not.
             ! The decimal value is rounded to the nearest float, ties to
               even, however many digits it has.
             ! A value too large to be finite returns the fallback. A value
               too small to represent is 0.0. '-0' is 0.0.

400-0000023  TO_BIG(value: int) -> bigint
             Widen an int to a bigint
             ! Every int is a bigint, so this never fails and never changes
               the value.
             ! int and bigint never mix: ADD takes two ints and ADD_BIG takes
               two bigints. This is how an int crosses over.

400-0000024  BIG_TO_INT(value: bigint) -> int
             Narrow a bigint to an int
             ! A value outside the 64-bit signed range is an overflow error.
               It never wraps or saturates.
             errors: overflow

400-0000025  ADD_BIG(a: bigint, b: bigint) -> bigint
             Add two bigints
             ! bigint is an exact whole number of up to 4000 decimal digits.
               There is no rounding and no wrapping.
             ! A result with more than 4000 decimal digits is an overflow
               error. Every bigint address that can grow checks this, so
               Python and Rust fail at exactly the same place.
             errors: overflow

400-0000026  SUB_BIG(a: bigint, b: bigint) -> bigint
             Subtract the second bigint from the first
             ! A result with more than 4000 decimal digits is an overflow
               error. Every bigint address that can grow checks this, so
               Python and Rust fail at exactly the same place.
             ! Zero has one sign: 5 - 5 is 0, never -0.
             errors: overflow

400-0000027  MUL_BIG(a: bigint, b: bigint) -> bigint
             Multiply two bigints
             ! A result with more than 4000 decimal digits is an overflow
               error. Every bigint address that can grow checks this, so
               Python and Rust fail at exactly the same place.
             errors: overflow

400-0000028  DIV_BIG(a: bigint, b: bigint) -> bigint
             Divide one bigint by another, truncating toward zero
             ! TRUNCATES TOWARD ZERO, exactly as DIV (400-0000004) does: -7 /
               2 is -3, not -4. A Python backend must NOT use //.
             ! The quotient is never larger than the dividend, so this cannot
               overflow.
             errors: division_by_zero

400-0000029  MOD_BIG(a: bigint, b: bigint) -> bigint
             Remainder of dividing one bigint by another
             ! SIGN OF THE DIVIDEND, exactly as MOD (400-0000005) does: -7
               mod 2 is -1, not 1. A Python backend must NOT use %.
             ! Consistent with DIV_BIG (400-0000028) so that a ==
               DIV_BIG(a,b)*b + MOD_BIG(a,b).
             errors: division_by_zero

400-0000030  POW_BIG(base: bigint, exponent: int) -> bigint
             Raise a bigint to a whole-number power
             ! POW_BIG(x, 0) is 1 for every x, including POW_BIG(0, 0).
             ! A negative exponent is an error, not a fraction.
             ! Overflow is an error exactly when the true result has more
               than 4000 decimal digits. POW_BIG(10, 3999) fits; POW_BIG(10,
               4000) does not.
             ! A backend must not build an intermediate of more than 8000
               digits before noticing an overflow: the exponent is an int,
               and 2 to the power 2^62 would never finish.
             errors: negative_exponent, overflow

400-0000031  PARSE_BIG(value: text, fallback: bigint) -> bigint
             Read a bigint from text, with a fallback
             ! Never fails; unparseable text returns the fallback.
             ! The same grammar as PARSE_INT (400-0000009): optional leading
               '-' or '+' then ASCII digits, with surrounding whitespace
               trimmed first. Underscores, other digit systems, and other
               bases are rejected.
             ! Leading zeros do not count toward the 4000-digit ceiling. More
               than 4000 digits after them returns the fallback.

400-0000032  GCD(a: int, b: int) -> int
             The greatest common divisor of two integers
             ! The result is never negative: GCD(-12, 18) is 6. Signs of the
               inputs do not matter.
             ! GCD(a, 0) is the absolute value of a, and GCD(0, 0) is 0.
             ! When the true answer is 9223372036854775808 it does not fit,
               so it is an overflow error. That happens only when one input
               is the smallest 64-bit integer and the other is 0 or that same
               number. Python's math.gcd would return the bigger number;
               Rust's unsigned_abs would hold it but not convert back.
             errors: overflow

400-0000033  LCM(a: int, b: int) -> int
             The least common multiple of two integers
             ! The result is never negative: LCM(-4, 6) is 12. Signs of the
               inputs do not matter.
             ! LCM(a, 0) is 0 for every a, including LCM(0, 0).
             ! Overflow is an error whenever the true answer does not fit in
               64 bits. A backend must divide by the GCD before multiplying,
               so it never builds a product bigger than the answer.
             errors: overflow

400-0000034  PRODUCT(values: list<int>) -> int
             Multiply together a list of integers
             ! An empty list multiplies to 1.
             ! Multiplied left to right, like SUM (400-0000008). Overflow is
               an error the moment a running product does not fit, even when
               a later 0 would have brought the answer back:
               PRODUCT([9223372036854775807, 2, 0]) is an overflow error, not
               0.
             errors: overflow

400-0000035  IS_EVEN(a: int) -> bool
             Whether an integer is even
             ! Negative numbers follow the same rule: -4 is even and -3 is
               not. Zero is even.
             ! Never fails, including on the smallest 64-bit integer, which
               is even.

400-0000036  IS_ODD(a: int) -> bool
             Whether an integer is odd
             ! Negative numbers follow the same rule: -3 is odd. A backend
               must not test the remainder against 1, because Rust's -3 % 2
               is -1.
             ! Always the opposite of IS_EVEN (400-0000035). Never fails.

400-0000040  TO_DEC(value: int) -> decimal
             Widen an int to a decimal
             ! The result has no places: 12 becomes 12, not 12.0. ROUND_DEC
               (400-0000047) gives it places.
             ! Never fails and never changes the value.
             ! int and decimal never mix: ADD takes two ints and ADD_DEC
               takes two decimals. This is how an int crosses over.

400-0000041  BIG_TO_DEC(value: bigint) -> decimal
             Widen a bigint to a decimal
             ! The result has no places. Never fails: a bigint has at most
               4000 digits, and so may a decimal.

400-0000042  DEC_TO_INT(value: decimal) -> int
             Drop a decimal's fractional part to get an int
             ! TRUNCATES TOWARD ZERO, as TO_INT (400-0000020) does: 2.9 is 2
               and -2.9 is -2. Use ROUND_DEC with 0 places first for nearest.
             ! A value whose truncation does not fit a 64-bit signed integer
               is an overflow error. It never wraps or saturates.
             errors: overflow

400-0000043  ADD_DEC(a: decimal, b: decimal) -> decimal
             Add two decimals exactly
             ! decimal is an exact base-10 number: a whole-number coefficient
               and a scale, the count of digits after the point. 0.10 + 0.20
               is exactly 0.30.
             ! The result's scale is the larger of the two: 1.5 + 0.25 is
               1.75, and 0.10 + 0.20 is 0.30, never 0.3.
             ! A result with more than 4000 digits, or more than 1000 of them
               after the point, is an overflow error. Every decimal address
               that can grow checks this.
             errors: overflow

400-0000044  SUB_DEC(a: decimal, b: decimal) -> decimal
             Subtract the second decimal from the first, exactly
             ! The result's scale is the larger of the two: 1 - 0.01 is 0.99.
             ! A result with more than 4000 digits, or more than 1000 of them
               after the point, is an overflow error.
             ! Zero has one sign: 0.5 - 0.5 is 0.0, never -0.0.
             errors: overflow

400-0000045  MUL_DEC(a: decimal, b: decimal) -> decimal
             Multiply two decimals exactly
             ! EXACT: nothing is rounded. The scales add, so 1.5 x 0.25 is
               0.375 and 19.99 x 3 is 59.97. Use ROUND_DEC (400-0000047) to
               get back to a number of places.
             ! A result with more than 4000 digits, or more than 1000 of them
               after the point, is an overflow error.
             errors: overflow

400-0000046  DIV_DEC(a: decimal, b: decimal, places: int) -> decimal
             Divide two decimals, rounded to a number of places
             ! The exact quotient a / b, rounded ONCE to exactly `places`
               digits after the point. HALVES AWAY FROM ZERO: 1 / 8 to 2
               places is 0.13, and -1 / 8 is -0.13.
             ! The result always has `places` places, even when the quotient
               is exact: 1 / 4 to 3 places is 0.250.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error. A zero divisor is a division_by_zero
               error.
             ! A result with more than 4000 digits is an overflow error.
             errors: division_by_zero, invalid_places, overflow

400-0000047  ROUND_DEC(value: decimal, places: int) -> decimal
             Round a decimal to a number of places, halves away from zero
             ! The result has exactly `places` digits after the point. HALVES
               AWAY FROM ZERO: 2.345 to 2 places is 2.35, -2.345 is -2.35,
               and 2.5 to 0 places is 3.
             ! More places than the value has pads with zeros, exactly: 5 to
               2 places is 5.00.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error.
             ! Rounding can add a digit (9.99 to 1 place is 10.0), so a
               result with more than 4000 digits is an overflow error.
             ! NO NEGATIVE ZERO: -0.004 to 2 places is 0.00.
             errors: invalid_places, overflow

400-0000048  PARSE_DEC(value: text, fallback: decimal) -> decimal
             Read a decimal from text, with a fallback
             ! Never fails; unparseable text returns the fallback.
             ! Grammar: optional leading '-' or '+', ASCII digits, then
               optionally '.' and more ASCII digits, with surrounding
               whitespace trimmed first. '.5', '5.', exponents, underscores
               and thousands separators are rejected.
             ! The places are kept as written: '1.50' is 1.50, not 1.5.
             ! Leading zeros do not count toward the 4000-digit ceiling. More
               than 4000 digits after them, or more than 1000 after the
               point, returns the fallback.

400-0000049  DEC_TO_FLOAT(value: decimal) -> float
             Convert a decimal to the nearest float
             ! The float nearest the decimal's exact value, ties to even, the
               way PARSE_FLOAT reads its digits. 0.1 becomes the float that
               prints as 0.1.
             ! A value too large to be a finite float is an overflow error. A
               value too small becomes 0.0, never -0.0.
             errors: overflow

400-0000050  FLOAT_TO_DEC(value: float) -> decimal
             Convert a float to the decimal it prints as
             ! The result is the float's SHORTEST DIGITS, the ones TO_TEXT
               prints, never its exact binary value: 0.1 becomes 0.1, not
               0.1000000000000000055511151231257827021181583404541015625.
             ! With those digits d1...dn and exponent E, the result is
               d1...dn x 10^(E-n+1), with no places when that power is not
               negative: 2.5 is 2.5, 100.0 is 100, and 1e+16 is
               10000000000000000.
             ! Never fails: a float has at most 17 significant digits and E
               is between -324 and 308, inside both decimal ceilings.

400-0000060  NUMBER_EQUALS(a: T, b: T) -> bool
             True when two numbers of the same type are equal
             ! Both arguments have the same type: an int is never compared
               with a float. Works for int, bigint, float, decimal and
               fraction.
             ! Decimals are equal by value, so 0.3 equals 0.30. Fractions are
               always in lowest terms, so 2/4 equals 1/2.
             ! EXACT. For floats this is equality of the binary value, so 0.1
               + 0.2 does not equal 0.3. Use CLOSE_TO (400-0000065) for
               computed floats.
             ! There is one zero and no NaN, so every float equals itself and
               nothing else is equal to it.

400-0000061  NUMBER_NOT_EQUALS(a: T, b: T) -> bool
             True when two numbers of the same type are different
             ! Exactly the opposite of NUMBER_EQUALS (400-0000060), with the
               same exactness for floats.
             ! Works for int, bigint, float, decimal and fraction; decimals
               compare by value, so 0.3 and 0.30 are equal.

400-0000062  LESS_OR_EQUAL(a: T, b: T) -> bool
             True when the first number is less than or equal to the second
             ! Numeric order, the same order as LESS_THAN (600-0000005). Both
               arguments have the same type.
             ! True exactly when LESS_THAN(a, b) or NUMBER_EQUALS(a, b) is
               true.
             ! Works for int, bigint, float, decimal and fraction; decimals
               compare by value, so 0.3 and 0.30 are equal.

400-0000063  GREATER_OR_EQUAL(a: T, b: T) -> bool
             True when the first number is greater than or equal to the second
             ! Numeric order, the same order as GREATER_THAN (600-0000006).
               Both arguments have the same type.
             ! True exactly when GREATER_THAN(a, b) or NUMBER_EQUALS(a, b) is
               true.
             ! Works for int, bigint, float, decimal and fraction; decimals
               compare by value, so 0.3 and 0.30 are equal.

400-0000064  COMPARE(a: T, b: T) -> int
             Compare two numbers: -1 if the first is smaller, 0 if equal, 1 if larger
             ! Returns exactly -1, 0, or 1, never another negative or
               positive number. Never fails.
             ! Numeric order, the same order as LESS_THAN (600-0000005). 0
               means NUMBER_EQUALS (400-0000060) is true.
             ! Python has no cmp() and Rust's cmp returns an Ordering, not a
               number; the contract picks the integers.
             ! Works for int, bigint, float, decimal and fraction; decimals
               compare by value, so 0.3 and 0.30 are equal.

400-0000065  CLOSE_TO(a: float, b: float, tolerance: float) -> bool
             True when two floats are within a tolerance of each other
             ! ABSOLUTE tolerance: true when |a - b| <= tolerance, with a - b
               rounded to the nearest float. Not Python's math.isclose, which
               is relative by default.
             ! The tolerance is included, so a tolerance of 0.0 is exact
               equality.
             ! A negative tolerance is never met: the result is false. Never
               fails.
             ! When a - b is too large to be finite the two are not close:
               the result is false, not an overflow error.

400-0000080  MAKE_FRACTION(numerator: int, denominator: int) -> fraction
             Build an exact fraction from a numerator and a denominator
             ! EVERY FRACTION IS KEPT IN LOWEST TERMS WITH A POSITIVE
               DENOMINATOR. 2/4 becomes 1/2, 3/-6 becomes -1/2, and 0/5
               becomes 0/1, so each value has exactly one form.
             ! A zero denominator is a division_by_zero error.
             ! The numerator and denominator of the lowest-terms form must
               each fit in a 64-bit signed integer, or it is an overflow
               error: -9223372036854775808 / -1 overflows.
             ! This applies to every fraction address: the working is exact,
               and only the lowest-terms result has to fit.
             errors: division_by_zero, overflow

400-0000081  ADD_FRACTION(a: fraction, b: fraction) -> fraction
             Add two fractions exactly
             ! Exact: 1/10 + 2/10 is 3/10. The result is in lowest terms and
               is an overflow error if that does not fit in 64 bits, as
               MAKE_FRACTION (400-0000080) says.
             errors: overflow

400-0000082  SUB_FRACTION(a: fraction, b: fraction) -> fraction
             Subtract one fraction from another exactly
             ! a - b, exact. The result is in lowest terms and is an overflow
               error if that does not fit in 64 bits, as MAKE_FRACTION
               (400-0000080) says.
             errors: overflow

400-0000083  MUL_FRACTION(a: fraction, b: fraction) -> fraction
             Multiply two fractions exactly
             ! Exact. The result is in lowest terms and is an overflow error
               if that does not fit in 64 bits, as MAKE_FRACTION
               (400-0000080) says.
             errors: overflow

400-0000084  DIV_FRACTION(a: fraction, b: fraction) -> fraction
             Divide one fraction by another exactly
             ! a / b, exact: nothing is truncated or rounded. 1/1 divided by
               3/1 is 1/3.
             ! Dividing by a zero fraction is a division_by_zero error.
             ! The result is in lowest terms and is an overflow error if that
               does not fit in 64 bits, as MAKE_FRACTION (400-0000080) says.
             errors: division_by_zero, overflow

400-0000085  NEGATE_FRACTION(a: fraction) -> fraction
             Flip the sign of a fraction
             ! A fraction whose numerator is -9223372036854775808 has no
               positive twin in 64 bits, so negating it is an overflow error,
               as NEGATE (400-0000011) is for int.
             errors: overflow

400-0000086  ABS_FRACTION(a: fraction) -> fraction
             The distance of a fraction from zero
             ! A fraction whose numerator is -9223372036854775808 has no
               positive twin in 64 bits, so its absolute value is an overflow
               error, as ABS (400-0000010) is for int.
             errors: overflow

400-0000087  NUMERATOR(a: fraction) -> int
             The top number of a fraction in lowest terms
             ! Of the lowest-terms form, and it carries the sign: the
               numerator of MAKE_FRACTION(2, -4) is -1.

400-0000088  DENOMINATOR(a: fraction) -> int
             The bottom number of a fraction in lowest terms
             ! Of the lowest-terms form, so it is always at least 1: the
               denominator of MAKE_FRACTION(2, -4) is 2, and of a whole
               number it is 1.

400-0000089  FRACTION_TO_FLOAT(a: fraction) -> float
             The float nearest to a fraction
             ! The exact value numerator / denominator, rounded once to the
               nearest float, ties to even. NOT float(numerator) /
               float(denominator), which rounds up to three times and can be
               one step off when either part is past 2^53.
             ! Never fails: every fraction is between -2^63 and 2^63, so the
               float is finite. Zero is 0.0, never -0.0.

400-0000090  FLOOR_FRACTION(a: fraction) -> int
             The largest whole number not above a fraction
             ! ROUNDS TOWARD NEGATIVE INFINITY, not toward zero: 7/2 gives 3
               and -7/2 gives -4. That is Python's //, and NOT Rust's /,
               which truncates. Never fails: the result is never further from
               zero than the numerator.

400-0000091  ROUND_FRACTION(a: fraction) -> int
             Round a fraction to the nearest whole number
             ! HALVES GO AWAY FROM ZERO, as in ROUND (400-0000021): 5/2 gives
               3 and -5/2 gives -3. Python's round() would give 2 and -2.
               Never fails: the result is never further from zero than the
               numerator.

400-0000092  PARSE_FRACTION(value: text, fallback: fraction) -> fraction
             Read a fraction from text, or a fallback when it is not one
             ! Never fails; unparseable text returns the fallback.
             ! Accepts, after trimming surrounding whitespace: an optional
               '+' or '-', one or more ASCII digits, and optionally '/'
               followed by one or more ASCII digits. So '3', '-1/3' and '2/4'
               parse; '1 / 3', '1/-3', '1.5', '/3' and '1/' do not.
             ! The numerator as written and the denominator as written must
               each fit in a 64-bit signed integer, and the denominator must
               not be zero; otherwise the fallback is returned.
             ! The result is in lowest terms: '2/4' reads as 1/2. Whatever
               TO_TEXT (100-0000005) prints for a fraction reads back as the
               same fraction.

400-0000100  DEC_TO_BIG(value: decimal) -> bigint
             Drop a decimal's fractional part to get a bigint
             ! TRUNCATES TOWARD ZERO, as DEC_TO_INT (400-0000042) does: 2.9
               is 2 and -2.9 is -2. Use ROUND_DEC with 0 places first for
               nearest.
             ! Never fails: a decimal has at most 4000 digits, and so may a
               bigint.

400-0000101  BIG_TO_FLOAT(value: bigint) -> float
             Convert a bigint to the nearest float
             ! The float nearest the bigint's exact value, ties to even, the
               way PARSE_FLOAT reads its digits. Past 2^53 not every whole
               number is a float, so 2^53 + 1 becomes 2^53.
             ! A value too large to be a finite float is an overflow error.
             errors: overflow

400-0000102  FLOAT_TO_BIG(value: float) -> bigint
             Drop a float's fractional part to get a bigint
             ! TRUNCATES TOWARD ZERO, as TO_INT (400-0000020) does: 2.9 is 2
               and -2.9 is -2. Use ROUND first for nearest.
             ! The float's EXACT binary value, not its printed digits: 1e23
               is 99999999999999991611392, because that is the float 1e23
               really is. FLOAT_TO_DEC (400-0000050) is the one that keeps
               the printed digits.
             ! Never fails: the largest float has 309 digits, well under the
               bigint ceiling.

400-0000103  DEC_TO_FRACTION(value: decimal) -> fraction
             Turn a decimal into the exact same fraction
             ! EXACT, in lowest terms: 0.75 is 3/4, 2.50 is 5/2, and -0.10 is
               -1/10.
             ! When the reduced numerator or denominator does not fit in 64
               bits, the result is an overflow error. It never rounds to make
               it fit.
             errors: overflow

400-0000104  FRACTION_TO_DEC(value: fraction, places: int) -> decimal
             Turn a fraction into a decimal, rounded to a number of places
             ! The exact value numerator / denominator, rounded ONCE to
               exactly `places` digits after the point. HALVES AWAY FROM
               ZERO: 1/8 to 2 places is 0.13, and -1/8 is -0.13.
             ! The result always has `places` places, even when the fraction
               is exact: 1/4 to 3 places is 0.250.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error. Otherwise it never fails.
             errors: invalid_places

400-0000105  BIG_TO_FRACTION(value: bigint) -> fraction
             Turn a bigint into a whole-number fraction
             ! The value over 1: 7 becomes 7, which prints as 7.
             ! A fraction's parts are 64-bit, so a bigint that does not fit a
               64-bit signed integer is an overflow error.
             errors: overflow

400-0000120  FORMAT_FLOAT(value: float, places: int) -> text
             Print a float with a set number of places, like 3.14
             ! ROUNDS THE PRINTED DIGITS, not the binary value: the float's
               shortest digits, exactly what TO_TEXT (100-0000005) and
               FLOAT_TO_DEC (400-0000050) give, are rounded to `places`.
               2.675 to 2 places is 2.68. A Python backend must NOT use
               format() or an f-string, and a Rust backend must NOT use
               {:.N}.
             ! HALVES AWAY FROM ZERO, as ROUND_DEC (400-0000047): 0.125 to 2
               places is 0.13 and -0.125 is -0.13. 2.5 to 0 places is 3. More
               places than the float has pads with zeros: 3.0 to 2 places is
               3.00.
             ! Always plain digits with exactly `places` digits after the
               point and no point when `places` is 0. NEVER an exponent:
               1e+20 to 1 place is 100000000000000000000.0. NEVER a negative
               zero: a value that rounds to zero prints without a minus sign.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error.
             errors: invalid_places

400-0000121  FORMAT_DEC(value: decimal, places: int) -> text
             Print a decimal with a set number of places, like 19.99
             ! HALVES AWAY FROM ZERO: 2.345 to 2 places is 2.35, -2.345 is
               -2.35, and 2.5 to 0 places is 3. More places pads with zeros:
               5 to 2 places is 5.00.
             ! Always plain digits with exactly `places` digits after the
               point and no point when `places` is 0. NEVER an exponent:
               1e+20 to 1 place is 100000000000000000000.0. NEVER a negative
               zero: a value that rounds to zero prints without a minus sign.
               Never an overflow: unlike ROUND_DEC the result is text, so it
               has no 4000-digit ceiling.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error.
             errors: invalid_places

400-0000122  FORMAT_FRACTION(value: fraction, places: int) -> text
             Print a fraction as a decimal with a set number of places, like 0.33
             ! EXACT, ROUNDED ONCE: the result is the fraction's exact value
               rounded to `places`, never via a float. 1/3 to 4 places is
               0.3333 and 2/3 is 0.6667.
             ! HALVES AWAY FROM ZERO, as ROUND_FRACTION (400-0000091): 1/8 to
               2 places is 0.13 and -1/8 is -0.13. 5/2 to 0 places is 3.
             ! Always plain digits with exactly `places` digits after the
               point and no point when `places` is 0. NEVER an exponent:
               1e+20 to 1 place is 100000000000000000000.0. NEVER a negative
               zero: a value that rounds to zero prints without a minus sign.
             ! `places` must be between 0 and 1000, or it is an
               invalid_places error.
             errors: invalid_places
```

### 500 — Input / output — the only addresses with effects

```
500-0000001  READ_TEXT_FILE(path: text) -> text  [filesystem-read]
             Read a whole UTF-8 file as text
             ! UTF-8 only. Invalid bytes are a decode_error, never
               replacement characters.
             ! Content is returned byte-for-byte; no newline translation
               happens here. SPLIT_LINES (200-0000001) is where CRLF is
               normalized.
             errors: file_not_found, decode_error, permission_denied

500-0000002  WRITE_TEXT_FILE(path: text, content: text)  [filesystem-write]
             Write text to a file as UTF-8, replacing it if it exists
             ! TRUNCATES an existing file. There is no append address in v0.
             ! Writes exactly the given content: no trailing newline is added
               and no newline translation is performed, so output is
               byte-identical on every platform.
             ! Parent directories are not created.
             errors: permission_denied, path_not_writable

500-0000003  READ_CSV(path: text) -> list<map<text,text>>  [filesystem-read]
             Read a CSV file with a header row into a list of records
             ! Comma separated, double-quote quoting, doubled quotes escape a
               quote inside a quoted field. No other dialects in contract v1.
             ! The first row is the header. A file with only a header yields
               an empty list.
             ! Rows with more cells than headers are a malformed_csv error;
               rows with fewer are padded with empty text, so every record
               has exactly the header's keys.
             ! Values are never trimmed, coerced, or type-guessed. Everything
               is text; use PARSE_INT (400-0000009) explicitly.
             errors: file_not_found, decode_error, malformed_csv, permission_denied

500-0000004  WRITE_CSV(path: text, rows: list<map<text,text>>, columns: list<text>)  [filesystem-write]
             Write records to a CSV file with a header row
             ! The columns list fixes both which fields are written and their
               order; keys not listed are dropped and listed keys missing
               from a row are written as empty.
             ! Lines end with a single U+000A on every platform.
             ! A field is quoted only when it contains a comma, a double
               quote, CR, or LF. Quotes inside are doubled. This
               minimal-quoting rule is part of the contract so output is
               byte-identical across backends.
             errors: permission_denied, path_not_writable
```

### 600 — Logic and comparison

```
600-0000001  NOT(value: bool) -> bool
             Invert a boolean

600-0000002  AND(a: bool, b: bool) -> bool
             True when both booleans are true
             ! EAGER. There is no short-circuit, because both operands are
               already-bound values.

600-0000003  OR(a: bool, b: bool) -> bool
             True when either boolean is true
             ! EAGER, mirroring AND (600-0000002).

600-0000004  EQUALS(a: T, b: T) -> bool
             Test two values of the same type for equality
             ! Text equality is exact code-point equality: no case folding,
               no Unicode normalization, no locale.

600-0000005  LESS_THAN(a: T, b: T) -> bool
             True when the first value orders before the second
             ! Ordering matches SORT (300-0000005): numeric for int, Unicode
               scalar value for text, false before true for bool.
             ! float compares numerically, and an int is never compared with
               a float: both arguments have the same type.
             ! bigint compares numerically, and an int is never compared with
               a bigint either.
             ! decimal compares numerically, by value: 0.3 is not less than
               0.30.
             ! fraction compares by exact value, never through a float: 1/3
               is less than 1/2.

600-0000006  GREATER_THAN(a: T, b: T) -> bool
             True when the first value orders after the second
             ! Ordering matches LESS_THAN (600-0000005).

600-0000007  IS_EMPTY(value: text) -> bool
             True when text has no characters
             ! Whitespace is NOT empty. Combine with TRIM (200-0000005) to
               test for blankness.
```

<!-- END GENERATED ADDRESS TABLE -->
