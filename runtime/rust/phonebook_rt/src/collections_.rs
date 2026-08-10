//! Area 300 — collections.
//!
//! The ordering promises live here. `ENTRIES` sorting by key costs nothing in
//! Rust, because `BTreeMap` already iterates in key order — but the Python side
//! has to sort explicitly, since its dicts iterate in insertion order. Neither
//! backend gets to decide; the contract did.

use std::collections::{BTreeMap, BTreeSet};

/// 300-0000002 FILTER — order preserved, predicate applied once per item.
pub fn filter_seq<T, F>(sequence: &[T], predicate: F) -> Vec<T>
where
    T: Clone,
    F: Fn(&T) -> bool,
{
    sequence
        .iter()
        .filter(|item| predicate(item))
        .cloned()
        .collect()
}

/// 300-0000003 MAP
pub fn map_seq<T, R, F>(sequence: &[T], transform: F) -> Vec<R>
where
    F: Fn(&T) -> R,
{
    sequence.iter().map(transform).collect()
}

/// 300-0000004 REDUCE — left fold, always.
pub fn reduce_seq<T, A, F>(sequence: &[T], combine: F, initial: &A) -> A
where
    A: Clone,
    F: Fn(&A, &T) -> A,
{
    let mut accumulator = initial.clone();
    for item in sequence {
        accumulator = combine(&accumulator, item);
    }
    accumulator
}

/// 300-0000005 SORT — stable; `String` orders by byte, which for UTF-8 is
/// exactly code-point order, so this agrees with Python without special care.
pub fn sort_seq<T: Clone + Ord>(sequence: &[T]) -> Vec<T> {
    let mut out = sequence.to_vec();
    out.sort();
    out
}

/// 300-0000006 SORT_BY — stable in both directions.
///
/// Descending reverses the *comparison*, not the result. Reversing the sorted
/// vector instead would invert the order of equal keys and quietly break the
/// contract's stability promise.
pub fn sort_by<T, K, F>(sequence: &[T], key: F, descending: &bool) -> Vec<T>
where
    T: Clone,
    K: Ord,
    F: Fn(&T) -> K,
{
    let mut out = sequence.to_vec();
    if *descending {
        out.sort_by_key(|item| std::cmp::Reverse(key(item)));
    } else {
        out.sort_by_key(&key);
    }
    out
}

/// 300-0000007 REVERSE
pub fn reverse_seq<T: Clone>(sequence: &[T]) -> Vec<T> {
    sequence.iter().rev().cloned().collect()
}

/// 300-0000008 UNIQUE — first-occurrence order.
pub fn unique<T: Clone + Ord>(sequence: &[T]) -> Vec<T> {
    let mut seen: BTreeSet<T> = BTreeSet::new();
    let mut out: Vec<T> = Vec::new();
    for item in sequence {
        if seen.insert(item.clone()) {
            out.push(item.clone());
        }
    }
    out
}

/// 300-0000009 COUNT
pub fn count<T>(sequence: &[T]) -> i64 {
    sequence.len() as i64
}

/// 300-0000010 TAKE — clamped at both ends, never an error.
pub fn take<T: Clone>(sequence: &[T], n: &i64) -> Vec<T> {
    if *n <= 0 {
        return Vec::new();
    }
    let limit = (*n as usize).min(sequence.len());
    sequence[..limit].to_vec()
}

/// 300-0000011 FIRST — total by construction.
pub fn first<T: Clone>(sequence: &[T], fallback: &T) -> T {
    sequence
        .first()
        .cloned()
        .unwrap_or_else(|| fallback.clone())
}

/// 300-0000012 COUNT_OCCURRENCES
pub fn count_occurrences<T: Clone + Ord>(sequence: &[T]) -> BTreeMap<T, i64> {
    let mut tallies: BTreeMap<T, i64> = BTreeMap::new();
    for item in sequence {
        *tallies.entry(item.clone()).or_insert(0) += 1;
    }
    tallies
}

/// 300-0000013 ENTRIES — sorted by key, by contract.
pub fn entries<K: Clone + Ord, V: Clone>(mapping: &BTreeMap<K, V>) -> Vec<(K, V)> {
    mapping
        .iter()
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect()
}

/// 300-0000014 GET — total: a missing key returns the fallback.
pub fn get<K: Ord, V: Clone>(mapping: &BTreeMap<K, V>, key: &K, fallback: &V) -> V {
    mapping
        .get(key)
        .cloned()
        .unwrap_or_else(|| fallback.clone())
}

/// 300-0000015 PAIR_KEY
pub fn pair_key<K: Clone, V>(value: &(K, V)) -> K {
    value.0.clone()
}

/// 300-0000016 PAIR_VALUE
pub fn pair_value<K, V: Clone>(value: &(K, V)) -> V {
    value.1.clone()
}
