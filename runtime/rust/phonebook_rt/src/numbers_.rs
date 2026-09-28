//! Area 400 — integer, floating-point and fraction arithmetic.
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

/// Euclid's algorithm on non-negative integers, as the Python runtime writes it.
fn gcd(mut a: u128, mut b: u128) -> u128 {
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
    let divisor = gcd(numerator.unsigned_abs(), denominator as u128) as i128;
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
