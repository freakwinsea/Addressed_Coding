//! The `decimal` type: an exact base-10 number, such as money.
//!
//! A decimal is a whole-number coefficient and a scale, the count of digits
//! after the point: 0.30 is (30, 2), and -1.5 is (-15, 1). 0.10 + 0.20 is
//! exactly 0.30, where an f64 would give 0.30000000000000004.
//!
//! Rust's standard library has no decimal type and this crate takes no
//! dependencies, so it is written out here, with the coefficient held in the
//! crate's own `BigInt`. The Python runtime carries the same type in
//! `phonebook_rt/decimal_.py`, written independently, not with Python's
//! `decimal` module; the two are meant to be read side by side.
//!
//! The scale is kept, not normalized away, so 0.10 + 0.20 prints as "0.30".
//! Comparison is by value, so 0.3 and 0.30 are equal and sort as ties.

use std::cmp::Ordering;

use crate::bigint::BigInt;

/// At most this many digits in the coefficient, the same ceiling as bigint.
pub const MAX_DIGITS: usize = crate::bigint::MAX_DIGITS;
/// At most this many digits after the point.
pub const MAX_SCALE: usize = 1000;

/// coefficient x 10^-scale. Zero is never negative, because `BigInt` zero is
/// never negative.
#[derive(Clone, Debug, Default)]
pub struct Decimal {
    coefficient: BigInt,
    scale: usize,
}

impl Decimal {
    pub fn new(coefficient: BigInt, scale: usize) -> Decimal {
        Decimal { coefficient, scale }
    }

    pub fn coefficient(&self) -> &BigInt {
        &self.coefficient
    }

    pub fn scale(&self) -> usize {
        self.scale
    }

    /// Read `[+-]?digits('.'digits)?`, nothing else. `None` for any other
    /// text, or for more than MAX_DIGITS digits once leading zeros are
    /// dropped, or more than MAX_SCALE digits after the point.
    pub fn parse(text: &str) -> Option<Decimal> {
        let (sign, unsigned) = match text.as_bytes().first() {
            Some(b'-') => ("-", &text[1..]),
            Some(b'+') => ("", &text[1..]),
            _ => ("", text),
        };
        let (whole, fraction) = match unsigned.split_once('.') {
            Some((whole, fraction)) => (whole, fraction),
            None => (unsigned, ""),
        };
        let all_digits = |part: &str| part.bytes().all(|b| b.is_ascii_digit());
        if whole.is_empty() || !all_digits(whole) || !all_digits(fraction) {
            return None;
        }
        if unsigned.contains('.') && fraction.is_empty() {
            return None;
        }
        if fraction.len() > MAX_SCALE {
            return None;
        }
        // BigInt::parse drops leading zeros and refuses past MAX_DIGITS.
        let coefficient = BigInt::parse(&format!("{sign}{whole}{fraction}"))?;
        Some(Decimal::new(coefficient, fraction.len()))
    }

    /// A decimal literal from generated code. The parser has already checked
    /// it, so a failure here is a bug in the emitter, not the program.
    pub fn literal(text: &str) -> Decimal {
        match Decimal::parse(text) {
            Some(value) => value,
            None => panic!("invalid decimal literal {text:?}"),
        }
    }

    /// Fault unless the value is within both ceilings.
    pub fn checked(self, operation: &str) -> Decimal {
        if self.scale > MAX_SCALE {
            crate::fault(
                "overflow",
                &format!("{operation} result has more than {MAX_SCALE} digits after the point"),
            );
        }
        if self.coefficient.digit_count() > MAX_DIGITS {
            crate::fault(
                "overflow",
                &format!("{operation} result has more than {MAX_DIGITS} digits"),
            );
        }
        self
    }

    /// The coefficient this value would have at `scale`, rounding halves away
    /// from zero when that drops digits.
    pub fn rescaled(&self, scale: usize) -> BigInt {
        if scale >= self.scale {
            return self.coefficient.mul(&BigInt::pow10(scale - self.scale));
        }
        divide_rounded(&self.coefficient, &BigInt::pow10(self.scale - scale))
    }
}

/// numerator / denominator to the nearest whole number, halves away from
/// zero. The denominator is positive.
pub fn divide_rounded(numerator: &BigInt, denominator: &BigInt) -> BigInt {
    // div_rem truncates toward zero, and the remainder takes the numerator's
    // sign, so rounding away from zero is one more step in that direction.
    let (quotient, remainder) = numerator.div_rem(denominator);
    let remainder = remainder.abs();
    if remainder.add(&remainder) >= *denominator {
        let one = BigInt::from_i64(1);
        if numerator.is_negative() {
            return quotient.sub(&one);
        }
        return quotient.add(&one);
    }
    quotient
}

impl Ord for Decimal {
    /// By value: 0.3 and 0.30 are equal.
    fn cmp(&self, other: &Decimal) -> Ordering {
        let scale = self.scale.max(other.scale);
        self.rescaled(scale).cmp(&other.rescaled(scale))
    }
}

impl PartialOrd for Decimal {
    fn partial_cmp(&self, other: &Decimal) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl PartialEq for Decimal {
    fn eq(&self, other: &Decimal) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl Eq for Decimal {}

impl std::fmt::Display for Decimal {
    /// Every digit of the coefficient, with the point `scale` digits from the
    /// right and at least one digit before it: "0.30", "-0.05", "12".
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut digits = self.coefficient.abs().to_string();
        if self.scale > 0 {
            if digits.len() < self.scale + 1 {
                digits = "0".repeat(self.scale + 1 - digits.len()) + &digits;
            }
            digits.insert(digits.len() - self.scale, '.');
        }
        if self.coefficient.is_negative() {
            f.write_str("-")?;
        }
        f.write_str(&digits)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dec(text: &str) -> Decimal {
        Decimal::parse(text).unwrap()
    }

    #[test]
    fn round_trips_through_text() {
        for text in ["0", "0.30", "-0.05", "12", "-1234567890.123456789", "0.000"] {
            assert_eq!(dec(text).to_string(), text);
        }
        assert_eq!(dec("-0.00").to_string(), "0.00");
        assert_eq!(dec("+007.50").to_string(), "7.50");
    }

    #[test]
    fn rejects_other_shapes() {
        for text in ["", ".5", "5.", "1e5", "1.2.3", "--1", "1_000", " 1"] {
            assert!(Decimal::parse(text).is_none(), "{text:?}");
        }
    }

    #[test]
    fn compares_by_value() {
        assert_eq!(dec("0.3"), dec("0.30"));
        assert!(dec("-0.31") < dec("-0.3"));
        assert!(dec("10") > dec("9.999"));
    }

    #[test]
    fn rounds_halves_away_from_zero() {
        assert_eq!(dec("2.5").rescaled(0).to_string(), "3");
        assert_eq!(dec("-2.5").rescaled(0).to_string(), "-3");
        assert_eq!(dec("2.49").rescaled(0).to_string(), "2");
        assert_eq!(dec("-0.004").rescaled(2).to_string(), "0");
    }
}
