//! Area 400 — integer arithmetic.
//!
//! Rust is the backend that agrees with the contract here for free: `/`
//! truncates toward zero and `%` takes the sign of the dividend, which is
//! exactly what 400-0000004 and 400-0000005 promise. The Python runtime has to
//! implement both by hand to match. Same contract, different effort — and the
//! program never learns which side had to work harder.

/// 400-0000001 ADD
pub fn add(a: &i64, b: &i64) -> i64 {
    match a.checked_add(*b) {
        Some(value) => value,
        None => crate::fault("overflow", "ADD overflowed a 64-bit signed integer"),
    }
}

/// 400-0000002 SUB
pub fn sub(a: &i64, b: &i64) -> i64 {
    match a.checked_sub(*b) {
        Some(value) => value,
        None => crate::fault("overflow", "SUB overflowed a 64-bit signed integer"),
    }
}

/// 400-0000003 MUL
pub fn mul(a: &i64, b: &i64) -> i64 {
    match a.checked_mul(*b) {
        Some(value) => value,
        None => crate::fault("overflow", "MUL overflowed a 64-bit signed integer"),
    }
}

/// 400-0000004 DIV — truncates toward zero, which is Rust's own behavior.
pub fn div(a: &i64, b: &i64) -> i64 {
    if *b == 0 {
        crate::fault("division_by_zero", "DIV by zero");
    }
    match a.checked_div(*b) {
        Some(value) => value,
        None => crate::fault("overflow", "DIV overflowed a 64-bit signed integer"),
    }
}

/// 400-0000005 MOD — sign of the dividend, which is Rust's own behavior.
pub fn mod_(a: &i64, b: &i64) -> i64 {
    if *b == 0 {
        crate::fault("division_by_zero", "MOD by zero");
    }
    match a.checked_rem(*b) {
        Some(value) => value,
        None => crate::fault("overflow", "MOD overflowed a 64-bit signed integer"),
    }
}

/// 400-0000006 MIN
pub fn min_(a: &i64, b: &i64) -> i64 {
    if a < b {
        *a
    } else {
        *b
    }
}

/// 400-0000007 MAX
pub fn max_(a: &i64, b: &i64) -> i64 {
    if a > b {
        *a
    } else {
        *b
    }
}

/// 400-0000008 SUM — left to right; empty sums to 0.
pub fn sum_(values: &[i64]) -> i64 {
    let mut total: i64 = 0;
    for value in values {
        total = add(&total, value);
    }
    total
}

/// 400-0000009 PARSE_INT — never fails; unparseable text yields the fallback.
pub fn parse_int(value: &str, fallback: &i64) -> i64 {
    let candidate = crate::text::trim(value);
    let digits = candidate
        .strip_prefix(['+', '-'])
        .unwrap_or(candidate.as_str());
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return *fallback;
    }
    candidate.parse::<i64>().unwrap_or(*fallback)
}
