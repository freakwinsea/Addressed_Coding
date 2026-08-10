//! Area 600 — logic and comparison.

/// 600-0000001 NOT
pub fn not_(value: &bool) -> bool {
    !*value
}

/// 600-0000002 AND — eager.
pub fn and_(a: &bool, b: &bool) -> bool {
    *a && *b
}

/// 600-0000003 OR — eager.
pub fn or_(a: &bool, b: &bool) -> bool {
    *a || *b
}

/// 600-0000004 EQUALS — exact code-point equality for text.
pub fn equals<T: PartialEq>(a: &T, b: &T) -> bool {
    a == b
}

/// 600-0000005 LESS_THAN
pub fn less_than<T: PartialOrd>(a: &T, b: &T) -> bool {
    a < b
}

/// 600-0000006 GREATER_THAN
pub fn greater_than<T: PartialOrd>(a: &T, b: &T) -> bool {
    a > b
}

/// 600-0000007 IS_EMPTY — whitespace is not empty.
pub fn is_empty(value: &str) -> bool {
    value.is_empty()
}
