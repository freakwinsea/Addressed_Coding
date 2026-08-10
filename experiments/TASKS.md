# The 20 tasks

## Before you start

Read **[docs/WRITING-PHONE.md](../docs/WRITING-PHONE.md)** first, all of it. It
is about 6,000 tokens and it is the only description of this language that
exists — you have not seen `.phone` before and none of the address numbers are
guessable. If you are working outside a checkout, `dial brief` prints the same
content.

Then:

```bash
pip install -e .        # from the repository root
```

Write one file per task, named `t01.phone` through `t20.phone`, in a single
directory. Programs are run from the repository root, so keep the data paths
exactly as they are written below.

---

> **Running this as a study?** A full clone contains worked solutions in
> `experiments/reference/` and the exact outputs in `experiments/expected/`.
> Strip them from the model's clone first, or the result measures nothing:
>
> ```bash
> python scripts/prepare_study_clone.py /path/to/the/models/clone
> ```

Every task:

- reads from `experiments/data/`, with paths written relative to the repository
  root, which is where the program will be run from;
- prints a single deterministic result to standard output;
- is solvable with the 54 registered addresses. If one seems to need something
  that does not exist, it can be built from what does.

Score a finished set with:

```bash
python scripts/score_attempts.py path/to/that/directory
```

---

## Tier 1 — straight line, no local extensions

**t01.** Print how many lines are in `experiments/data/words.txt`.

**t02.** Print every line of `experiments/data/words.txt` with all letters
uppercased, one line per line.

**t03.** Print the lines of `experiments/data/words.txt` in reverse order, one
per line.

**t04.** Print how many distinct words appear in `experiments/data/words.txt`.
Words are separated by whitespace; compare them exactly as they appear.

**t05.** Print the total number of characters in `experiments/data/words.txt`,
counting every character in the file including newlines.

## Tier 2 — one local extension

**t06.** Print every line of `experiments/data/log.txt` that contains the text
`ERROR`, one per line, in the order they appear.

**t07.** Print how many lines of `experiments/data/log.txt` contain the text
`ERROR`.

**t08.** `experiments/data/numbers.txt` holds one integer per line. Print their
sum.

**t09.** Print the largest integer in `experiments/data/numbers.txt`.

**t10.** Print the mean of the integers in `experiments/data/numbers.txt`, as an
integer. There is no floating point; the division truncates toward zero.

**t11.** Print `true` if any line of `experiments/data/log.txt` starts with `#`,
and `false` otherwise.

**t12.** `experiments/data/inventory.csv` has columns `name,category,qty,price_cents`.
Print the name of every item whose `qty` is `0`, one per line, in file order.

## Tier 3 — several extensions, pairs, sorting by a derived key

**t13.** Print the longest word in `experiments/data/words.txt`. Exactly one word
is longest.

**t14.** Print every word in `experiments/data/words.txt` that appears more than
twice, in alphabetical order, one per line.

**t15.** For each row of `experiments/data/inventory.csv`, build the text
`name (category)` — for example `Widget (hardware)`. Print all of them sorted
alphabetically, one per line.

**t16.** Print the distinct values of the `category` column in
`experiments/data/inventory.csv`, sorted alphabetically, one per line.

**t17.** Print the number of characters in the longest line of
`experiments/data/words.txt`.

## Tier 4 — folding and writing files

**t18.** Print the total value of `experiments/data/inventory.csv` in cents: for
every row, `qty` multiplied by `price_cents`, all summed together.

**t19.** Write every `ERROR` line of `experiments/data/log.txt` to
`experiments/out/errors.txt`, one per line, then print how many lines were
written. The directory `experiments/out/` already exists.

**t20.** Write a CSV to `experiments/out/restock.csv` with the columns `name`
and `qty`, in that order, containing only the rows of
`experiments/data/inventory.csv` whose `qty` is greater than 10. Then print how
many data rows were written.
