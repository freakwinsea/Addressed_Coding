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
| `SORT_BY` | `callable(T)->K` | one param, returns `int`/`float`/`text`/`bool` |
| `REDUCE` | `callable(A,T)->A` | **two** params: accumulator first, item second |

You can also pass a registered address directly when its shape already fits —
but most useful ones take extra arguments (`GET` takes three), so an extension
is the normal answer.

## 4. Types

```
int   float   bool   text   unit
list<T>   map<K,V>   pair<K,V>   callable(T,...)->R   any
```

- `unit` means "returns nothing" — do not bind it.
- `pair<K,V>` comes from `ENTRIES`; take it apart with `PAIR_KEY` / `PAIR_VALUE`.
- `map<K,V>` comes from `READ_CSV` (one map per row) and `COUNT_OCCURRENCES`.
- Generic variables (`T`, `K`, `V`, `A`, `R`) are resolved from your arguments.
- Some addresses require a *comparable* or *keyable* type. Comparable is `int`,
  `float`, `text`, or `bool`; keyable is the same without `float`. You cannot
  sort a list of lists, and you cannot use a float as a map key or in `EQUALS`.
- **`int` and `float` never mix.** `ADD` is for ints and `ADD_FLOAT` for floats;
  write `2.0`, not `2`, where a float is wanted. Cross with `TO_FLOAT` and
  `TO_INT` (which truncates; use `ROUND` first for nearest).
- Floats are always finite. Dividing by zero is an error, not infinity.
  For money, whole cents in an `int` are still the exact choice.

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

600-0000006  GREATER_THAN(a: T, b: T) -> bool
             True when the first value orders after the second
             ! Ordering matches LESS_THAN (600-0000005).

600-0000007  IS_EMPTY(value: text) -> bool
             True when text has no characters
             ! Whitespace is NOT empty. Combine with TRIM (200-0000005) to
               test for blankness.
```

<!-- END GENERATED ADDRESS TABLE -->
