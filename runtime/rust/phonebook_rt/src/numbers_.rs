//! Area 400 — integer, floating-point, bigint, decimal and fraction arithmetic.
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

use std::cmp::Ordering;

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

/// Euclid on the magnitudes, which may be 2^63: the caller checks the fit.
/// `unsigned_abs` is what lets the smallest i64 in without overflowing.
fn magnitude_gcd(a: &i64, b: &i64) -> u64 {
    let mut a = a.unsigned_abs();
    let mut b = b.unsigned_abs();
    while b != 0 {
        let rest = a % b;
        a = b;
        b = rest;
    }
    a
}

/// 400-0000032 GCD — never negative; 2^63 does not fit and overflows.
pub fn gcd(a: &i64, b: &i64) -> i64 {
    match i64::try_from(magnitude_gcd(a, b)) {
        Ok(value) => value,
        Err(_) => crate::fault("overflow", "GCD overflowed a 64-bit signed integer"),
    }
}

/// 400-0000033 LCM — never negative; divides before multiplying.
pub fn lcm(a: &i64, b: &i64) -> i64 {
    if *a == 0 || *b == 0 {
        return 0;
    }
    let divisor = magnitude_gcd(a, b);
    let result = (a.unsigned_abs() / divisor)
        .checked_mul(b.unsigned_abs())
        .and_then(|value| i64::try_from(value).ok());
    match result {
        Some(value) => value,
        None => crate::fault("overflow", "LCM overflowed a 64-bit signed integer"),
    }
}

/// 400-0000034 PRODUCT — left to right; empty is 1; a running overflow faults.
pub fn product(values: &[i64]) -> i64 {
    let mut total: i64 = 1;
    for value in values {
        total = match total.checked_mul(*value) {
            Some(next) => next,
            None => crate::fault("overflow", "PRODUCT overflowed a 64-bit signed integer"),
        };
    }
    total
}

/// 400-0000035 IS_EVEN — the remainder is compared with 0, never with 1.
pub fn is_even(a: &i64) -> bool {
    a % 2 == 0
}

/// 400-0000036 IS_ODD — the opposite of IS_EVEN, for negatives too.
/// Not `a % 2 == 1`: Rust's -3 % 2 is -1.
pub fn is_odd(a: &i64) -> bool {
    a % 2 != 0
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

// --------------------------------------------------------------------------
// decimals
// --------------------------------------------------------------------------
//
// The type itself is in `crate::decimal`. What the functions below add is the
// contract around it: which scale a result has, the one rounding rule (halves
// away from zero, as ROUND), and the ceilings, which every result that can
// grow passes through `Decimal::checked` to meet.

use crate::decimal::{divide_rounded, Decimal, MAX_SCALE};

fn checked_places(places: i64, operation: &str) -> usize {
    if places < 0 || places > MAX_SCALE as i64 {
        crate::fault(
            "invalid_places",
            &format!("{operation} places {places} is not between 0 and {MAX_SCALE}"),
        );
    }
    places as usize
}

/// 400-0000040 TO_DEC — an int as a decimal with no places; never fails.
pub fn to_dec(value: &i64) -> Decimal {
    Decimal::new(BigInt::from_i64(*value), 0)
}

/// 400-0000041 BIG_TO_DEC — a bigint as a decimal with no places; never fails.
pub fn big_to_dec(value: &BigInt) -> Decimal {
    Decimal::new(value.clone(), 0)
}

/// 400-0000042 DEC_TO_INT — truncates toward zero, as TO_INT does.
pub fn dec_to_int(value: &Decimal) -> i64 {
    let whole = value.coefficient().div_rem(&BigInt::pow10(value.scale())).0;
    match whole.to_i64() {
        Some(whole) => whole,
        None => crate::fault(
            "overflow",
            "DEC_TO_INT value does not fit in a 64-bit signed integer",
        ),
    }
}

/// 400-0000043 ADD_DEC — the result has the larger of the two scales.
pub fn add_dec(a: &Decimal, b: &Decimal) -> Decimal {
    let scale = a.scale().max(b.scale());
    Decimal::new(a.rescaled(scale).add(&b.rescaled(scale)), scale).checked("ADD_DEC")
}

/// 400-0000044 SUB_DEC — the result has the larger of the two scales.
pub fn sub_dec(a: &Decimal, b: &Decimal) -> Decimal {
    let scale = a.scale().max(b.scale());
    Decimal::new(a.rescaled(scale).sub(&b.rescaled(scale)), scale).checked("SUB_DEC")
}

/// 400-0000045 MUL_DEC — exact; the scales add, so 1.5 x 0.25 is 0.375.
pub fn mul_dec(a: &Decimal, b: &Decimal) -> Decimal {
    Decimal::new(a.coefficient().mul(b.coefficient()), a.scale() + b.scale()).checked("MUL_DEC")
}

/// 400-0000046 DIV_DEC — the exact quotient, rounded once to `places`.
///
/// a / b = (ca / 10^sa) / (cb / 10^sb), so the quotient at `places` places is
/// ca * 10^(sb + places) / (cb * 10^sa), rounded to a whole number. Both
/// exponents are never negative, so nothing is rounded before that division.
pub fn div_dec(a: &Decimal, b: &Decimal, places: &i64) -> Decimal {
    let places = checked_places(*places, "DIV_DEC");
    if b.coefficient().is_zero() {
        crate::fault("division_by_zero", "DIV_DEC by zero");
    }
    let mut numerator = a.coefficient().mul(&BigInt::pow10(b.scale() + places));
    let mut denominator = b.coefficient().mul(&BigInt::pow10(a.scale()));
    if denominator.is_negative() {
        numerator = numerator.neg();
        denominator = denominator.neg();
    }
    Decimal::new(divide_rounded(&numerator, &denominator), places).checked("DIV_DEC")
}

/// 400-0000047 ROUND_DEC — to exactly `places` places, halves away from zero.
/// Fewer places than the value has rounds; more pads with zeros, so
/// ROUND_DEC(5, 2) is 5.00.
pub fn round_dec(value: &Decimal, places: &i64) -> Decimal {
    let places = checked_places(*places, "ROUND_DEC");
    Decimal::new(value.rescaled(places), places).checked("ROUND_DEC")
}

/// 400-0000048 PARSE_DEC — never fails; unparseable text yields the fallback.
pub fn parse_dec(value: &str, fallback: &Decimal) -> Decimal {
    Decimal::parse(&crate::text::trim(value)).unwrap_or_else(|| fallback.clone())
}

/// 400-0000049 DEC_TO_FLOAT — the nearest float, ties to even.
///
/// `str::parse::<f64>` of the decimal's own text is correctly rounded however
/// many digits it has, as Python's `float()` is, so both backends read the
/// same digits the same way.
pub fn dec_to_float(value: &Decimal) -> f64 {
    match value.to_string().parse::<f64>() {
        Ok(parsed) => finite(parsed, "DEC_TO_FLOAT"),
        Err(_) => unreachable!("a decimal's text is always a valid float"),
    }
}

/// 400-0000050 FLOAT_TO_DEC — the float's shortest digits, as TO_TEXT prints
/// them, never its exact binary value: 0.1 is 0.1.
///
/// With digits d1...dn and exponent E, the value is d1...dn x 10^(E-n+1). A
/// float has at most 17 significant digits and E is between -324 and 308, so
/// the result is always inside both ceilings.
pub fn float_to_dec(value: &f64) -> Decimal {
    let (digits, exponent) = shortest_digits(value.abs());
    let power = exponent as i64 - digits.len() as i64 + 1;
    let sign = if *value < 0.0 { "-" } else { "" };
    let coefficient = BigInt::literal(&format!("{sign}{digits}"));
    if power >= 0 {
        return Decimal::new(coefficient.mul(&BigInt::pow10(power as usize)), 0);
    }
    Decimal::new(coefficient, (-power) as usize)
}

// --------------------------------------------------------------------------
// comparisons
// --------------------------------------------------------------------------

/// 400-0000060 NUMBER_EQUALS — exact, floats included.
pub fn number_equals<T: PartialEq>(a: &T, b: &T) -> bool {
    a == b
}

/// 400-0000061 NUMBER_NOT_EQUALS
pub fn number_not_equals<T: PartialEq>(a: &T, b: &T) -> bool {
    a != b
}

/// 400-0000062 LESS_OR_EQUAL
pub fn less_or_equal<T: PartialOrd>(a: &T, b: &T) -> bool {
    a <= b
}

/// 400-0000063 GREATER_OR_EQUAL
pub fn greater_or_equal<T: PartialOrd>(a: &T, b: &T) -> bool {
    a >= b
}

/// 400-0000064 COMPARE — exactly -1, 0, or 1.
///
/// Written with `<` and `>` rather than `partial_cmp`, which returns an
/// `Option` for floats; with no NaN there is always an answer.
pub fn compare<T: PartialOrd>(a: &T, b: &T) -> i64 {
    if a < b {
        -1
    } else if a > b {
        1
    } else {
        0
    }
}

/// 400-0000065 CLOSE_TO — absolute tolerance, edge included.
///
/// A difference too large to be finite comes out as infinity, which no
/// tolerance reaches, and a negative tolerance is below every difference.
/// Neither needs its own branch.
pub fn close_to(a: &f64, b: &f64, tolerance: &f64) -> bool {
    (a - b).abs() <= *tolerance
}

// --------------------------------------------------------------------------
// fractions
// --------------------------------------------------------------------------
//
// A fraction is an exact ratio of two 64-bit integers, always kept in lowest
// terms with a positive denominator. That one rule makes every fraction have a
// single spelling, so equality, ordering and printing need no further thought.
//
// No crate: the arithmetic is written out by hand, the same way the Python
// runtime writes it. Every product of two 64-bit values fits in i128, so the
// intermediates here are exact, as Python's unbounded ints are; only the
// reduced result has to fit back into 64 bits.

/// An exact fraction: numerator / denominator, in lowest terms, denominator > 0.
///
/// The fields are private and every constructor goes through `fraction`, so
/// the invariant always holds and the derived equality and hash are exact.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Fraction {
    numerator: i64,
    denominator: i64,
}

impl Ord for Fraction {
    /// Cross-multiplied in i128, which cannot overflow.
    fn cmp(&self, other: &Self) -> Ordering {
        let left = self.numerator as i128 * other.denominator as i128;
        let right = other.numerator as i128 * self.denominator as i128;
        left.cmp(&right)
    }
}

impl PartialOrd for Fraction {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Euclid's algorithm on the wide working values, as the Python runtime writes it.
/// Not GCD (400-0000032): that one works in i64, and these products need i128.
fn gcd_wide(mut a: u128, mut b: u128) -> u128 {
    while b != 0 {
        let rest = a % b;
        a = b;
        b = rest;
    }
    a
}

/// Lowest terms, positive denominator, and both parts inside 64 bits.
///
/// `denominator` is never zero here; every caller has already checked.
fn fraction(numerator: i128, denominator: i128, operation: &str) -> Fraction {
    let (numerator, denominator) = if denominator < 0 {
        (-numerator, -denominator)
    } else {
        (numerator, denominator)
    };
    let divisor = gcd_wide(numerator.unsigned_abs(), denominator as u128) as i128;
    let numerator = numerator / divisor;
    let denominator = denominator / divisor;
    match (i64::try_from(numerator), i64::try_from(denominator)) {
        (Ok(numerator), Ok(denominator)) => Fraction {
            numerator,
            denominator,
        },
        _ => crate::fault(
            "overflow",
            &format!("{operation} result does not fit in a 64-bit fraction"),
        ),
    }
}

/// 400-0000080 MAKE_FRACTION — reduced to lowest terms, sign on the numerator.
pub fn make_fraction(numerator: &i64, denominator: &i64) -> Fraction {
    if *denominator == 0 {
        crate::fault("division_by_zero", "MAKE_FRACTION with a zero denominator");
    }
    fraction(*numerator as i128, *denominator as i128, "MAKE_FRACTION")
}

/// 400-0000081 ADD_FRACTION
pub fn add_fraction(a: &Fraction, b: &Fraction) -> Fraction {
    fraction(
        a.numerator as i128 * b.denominator as i128 + b.numerator as i128 * a.denominator as i128,
        a.denominator as i128 * b.denominator as i128,
        "ADD_FRACTION",
    )
}

/// 400-0000082 SUB_FRACTION
pub fn sub_fraction(a: &Fraction, b: &Fraction) -> Fraction {
    fraction(
        a.numerator as i128 * b.denominator as i128 - b.numerator as i128 * a.denominator as i128,
        a.denominator as i128 * b.denominator as i128,
        "SUB_FRACTION",
    )
}

/// 400-0000083 MUL_FRACTION
pub fn mul_fraction(a: &Fraction, b: &Fraction) -> Fraction {
    fraction(
        a.numerator as i128 * b.numerator as i128,
        a.denominator as i128 * b.denominator as i128,
        "MUL_FRACTION",
    )
}

/// 400-0000084 DIV_FRACTION — dividing by a zero fraction is an error.
pub fn div_fraction(a: &Fraction, b: &Fraction) -> Fraction {
    if b.numerator == 0 {
        crate::fault("division_by_zero", "DIV_FRACTION by zero");
    }
    fraction(
        a.numerator as i128 * b.denominator as i128,
        a.denominator as i128 * b.numerator as i128,
        "DIV_FRACTION",
    )
}

/// 400-0000085 NEGATE_FRACTION — the smallest i64 numerator overflows.
pub fn negate_fraction(a: &Fraction) -> Fraction {
    fraction(
        -(a.numerator as i128),
        a.denominator as i128,
        "NEGATE_FRACTION",
    )
}

/// 400-0000086 ABS_FRACTION — the smallest i64 numerator overflows.
pub fn abs_fraction(a: &Fraction) -> Fraction {
    fraction(
        (a.numerator as i128).abs(),
        a.denominator as i128,
        "ABS_FRACTION",
    )
}

/// 400-0000087 NUMERATOR — of the lowest-terms form, carrying the sign.
pub fn numerator(a: &Fraction) -> i64 {
    a.numerator
}

/// 400-0000088 DENOMINATOR — of the lowest-terms form, always positive.
pub fn denominator(a: &Fraction) -> i64 {
    a.denominator
}

/// 400-0000089 FRACTION_TO_FLOAT — nearest float, ties to even.
///
/// NOT `n as f64 / d as f64`: each `as` can round once and the division again,
/// and a value past 2^53 would come out one step off. Python's `int / int`
/// rounds once, so this does the same by long division: take a quotient with
/// 54 or 55 bits, keep 53, and round what is left over by hand.
pub fn fraction_to_float(a: &Fraction) -> f64 {
    if a.numerator == 0 {
        return 0.0;
    }
    let top = a.numerator.unsigned_abs() as u128;
    let bottom = a.denominator as u128;
    let top_bits = 128 - top.leading_zeros() as i32;
    let bottom_bits = 128 - bottom.leading_zeros() as i32;
    // top / bottom lies strictly between 2^(top_bits-bottom_bits-1) and
    // 2^(top_bits-bottom_bits+1), so scaling by 2^shift puts the quotient in
    // [2^53, 2^55). The shifted value has at most 54 + 63 bits.
    let shift = 54 - top_bits + bottom_bits;
    let (scaled_top, scaled_bottom) = if shift >= 0 {
        (top << shift, bottom)
    } else {
        (top, bottom << -shift)
    };
    let quotient = scaled_top / scaled_bottom;
    let inexact = scaled_top % scaled_bottom != 0;
    let dropped = if quotient >= 1u128 << 54 { 2 } else { 1 };
    let mut mantissa = quotient >> dropped;
    let rest = quotient & ((1u128 << dropped) - 1);
    let half = 1u128 << (dropped - 1);
    if rest > half || (rest == half && (inexact || mantissa & 1 == 1)) {
        mantissa += 1;
    }
    let mut exponent = dropped - shift;
    if mantissa == 1u128 << 53 {
        mantissa >>= 1;
        exponent += 1;
    }
    // The magnitude is between 2^-63 and 2^63, far from subnormals and
    // infinity, so the power of two is exact and so is the product.
    let scale = f64::from_bits(((exponent + 1023) as u64) << 52);
    let magnitude = mantissa as f64 * scale;
    if a.numerator < 0 {
        -magnitude
    } else {
        magnitude
    }
}

/// 400-0000090 FLOOR_FRACTION — toward negative infinity. With a positive
/// denominator, `div_euclid` is exactly floor division; `/` would truncate.
pub fn floor_fraction(a: &Fraction) -> i64 {
    a.numerator.div_euclid(a.denominator)
}

/// 400-0000091 ROUND_FRACTION — halves away from zero, like ROUND.
pub fn round_fraction(a: &Fraction) -> i64 {
    let magnitude = (a.numerator as i128).abs();
    let denominator = a.denominator as i128;
    let mut whole = magnitude / denominator;
    if 2 * (magnitude % denominator) >= denominator {
        whole += 1;
    }
    // Never past the numerator's own magnitude, so it always fits.
    (if a.numerator < 0 { -whole } else { whole }) as i64
}

/// 400-0000092 PARSE_FRACTION — never fails; unparseable text yields the fallback.
pub fn parse_fraction(value: &str, fallback: &Fraction) -> Fraction {
    let candidate = crate::text::trim(value);
    let (top, bottom) = match candidate.split_once('/') {
        Some((top, bottom)) => (top, Some(bottom)),
        None => (candidate.as_str(), None),
    };
    let digits = top.strip_prefix(['+', '-']).unwrap_or(top);
    let all_digits = |text: &str| !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit());
    if !all_digits(digits) || !bottom.is_none_or(all_digits) {
        return *fallback;
    }
    let top_value = match top.parse::<i64>() {
        Ok(parsed) => parsed,
        Err(_) => return *fallback,
    };
    let bottom_value = match bottom.map_or(Ok(1), |text| text.parse::<i64>()) {
        Ok(parsed) if parsed > 0 => parsed,
        _ => return *fallback,
    };
    fraction(top_value as i128, bottom_value as i128, "PARSE_FRACTION")
}

/// How TO_TEXT (100-0000005) renders a fraction: `-1/3`, or `2` when whole.
pub fn fraction_text(value: &Fraction) -> String {
    if value.denominator == 1 {
        value.numerator.to_string()
    } else {
        format!("{}/{}", value.numerator, value.denominator)
    }
}

// --------------------------------------------------------------------------
// conversions between the exact types
// --------------------------------------------------------------------------

/// 400-0000100 DEC_TO_BIG — truncates toward zero, as DEC_TO_INT does; never fails.
pub fn dec_to_big(value: &Decimal) -> BigInt {
    value.coefficient().div_rem(&BigInt::pow10(value.scale())).0
}

/// 400-0000101 BIG_TO_FLOAT — the nearest float, ties to even.
///
/// `str::parse::<f64>` of the bigint's text, as DEC_TO_FLOAT reads a
/// decimal's, so both backends round the same digits the same way.
pub fn big_to_float(value: &BigInt) -> f64 {
    match value.to_string().parse::<f64>() {
        Ok(parsed) => finite(parsed, "BIG_TO_FLOAT"),
        Err(_) => unreachable!("a bigint's text is always a valid float"),
    }
}

/// 400-0000102 FLOAT_TO_BIG — the float's exact binary value, truncated
/// toward zero.
///
/// NOT `as i128`, which saturates. A finite float is mantissa x 2^exponent
/// with a 53-bit mantissa, so the whole part is the mantissa shifted right
/// (dropping the fraction bits) or multiplied up by a power of two.
pub fn float_to_big(value: &f64) -> BigInt {
    let bits = value.to_bits();
    let exponent_bits = ((bits >> 52) & 0x7ff) as i64;
    if exponent_bits == 0 {
        // Zero or subnormal: always less than 1 in size.
        return BigInt::from_i64(0);
    }
    let mantissa = ((bits & ((1u64 << 52) - 1)) | (1u64 << 52)) as i64;
    let exponent = exponent_bits - 1075;
    let mut magnitude = if exponent >= 0 {
        let mut result = BigInt::from_i64(mantissa);
        let mut left = exponent;
        while left > 0 {
            let step = left.min(62);
            result = result.mul(&BigInt::from_i64(1i64 << step));
            left -= step;
        }
        result
    } else if exponent > -53 {
        BigInt::from_i64(mantissa >> -exponent)
    } else {
        BigInt::from_i64(0)
    };
    if *value < 0.0 {
        magnitude = magnitude.neg();
    }
    magnitude
}

/// Euclid's algorithm on bigints, both not negative.
fn gcd_big(mut a: BigInt, mut b: BigInt) -> BigInt {
    while !b.is_zero() {
        let rest = a.div_rem(&b).1;
        a = b;
        b = rest;
    }
    a
}

/// 400-0000103 DEC_TO_FRACTION — exact: coefficient / 10^scale, reduced.
///
/// The coefficient can have 4000 digits, far past `fraction`'s i128 working,
/// so this reduces in bigints first and only then asks whether the parts fit.
pub fn dec_to_fraction(value: &Decimal) -> Fraction {
    let top = value.coefficient().clone();
    let bottom = BigInt::pow10(value.scale());
    let divisor = gcd_big(top.abs(), bottom.clone());
    let top = top.div_rem(&divisor).0;
    let bottom = bottom.div_rem(&divisor).0;
    match (top.to_i64(), bottom.to_i64()) {
        (Some(numerator), Some(denominator)) => Fraction {
            numerator,
            denominator,
        },
        _ => crate::fault(
            "overflow",
            "DEC_TO_FRACTION result does not fit in a 64-bit fraction",
        ),
    }
}

/// 400-0000104 FRACTION_TO_DEC — rounded once to `places`, halves away from zero.
///
/// numerator * 10^places / denominator, rounded to a whole number, is the
/// coefficient. The denominator is always positive, as divide_rounded needs.
pub fn fraction_to_dec(value: &Fraction, places: &i64) -> Decimal {
    let places = checked_places(*places, "FRACTION_TO_DEC");
    let numerator = BigInt::from_i64(value.numerator).mul(&BigInt::pow10(places));
    Decimal::new(
        divide_rounded(&numerator, &BigInt::from_i64(value.denominator)),
        places,
    )
}

/// 400-0000105 BIG_TO_FRACTION — the value over 1; overflow past 64 bits.
pub fn big_to_fraction(value: &BigInt) -> Fraction {
    match value.to_i64() {
        Some(numerator) => Fraction {
            numerator,
            denominator: 1,
        },
        None => crate::fault(
            "overflow",
            "BIG_TO_FRACTION value does not fit in a 64-bit fraction",
        ),
    }
}
// printing
// --------------------------------------------------------------------------
//
// Each of these prints a number with exactly `places` digits after the point,
// rounding halves away from zero, as ROUND and ROUND_DEC do. None uses
// `format!("{:.2}")`: that decides on a float's exact binary value and sends
// halves to even, so 2.675 is `2.67`. The contract rounds the digits TO_TEXT
// prints, so 2.675 is `2.68`. Every result is plain digits, never an exponent,
// and never a negative zero.

/// coefficient x 10^-places as text, the way a decimal prints: `-0.05`.
fn fixed(coefficient: BigInt, places: usize) -> String {
    Decimal::new(coefficient, places).to_string()
}

/// 400-0000120 FORMAT_FLOAT — the float's shortest digits, rounded to `places`.
///
/// FLOAT_TO_DEC gives exactly the digits TO_TEXT prints, and ROUND_DEC's rule
/// rounds those. NOT `format!("{:.N}")`, which rounds the binary value half to even.
pub fn format_float(value: &f64, places: &i64) -> String {
    let places = checked_places(*places, "FORMAT_FLOAT");
    fixed(float_to_dec(value).rescaled(places), places)
}

/// 400-0000121 FORMAT_DEC — ROUND_DEC then TO_TEXT, without the 4000-digit ceiling.
pub fn format_dec(value: &Decimal, places: &i64) -> String {
    let places = checked_places(*places, "FORMAT_DEC");
    fixed(value.rescaled(places), places)
}

/// 400-0000122 FORMAT_FRACTION — the exact value, rounded once to `places`.
///
/// n/d at `places` places is n x 10^places / d rounded to a whole number, so
/// 1/3 to 4 places is 3333 / 10^4. Nothing is rounded before that division.
pub fn format_fraction(value: &Fraction, places: &i64) -> String {
    let places = checked_places(*places, "FORMAT_FRACTION");
    let scaled = BigInt::from_i64(value.numerator).mul(&BigInt::pow10(places));
    fixed(
        divide_rounded(&scaled, &BigInt::from_i64(value.denominator)),
        places,
    )
}
// roots, floors, ceilings and remainders
// --------------------------------------------------------------------------
//
// Square roots are worked out on whole numbers, never with `f64::sqrt`, so
// both backends follow one written-down method and agree bit for bit. The
// Python runtime leans on `math.isqrt` for the whole-number root, which has a
// single right answer; here it is written out, bit by bit for u128 and by
// Newton's method for BigInt. The rounding of the float and the decimal is
// spelled out the same way on both sides.

fn no_negative_root(negative: bool, operation: &str) {
    if negative {
        crate::fault(
            "negative_root",
            &format!("{operation} of a negative number"),
        );
    }
}

/// The square root of a u128, rounded down: the schoolbook method in base 4,
/// one result bit per step.
fn isqrt_u128(mut value: u128) -> u128 {
    if value == 0 {
        return 0;
    }
    let mut root: u128 = 0;
    let mut bit: u128 = 1 << ((127 - value.leading_zeros()) & !1);
    while bit != 0 {
        if value >= root + bit {
            value -= root + bit;
            root = (root >> 1) + bit;
        } else {
            root >>= 1;
        }
        bit >>= 2;
    }
    root
}

/// 400-0000140 SQRT — the exact square root, rounded once to the nearest
/// float, ties to even. NOT `f64::sqrt`: the same answer, but written out so
/// the two runtimes share a method instead of trusting two maths libraries.
///
/// value = m x 2^e with m a whole number. Make e even, then scale m up by a
/// power of four until its root has at least 55 bits. That root, rounded to
/// 53 bits with the bits it drops and whether it was exact, is the answer.
pub fn sqrt_(value: &f64) -> f64 {
    no_negative_root(*value < 0.0, "SQRT");
    if *value == 0.0 {
        return 0.0;
    }
    let bits = value.to_bits();
    let field = ((bits >> 52) & 0x7ff) as i64;
    let low = (bits & ((1u64 << 52) - 1)) as u128;
    let (mut mantissa, mut exponent) = if field == 0 {
        (low, -1074i64)
    } else {
        (low | (1u128 << 52), field - 1075)
    };
    if exponent.rem_euclid(2) == 1 {
        mantissa <<= 1;
        exponent -= 1;
    }
    let length = 128 - mantissa.leading_zeros() as i64;
    let shift = ((111 - length) / 2).max(0);
    let scaled = mantissa << (2 * shift);
    let root = isqrt_u128(scaled);
    let inexact = root * root != scaled;
    let drop = (128 - root.leading_zeros() as i64) - 53;
    let mut kept = root >> drop;
    let rest = root & ((1u128 << drop) - 1);
    let half = 1u128 << (drop - 1);
    if rest > half || (rest == half && (inexact || kept & 1 == 1)) {
        kept += 1;
    }
    let mut power = exponent / 2 - shift + drop;
    if kept == 1u128 << 53 {
        kept >>= 1;
        power += 1;
    }
    // kept x 2^power, with kept in [2^52, 2^53): a root is never subnormal
    // and never too large, so this is always a normal float.
    let biased = (power + 52 + 1023) as u64;
    f64::from_bits((biased << 52) | (kept as u64 - (1u64 << 52)))
}

/// 400-0000141 FLOOR — the largest whole float not above the value.
pub fn floor_(value: &f64) -> f64 {
    finite(value.floor(), "FLOOR")
}

/// 400-0000142 CEIL — the smallest whole float not below the value. `finite`
/// turns CEIL(-0.5), which is -0.0, into 0.0.
pub fn ceil_(value: &f64) -> f64 {
    finite(value.ceil(), "CEIL")
}

/// 400-0000143 MOD_FLOAT — sign of the dividend, like MOD. Rust's `%` and
/// Python's `math.fmod` are both the exact IEEE remainder.
pub fn mod_float(a: &f64, b: &f64) -> f64 {
    if *b == 0.0 {
        crate::fault("division_by_zero", "MOD_FLOAT by zero");
    }
    finite(a % b, "MOD_FLOAT")
}

/// 400-0000144 ISQRT — the square root rounded down.
pub fn isqrt(value: &i64) -> i64 {
    no_negative_root(*value < 0, "ISQRT");
    isqrt_u128(*value as u128) as i64
}

/// 400-0000145 ISQRT_BIG — the square root rounded down; never grows.
pub fn isqrt_big(value: &BigInt) -> BigInt {
    no_negative_root(value.is_negative(), "ISQRT_BIG");
    value.isqrt()
}

/// 400-0000146 SQRT_DEC — the exact root, rounded once to `places`, halves
/// away from zero.
///
/// The answer's coefficient is sqrt(c x 10^(2p - s)) rounded, which is
/// sqrt(top / bottom) with both whole. q = isqrt(top / bottom) is that root
/// rounded down, and it rounds up when the root is at least q + 1/2, that is
/// when 4 x top >= bottom x (2q + 1)^2.
pub fn sqrt_dec(value: &Decimal, places: &i64) -> Decimal {
    let places = checked_places(*places, "SQRT_DEC");
    no_negative_root(value.coefficient().is_negative(), "SQRT_DEC");
    let (top, bottom) = if 2 * places >= value.scale() {
        (
            value
                .coefficient()
                .mul(&BigInt::pow10(2 * places - value.scale())),
            BigInt::from_i64(1),
        )
    } else {
        (
            value.coefficient().clone(),
            BigInt::pow10(value.scale() - 2 * places),
        )
    };
    let mut root = top.div_rem(&bottom).0.isqrt();
    let odd = root.add(&root).add(&BigInt::from_i64(1));
    if top.mul(&BigInt::from_i64(4)) >= bottom.mul(&odd.mul(&odd)) {
        root = root.add(&BigInt::from_i64(1));
    }
    Decimal::new(root, places).checked("SQRT_DEC")
}

/// The decimal's whole number toward -inf (FLOOR) or +inf (CEIL), 0 places.
fn whole_dec(value: &Decimal, up: bool, operation: &str) -> Decimal {
    // div_rem truncates toward zero; a remainder means one step is still
    // owed in the direction asked for.
    let (whole, remainder) = value.coefficient().div_rem(&BigInt::pow10(value.scale()));
    let one = BigInt::from_i64(1);
    let whole = if remainder.is_zero() {
        whole
    } else if up && !remainder.is_negative() {
        whole.add(&one)
    } else if !up && remainder.is_negative() {
        whole.sub(&one)
    } else {
        whole
    };
    Decimal::new(whole, 0).checked(operation)
}

/// 400-0000147 FLOOR_DEC — down to a whole number, with no places.
pub fn floor_dec(value: &Decimal) -> Decimal {
    whole_dec(value, false, "FLOOR_DEC")
}

/// 400-0000148 CEIL_DEC — up to a whole number, with no places.
pub fn ceil_dec(value: &Decimal) -> Decimal {
    whole_dec(value, true, "CEIL_DEC")
}

/// 400-0000149 MOD_DEC — exact, sign of the dividend, the larger scale.
/// `div_rem`'s remainder already takes the dividend's sign.
pub fn mod_dec(a: &Decimal, b: &Decimal) -> Decimal {
    if b.coefficient().is_zero() {
        crate::fault("division_by_zero", "MOD_DEC by zero");
    }
    let scale = a.scale().max(b.scale());
    let remainder = a.rescaled(scale).div_rem(&b.rescaled(scale)).1;
    Decimal::new(remainder, scale).checked("MOD_DEC")
}

/// 400-0000150 CEIL_FRACTION — toward positive infinity. The negated
/// numerator is taken in i128, because -i64::MIN does not fit in i64.
pub fn ceil_fraction(a: &Fraction) -> i64 {
    -((-(a.numerator as i128)).div_euclid(a.denominator as i128)) as i64
}

/// 400-0000151 MOD_FRACTION — exact, sign of the dividend.
///
/// Over the shared denominator a.den x b.den, the two numerators are
/// a.num x b.den and b.num x a.den, and the remainder is theirs. Rust's `%`
/// already takes the dividend's sign, and every product fits in i128.
pub fn mod_fraction(a: &Fraction, b: &Fraction) -> Fraction {
    if b.numerator == 0 {
        crate::fault("division_by_zero", "MOD_FRACTION by zero");
    }
    let left = a.numerator as i128 * b.denominator as i128;
    let right = b.numerator as i128 * a.denominator as i128;
    fraction(
        left % right,
        a.denominator as i128 * b.denominator as i128,
        "MOD_FRACTION",
    )
}

// --------------------------------------------------------------------------
// list maths: smallest, largest, sum, average and median
// --------------------------------------------------------------------------
//
// None of these lean on `Iterator::min`, `max` or `sum`. `min` and `max` need
// `Ord`, which `f64` does not have, and `max` keeps the LAST of equal values
// where the contract keeps the first; `sum` of i64 panics or wraps by build
// profile. Each rule is written out here as the Python runtime writes it.

fn not_empty<T>(values: &[T], operation: &str) {
    if values.is_empty() {
        crate::fault("empty_list", &format!("{operation} of an empty list"));
    }
}

/// 400-0000180 SMALLEST — the first of equal values wins.
pub fn smallest<T: Clone + PartialOrd>(values: &[T]) -> T {
    not_empty(values, "SMALLEST");
    let mut best = &values[0];
    for value in &values[1..] {
        if value < best {
            best = value;
        }
    }
    best.clone()
}

/// 400-0000181 LARGEST — the first of equal values wins.
pub fn largest<T: Clone + PartialOrd>(values: &[T]) -> T {
    not_empty(values, "LARGEST");
    let mut best = &values[0];
    for value in &values[1..] {
        if value > best {
            best = value;
        }
    }
    best.clone()
}

/// 400-0000182 SUM_FLOAT — left to right, each step rounded; not compensated.
pub fn sum_float(values: &[f64]) -> f64 {
    let mut total = 0.0;
    for value in values {
        total = finite(total + value, "SUM_FLOAT");
    }
    total
}

/// 400-0000183 SUM_BIG — exact; only the final total meets the ceiling.
pub fn sum_big(values: &[BigInt]) -> BigInt {
    let mut total = BigInt::default();
    for value in values {
        total = total.add(value);
    }
    total.checked("SUM_BIG")
}

/// The exact total at the largest scale in the list, not yet checked.
fn exact_dec_sum(values: &[Decimal]) -> Decimal {
    let mut scale = 0;
    for value in values {
        scale = scale.max(value.scale());
    }
    let mut total = BigInt::default();
    for value in values {
        total = total.add(&value.rescaled(scale));
    }
    Decimal::new(total, scale)
}

/// 400-0000184 SUM_DEC — exact, at the largest scale in the list.
pub fn sum_dec(values: &[Decimal]) -> Decimal {
    exact_dec_sum(values).checked("SUM_DEC")
}

/// 400-0000185 SUM_FRACTION — left to right with ADD_FRACTION's check each step.
pub fn sum_fraction(values: &[Fraction]) -> Fraction {
    let mut total = Fraction {
        numerator: 0,
        denominator: 1,
    };
    for value in values {
        total = fraction(
            total.numerator as i128 * value.denominator as i128
                + value.numerator as i128 * total.denominator as i128,
            total.denominator as i128 * value.denominator as i128,
            "SUM_FRACTION",
        );
    }
    total
}

/// (total x 10^-scale) / count, rounded once to `places`, halves away from zero.
fn average_places(
    total: &BigInt,
    scale: usize,
    count: usize,
    places: usize,
    operation: &str,
) -> Decimal {
    let numerator = total.mul(&BigInt::pow10(places));
    let denominator = BigInt::from_i64(count as i64).mul(&BigInt::pow10(scale));
    Decimal::new(divide_rounded(&numerator, &denominator), places).checked(operation)
}

/// 400-0000186 AVERAGE — the exact int sum over the count, rounded once.
pub fn average(values: &[i64], places: &i64) -> Decimal {
    let places = checked_places(*places, "AVERAGE");
    not_empty(values, "AVERAGE");
    let mut total = BigInt::default();
    for value in values {
        total = total.add(&BigInt::from_i64(*value));
    }
    average_places(&total, 0, values.len(), places, "AVERAGE")
}

/// 400-0000187 AVERAGE_FLOAT — SUM_FLOAT, then divided by the count.
pub fn average_float(values: &[f64]) -> f64 {
    not_empty(values, "AVERAGE_FLOAT");
    finite(sum_float(values) / values.len() as f64, "AVERAGE_FLOAT")
}

/// 400-0000188 AVERAGE_BIG — the exact sum over the count, rounded once.
pub fn average_big(values: &[BigInt], places: &i64) -> Decimal {
    let places = checked_places(*places, "AVERAGE_BIG");
    not_empty(values, "AVERAGE_BIG");
    let mut total = BigInt::default();
    for value in values {
        total = total.add(value);
    }
    average_places(&total, 0, values.len(), places, "AVERAGE_BIG")
}

/// 400-0000189 AVERAGE_DEC — the exact sum over the count, rounded once.
pub fn average_dec(values: &[Decimal], places: &i64) -> Decimal {
    let places = checked_places(*places, "AVERAGE_DEC");
    not_empty(values, "AVERAGE_DEC");
    let total = exact_dec_sum(values);
    average_places(
        total.coefficient(),
        total.scale(),
        values.len(),
        places,
        "AVERAGE_DEC",
    )
}

/// 400-0000190 AVERAGE_FRACTION — SUM_FRACTION over the count, exactly.
pub fn average_fraction(values: &[Fraction]) -> Fraction {
    not_empty(values, "AVERAGE_FRACTION");
    let total = sum_fraction(values);
    fraction(
        total.numerator as i128,
        total.denominator as i128 * values.len() as i128,
        "AVERAGE_FRACTION",
    )
}

/// The one middle value of a sorted copy, or the two middle values.
/// SORT (300-0000005) is stable, as the contract needs for equal decimals.
fn middle<T: Clone + PartialOrd>(values: &[T], operation: &str) -> (T, Option<T>) {
    not_empty(values, operation);
    let ordered = crate::collections_::sort_seq(values);
    let half = ordered.len() / 2;
    if ordered.len() % 2 == 1 {
        return (ordered[half].clone(), None);
    }
    (ordered[half - 1].clone(), Some(ordered[half].clone()))
}

/// total x 10^-scale halved exactly: one more place only when total is odd.
fn half_of(total: &BigInt, scale: usize) -> Decimal {
    let (half, rest) = total.div_rem(&BigInt::from_i64(2));
    if rest.is_zero() {
        return Decimal::new(half, scale);
    }
    Decimal::new(total.mul(&BigInt::from_i64(5)), scale + 1)
}

/// 400-0000191 MEDIAN — the middle int, or the exact midpoint of two.
pub fn median(values: &[i64]) -> Decimal {
    match middle(values, "MEDIAN") {
        (only, None) => Decimal::new(BigInt::from_i64(only), 0),
        (a, Some(b)) => half_of(&BigInt::from_i64(a).add(&BigInt::from_i64(b)), 0),
    }
}

/// 400-0000192 MEDIAN_FLOAT — the exact midpoint of two, rounded once.
///
/// When a + b is finite, it and the halving round only once between them:
/// halving is exact unless the result is subnormal, and a sum that small was
/// exact to begin with. When a + b is not finite both values are huge, so
/// halving each is exact and the one rounding is in their sum.
pub fn median_float(values: &[f64]) -> f64 {
    match middle(values, "MEDIAN_FLOAT") {
        (only, None) => only,
        (a, Some(b)) => {
            let total = a + b;
            if total.is_finite() {
                finite(total / 2.0, "MEDIAN_FLOAT")
            } else {
                finite(a / 2.0 + b / 2.0, "MEDIAN_FLOAT")
            }
        }
    }
}

/// 400-0000193 MEDIAN_BIG — the same rule as MEDIAN, under the ceiling.
pub fn median_big(values: &[BigInt]) -> Decimal {
    match middle(values, "MEDIAN_BIG") {
        (only, None) => Decimal::new(only, 0),
        (a, Some(b)) => half_of(&a.add(&b), 0).checked("MEDIAN_BIG"),
    }
}

/// 400-0000194 MEDIAN_DEC — the middle value as it is, or the exact midpoint.
pub fn median_dec(values: &[Decimal]) -> Decimal {
    match middle(values, "MEDIAN_DEC") {
        (only, None) => only,
        (a, Some(b)) => {
            let scale = a.scale().max(b.scale());
            half_of(&a.rescaled(scale).add(&b.rescaled(scale)), scale).checked("MEDIAN_DEC")
        }
    }
}

/// 400-0000195 MEDIAN_FRACTION — the middle value, or the exact midpoint.
/// Every product is under 2^126, so their sum and the doubled denominator
/// both fit in i128.
pub fn median_fraction(values: &[Fraction]) -> Fraction {
    match middle(values, "MEDIAN_FRACTION") {
        (only, None) => only,
        (a, Some(b)) => fraction(
            a.numerator as i128 * b.denominator as i128
                + b.numerator as i128 * a.denominator as i128,
            2 * a.denominator as i128 * b.denominator as i128,
            "MEDIAN_FRACTION",
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The hand-written root must be the correctly rounded one, which is what
    /// IEEE 754 requires of `f64::sqrt`; a seeded sweep over every exponent,
    /// subnormals included.
    #[test]
    fn sqrt_matches_the_correctly_rounded_root() {
        let mut state: u64 = 0x9E37_79B9_7F4A_7C15;
        for _ in 0..200_000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let value = f64::from_bits(state >> 1);
            if value.is_finite() {
                assert_eq!(sqrt_(&value).to_bits(), value.sqrt().to_bits(), "{value:e}");
            }
        }
        for value in [f64::MIN_POSITIVE, 5e-324, f64::MAX, 2.0, 0.25, 1e-310] {
            assert_eq!(sqrt_(&value).to_bits(), value.sqrt().to_bits(), "{value:e}");
        }
    }

    /// The midpoint must be the exact one rounded once, never overflowing;
    /// checked against the halving of the exact sum, taken in wider steps.
    #[test]
    fn float_midpoint_is_correctly_rounded() {
        let mut state: u64 = 0x2545_F491_4F6C_DD1D;
        for _ in 0..200_000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let a = f64::from_bits(state >> 1);
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let b = f64::from_bits(state);
            if !a.is_finite() || !b.is_finite() {
                continue;
            }
            // Scaling by a power of two is exact away from the ends, so the
            // rounded (a/4 + b/4) * 2 is the rounded midpoint for these.
            if a.abs() > 1e-300 && b.abs() > 1e-300 {
                let expected = finite((a / 4.0 + b / 4.0) * 2.0, "test");
                assert_eq!(
                    median_float(&[a, b]).to_bits(),
                    expected.to_bits(),
                    "{a:e} {b:e}"
                );
            }
        }
        let max = f64::MAX;
        assert_eq!(median_float(&[max, max]), max);
        assert_eq!(median_float(&[5e-324, 1e-323]), 1e-323);
    }

    #[test]
    fn whole_number_roots_round_down() {
        for value in [0i64, 1, 2, 3, 4, 15, 16, 17, 99, 100, i64::MAX] {
            let root = isqrt(&value) as i128;
            assert!(root * root <= value as i128 && (root + 1) * (root + 1) > value as i128);
        }
        let big = BigInt::parse(&"9".repeat(4000)).unwrap();
        let root = big.isqrt();
        assert!(root.mul(&root) <= big);
        let above = root.add(&BigInt::from_i64(1));
        assert!(above.mul(&above) > big);
    }
}
