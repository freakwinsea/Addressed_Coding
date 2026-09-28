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

/// 400-0000010 ABS — the smallest i64 has no positive twin, so it overflows.
pub fn abs_(a: &i64) -> i64 {
    match a.checked_abs() {
        Some(value) => value,
        None => crate::fault("overflow", "ABS overflowed a 64-bit signed integer"),
    }
}

/// 400-0000011 NEGATE — the smallest i64 overflows, as in ABS.
pub fn negate(a: &i64) -> i64 {
    match a.checked_neg() {
        Some(value) => value,
        None => crate::fault("overflow", "NEGATE overflowed a 64-bit signed integer"),
    }
}

/// 400-0000012 POW — squares step by step, the same algorithm as the Python
/// runtime. Not `checked_pow`: that takes a `u32` exponent, and the contract's
/// exponent is any non-negative i64. The base is only squared again when more
/// exponent bits remain, so a result that fits never trips on a square it did
/// not need.
pub fn pow_(base: &i64, exponent: &i64) -> i64 {
    if *exponent < 0 {
        crate::fault(
            "negative_exponent",
            &format!("POW exponent {exponent} is negative"),
        );
    }
    let mut base = *base;
    let mut exponent = *exponent;
    let mut result: i64 = 1;
    while exponent > 0 {
        if exponent & 1 == 1 {
            result = match result.checked_mul(base) {
                Some(value) => value,
                None => crate::fault("overflow", "POW overflowed a 64-bit signed integer"),
            };
        }
        exponent >>= 1;
        if exponent > 0 {
            base = match base.checked_mul(base) {
                Some(value) => value,
                None => crate::fault("overflow", "POW overflowed a 64-bit signed integer"),
            };
        }
    }
    result
}

/// 400-0000013 CLAMP — both ends included; low above high is an error.
/// Not `i64::clamp`, which panics on a reversed range instead of faulting.
pub fn clamp(value: &i64, low: &i64, high: &i64) -> i64 {
    if low > high {
        crate::fault(
            "invalid_range",
            &format!("CLAMP low {low} is above high {high}"),
        );
    }
    if value < low {
        *low
    } else if value > high {
        *high
    } else {
        *value
    }
}

/// 400-0000014 SIGN — exactly -1, 0, or 1.
pub fn sign(a: &i64) -> i64 {
    if *a < 0 {
        -1
    } else if *a > 0 {
        1
    } else {
        0
    }
}
