//! Area 400 — integer and floating-point arithmetic.
//!
//! Rust is the backend that agrees with the contract here for free: `/`
//! truncates toward zero and `%` takes the sign of the dividend, which is
//! exactly what 400-0000004 and 400-0000005 promise. The Python runtime has to
//! implement both by hand to match. Same contract, different effort — and the
//! program never learns which side had to work harder.
//!
//! Floats reverse that. `f64::round` already sends halves away from zero, but
//! Rust's `Display` would print 1e16 as `10000000000000000` and 1.0 as `1`, and
//! `as i64` saturates where the contract says overflow. Every float function
//! below funnels its result through `finite`, which settles NaN, infinity and
//! negative zero; `float_text` settles printing.

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

// --------------------------------------------------------------------------
// floats
// --------------------------------------------------------------------------

/// Every float result passes through here: finite, and zero has one sign.
fn finite(value: f64, operation: &str) -> f64 {
    if !value.is_finite() {
        crate::fault(
            "overflow",
            &format!("{operation} is too large to be a finite float"),
        );
    }
    if value == 0.0 {
        0.0
    } else {
        value
    }
}

/// 400-0000015 ADD_FLOAT
pub fn add_float(a: &f64, b: &f64) -> f64 {
    finite(a + b, "ADD_FLOAT")
}

/// 400-0000016 SUB_FLOAT
pub fn sub_float(a: &f64, b: &f64) -> f64 {
    finite(a - b, "SUB_FLOAT")
}

/// 400-0000017 MUL_FLOAT
pub fn mul_float(a: &f64, b: &f64) -> f64 {
    finite(a * b, "MUL_FLOAT")
}

/// 400-0000018 DIV_FLOAT — dividing by zero is an error, never inf or NaN.
pub fn div_float(a: &f64, b: &f64) -> f64 {
    if *b == 0.0 {
        crate::fault("division_by_zero", "DIV_FLOAT by zero");
    }
    finite(a / b, "DIV_FLOAT")
}

/// 400-0000019 TO_FLOAT — nearest float, ties to even, as `as f64` rounds.
pub fn to_float(value: &i64) -> f64 {
    *value as f64
}

/// 400-0000020 TO_INT — truncates toward zero; never saturates, unlike `as i64`.
pub fn to_int(value: &f64) -> i64 {
    let truncated = value.trunc();
    // -2^63 is a float exactly; 2^63 is the first value past the top.
    const RANGE: std::ops::Range<f64> = -9_223_372_036_854_775_808.0..9_223_372_036_854_775_808.0;
    if !RANGE.contains(&truncated) {
        crate::fault(
            "overflow",
            &format!(
                "{} does not fit in a 64-bit signed integer",
                float_text(value)
            ),
        );
    }
    truncated as i64
}

/// 400-0000021 ROUND — halves away from zero.
///
/// Written out rather than `f64::round`, to read side by side with the Python
/// runtime, which cannot use its host's `round()`. `magnitude - whole` is exact
/// because `whole` is `magnitude` with its fraction bits dropped.
pub fn round_(value: &f64) -> f64 {
    let magnitude = value.abs();
    let mut whole = magnitude.floor();
    if magnitude - whole >= 0.5 {
        whole += 1.0;
    }
    finite(if *value < 0.0 { -whole } else { whole }, "ROUND")
}

/// 400-0000022 PARSE_FLOAT — never fails; unparseable text yields the fallback.
pub fn parse_float(value: &str, fallback: &f64) -> f64 {
    let candidate = crate::text::trim(value);
    if !is_float_text(&candidate) {
        return *fallback;
    }
    match candidate.parse::<f64>() {
        Ok(parsed) if parsed.is_finite() => {
            if parsed == 0.0 {
                0.0
            } else {
                parsed
            }
        }
        _ => *fallback,
    }
}

/// The PARSE_FLOAT grammar: `[+-]? digits ('.' digits)? ([eE] [+-]? digits)?`.
///
/// Checked by hand first because `str::parse::<f64>` also accepts `inf`, `nan`,
/// `.5` and `5.`, none of which the contract does.
fn is_float_text(text: &str) -> bool {
    fn digits(bytes: &[u8], mut at: usize) -> usize {
        while at < bytes.len() && bytes[at].is_ascii_digit() {
            at += 1;
        }
        at
    }
    let bytes = text.as_bytes();
    let mut at = 0;
    if at < bytes.len() && (bytes[at] == b'+' || bytes[at] == b'-') {
        at += 1;
    }
    let end = digits(bytes, at);
    if end == at {
        return false;
    }
    at = end;
    if at < bytes.len() && bytes[at] == b'.' {
        let end = digits(bytes, at + 1);
        if end == at + 1 {
            return false;
        }
        at = end;
    }
    if at < bytes.len() && (bytes[at] == b'e' || bytes[at] == b'E') {
        at += 1;
        if at < bytes.len() && (bytes[at] == b'+' || bytes[at] == b'-') {
            at += 1;
        }
        let end = digits(bytes, at);
        if end == at {
            return false;
        }
        at = end;
    }
    at == bytes.len()
}

/// How TO_TEXT (100-0000005) renders a float.
///
/// The digits come from `{:e}`, which is the shortest string that reads back
/// as the same float. The layout is then applied by hand, the same way the
/// Python runtime applies it, rather than trusting either host's own layout.
pub fn float_text(value: &f64) -> String {
    let (digits, exponent) = shortest_digits(value.abs());
    let sign = if *value < 0.0 { "-" } else { "" };
    format!("{sign}{}", layout(&digits, exponent))
}

/// Significant digits d1 d2 ... dn and exponent E, value = d1.d2...dn x 10^E.
///
/// `{:e}` gives the shortest digits, but when two candidates of that length
/// are equally close it takes the upper one: 635057293855503.25 comes out as
/// `...503.3`. The contract, like Python's repr, takes the one ending in an
/// even digit. The correctly rounded n-digit form, which rounds halves to even,
/// is that candidate whenever it reads back as the same float.
fn shortest_digits(magnitude: f64) -> (String, i32) {
    let shortest = format!("{magnitude:e}");
    let length = shortest
        .split('e')
        .next()
        .unwrap_or("")
        .replace('.', "")
        .len();
    let nearest = format!(
        "{magnitude:.precision$e}",
        precision = length.saturating_sub(1)
    );
    let chosen = if nearest.parse::<f64>() == Ok(magnitude) {
        nearest
    } else {
        shortest
    };
    let (mantissa, exp) = chosen.split_once('e').unwrap_or((&chosen, "0"));
    let exponent: i32 = exp.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let significant = digits.trim_end_matches('0');
    if significant.is_empty() {
        return ("0".to_string(), 0);
    }
    (significant.to_string(), exponent)
}

/// Positional for -4 <= E < 16, otherwise d.ddde+XX.
fn layout(digits: &str, exponent: i32) -> String {
    if (-4..16).contains(&exponent) {
        if exponent < 0 {
            let zeros = "0".repeat((-exponent - 1) as usize);
            return format!("0.{zeros}{digits}");
        }
        let width = (exponent + 1) as usize;
        let whole: String = if digits.len() >= width {
            digits[..width].to_string()
        } else {
            format!("{digits:0<width$}")
        };
        let fraction = if digits.len() > width {
            &digits[width..]
        } else {
            "0"
        };
        return format!("{whole}.{fraction}");
    }
    let mantissa = if digits.len() > 1 {
        format!("{}.{}", &digits[..1], &digits[1..])
    } else {
        digits.to_string()
    };
    let sign = if exponent >= 0 { '+' } else { '-' };
    format!("{mantissa}e{sign}{:02}", exponent.abs())
}

// --------------------------------------------------------------------------
// bigints
// --------------------------------------------------------------------------
//
// The arithmetic lives in `crate::bigint`, because Rust has no big integer of
// its own. Every result that can grow goes through `BigInt::checked`, which is
// where the 4000-digit ceiling is enforced, as `_checked_big` does in Python.

use crate::bigint::BigInt;

/// 400-0000023 TO_BIG — every int is a bigint; this never fails.
pub fn to_big(value: &i64) -> BigInt {
    BigInt::from_i64(*value)
}

/// 400-0000024 BIG_TO_INT — overflow outside the 64-bit range, never wraps.
pub fn big_to_int(value: &BigInt) -> i64 {
    match value.to_i64() {
        Some(value) => value,
        None => crate::fault(
            "overflow",
            "BIG_TO_INT value does not fit in a 64-bit signed integer",
        ),
    }
}

/// 400-0000025 ADD_BIG
pub fn add_big(a: &BigInt, b: &BigInt) -> BigInt {
    a.add(b).checked("ADD_BIG")
}

/// 400-0000026 SUB_BIG
pub fn sub_big(a: &BigInt, b: &BigInt) -> BigInt {
    a.sub(b).checked("SUB_BIG")
}

/// 400-0000027 MUL_BIG
pub fn mul_big(a: &BigInt, b: &BigInt) -> BigInt {
    a.mul(b).checked("MUL_BIG")
}

/// 400-0000028 DIV_BIG — truncates toward zero, as DIV does.
pub fn div_big(a: &BigInt, b: &BigInt) -> BigInt {
    if b.is_zero() {
        crate::fault("division_by_zero", "DIV_BIG by zero");
    }
    a.div_rem(b).0
}

/// 400-0000029 MOD_BIG — sign of the dividend, as MOD does.
pub fn mod_big(a: &BigInt, b: &BigInt) -> BigInt {
    if b.is_zero() {
        crate::fault("division_by_zero", "MOD_BIG by zero");
    }
    a.div_rem(b).1
}

/// 400-0000030 POW_BIG — the same square-and-multiply as POW, with every step
/// checked against the ceiling, so no intermediate grows past twice its digits.
pub fn pow_big(base: &BigInt, exponent: &i64) -> BigInt {
    if *exponent < 0 {
        crate::fault(
            "negative_exponent",
            &format!("POW_BIG exponent {exponent} is negative"),
        );
    }
    let mut base = base.clone();
    let mut exponent = *exponent;
    let mut result = BigInt::from_i64(1);
    while exponent > 0 {
        if exponent & 1 == 1 {
            result = result.mul(&base).checked("POW_BIG");
        }
        exponent >>= 1;
        if exponent > 0 {
            base = base.mul(&base).checked("POW_BIG");
        }
    }
    result
}

/// 400-0000031 PARSE_BIG — never fails; unparseable text yields the fallback.
/// Leading zeros are dropped before the digits are counted.
pub fn parse_big(value: &str, fallback: &BigInt) -> BigInt {
    BigInt::parse(&crate::text::trim(value)).unwrap_or_else(|| fallback.clone())
}
