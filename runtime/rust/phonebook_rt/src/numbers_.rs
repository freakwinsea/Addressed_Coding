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
