//! Area 200 — text.
//!
//! `LENGTH` and `SLICE` count Unicode scalar values. Rust indexes `String` by
//! byte, so these go through `chars()`. Python gets that for free. Same
//! contract, different amount of work — which is the whole point of putting the
//! promise in the registry rather than in either language.

/// The contract's whitespace set: ASCII only, deliberately not Unicode-wide.
pub const WHITESPACE: [char; 6] = [' ', '\t', '\n', '\r', '\u{0c}', '\u{0b}'];

fn is_space(c: char) -> bool {
    WHITESPACE.contains(&c)
}

/// 200-0000001 SPLIT_LINES — CRLF-tolerant, absorbs one trailing newline.
pub fn split_lines(value: &str) -> Vec<String> {
    if value.is_empty() {
        return Vec::new();
    }
    let trimmed = value.strip_suffix('\n').unwrap_or(value);
    trimmed
        .split('\n')
        .map(|part| part.strip_suffix('\r').unwrap_or(part).to_string())
        .collect()
}

/// 200-0000002 SPLIT
pub fn split(value: &str, separator: &str) -> Vec<String> {
    if separator.is_empty() {
        crate::fault("empty_separator", "SPLIT needs a non-empty separator");
    }
    value
        .split(separator)
        .map(|part| part.to_string())
        .collect()
}

/// 200-0000003 SPLIT_WORDS — ASCII whitespace runs, no empty words.
pub fn split_words(value: &str) -> Vec<String> {
    value
        .split(is_space)
        .filter(|word| !word.is_empty())
        .map(|word| word.to_string())
        .collect()
}

/// 200-0000004 JOIN
pub fn join(parts: &[String], separator: &str) -> String {
    parts.join(separator)
}

/// 200-0000005 TRIM
pub fn trim(value: &str) -> String {
    value.trim_matches(is_space).to_string()
}

/// 200-0000006 LOWERCASE — ASCII only, by contract.
pub fn lowercase(value: &str) -> String {
    value.to_ascii_lowercase()
}

/// 200-0000007 UPPERCASE — ASCII only, by contract.
pub fn uppercase(value: &str) -> String {
    value.to_ascii_uppercase()
}

/// 200-0000008 REPLACE — left to right, non-overlapping, never rescanned.
pub fn replace(value: &str, find: &str, replace_with: &str) -> String {
    if find.is_empty() {
        crate::fault("empty_find", "REPLACE needs a non-empty search string");
    }
    value.replace(find, replace_with)
}

/// 200-0000009 CONTAINS
pub fn contains(haystack: &str, needle: &str) -> bool {
    haystack.contains(needle)
}

/// 200-0000010 STARTS_WITH
pub fn starts_with(value: &str, prefix: &str) -> bool {
    value.starts_with(prefix)
}

/// 200-0000011 LENGTH — Unicode scalar values, not bytes.
pub fn length(value: &str) -> i64 {
    value.chars().count() as i64
}

/// 200-0000012 SLICE — clamped; negative indices clamp to 0, never wrap.
pub fn slice_(value: &str, start: &i64, end: &i64) -> String {
    let size = value.chars().count() as i64;
    let lo = (*start).clamp(0, size);
    let hi = (*end).clamp(0, size);
    if hi <= lo {
        return String::new();
    }
    value
        .chars()
        .skip(lo as usize)
        .take((hi - lo) as usize)
        .collect()
}
