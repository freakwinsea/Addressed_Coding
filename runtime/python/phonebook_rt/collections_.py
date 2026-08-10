"""Area 300 — collections.

The ordering promises live here: ENTRIES sorts by key, SORT and SORT_BY are
stable, UNIQUE keeps first occurrences. Those are the rules that make a
map-derived result identical in a language with insertion-ordered dicts and a
language with key-ordered trees.
"""

from __future__ import annotations


def make_list(*items):
    """300-0000001 LIST."""
    return list(items)


def filter_seq(sequence: list, predicate):
    """300-0000002 FILTER — order preserved, predicate applied once per item."""
    return [item for item in sequence if predicate(item)]


def map_seq(sequence: list, transform):
    """300-0000003 MAP."""
    return [transform(item) for item in sequence]


def reduce_seq(sequence: list, combine, initial):
    """300-0000004 REDUCE — left fold, always."""
    accumulator = initial
    for item in sequence:
        accumulator = combine(accumulator, item)
    return accumulator


def sort_seq(sequence: list):
    """300-0000005 SORT — stable; text orders by code point, not locale."""
    return sorted(sequence)


def sort_by(sequence: list, key, descending: bool):
    """300-0000006 SORT_BY — stable in both directions.

    `reverse=True` reverses the comparison, not the result, so ties keep their
    original relative order. Reversing the sorted list instead would silently
    break that, and the tie order is exactly what makes word_freq's output
    reproducible.
    """
    return sorted(sequence, key=key, reverse=descending)


def reverse_seq(sequence: list):
    """300-0000007 REVERSE."""
    return list(reversed(sequence))


def unique(sequence: list):
    """300-0000008 UNIQUE — first-occurrence order."""
    return list(dict.fromkeys(sequence))


def count(sequence: list) -> int:
    """300-0000009 COUNT."""
    return len(sequence)


def take(sequence: list, n: int):
    """300-0000010 TAKE — clamped at both ends, never an error."""
    if n <= 0:
        return []
    return sequence[:n]


def first(sequence: list, fallback):
    """300-0000011 FIRST — total by construction."""
    return sequence[0] if sequence else fallback


def count_occurrences(sequence: list) -> dict:
    """300-0000012 COUNT_OCCURRENCES."""
    tallies: dict = {}
    for item in sequence:
        tallies[item] = tallies.get(item, 0) + 1
    return tallies


def entries(mapping: dict) -> list:
    """300-0000013 ENTRIES — sorted by key, by contract."""
    return [(key, mapping[key]) for key in sorted(mapping)]


def get(mapping: dict, key, fallback):
    """300-0000014 GET — total: a missing key returns the fallback."""
    return mapping.get(key, fallback)


def pair_key(value):
    """300-0000015 PAIR_KEY."""
    return value[0]


def pair_value(value):
    """300-0000016 PAIR_VALUE."""
    return value[1]
