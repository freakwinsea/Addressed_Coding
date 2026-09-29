//! The `bigint` type: an exact whole number of up to 4000 decimal digits.
//!
//! Python's `int` already is one, so the Python runtime has nothing like this
//! file. Rust has no big integer in its standard library, and this crate takes
//! no dependencies, so the arithmetic is written out here: sign and magnitude,
//! with the magnitude stored as base-10^9 limbs, least significant first.
//!
//! Base 10^9 rather than 2^32 so that printing and parsing are just chunking
//! decimal digits, which keeps `TO_TEXT` obviously the same as Python's
//! `str(int)`. The algorithms are the schoolbook ones. At 4000 digits that is
//! at most 445 limbs, so there is nothing to gain from anything cleverer, and
//! a lot to lose in how easy this is to check.

use std::cmp::Ordering;

/// The ceiling every bigint address enforces (SPEC §3.2).
pub const MAX_DIGITS: usize = 4000;

const BASE: u64 = 1_000_000_000;
const LIMB_DIGITS: usize = 9;

/// A whole number. Zero is never negative, and `limbs` never ends in a zero
/// limb, so equal numbers are equal structs and the derived `Eq` is right.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Default)]
pub struct BigInt {
    negative: bool,
    limbs: Vec<u32>,
}

impl BigInt {
    fn from_parts(negative: bool, mut limbs: Vec<u32>) -> BigInt {
        while limbs.last() == Some(&0) {
            limbs.pop();
        }
        let negative = negative && !limbs.is_empty();
        BigInt { negative, limbs }
    }

    pub fn from_i64(value: i64) -> BigInt {
        // unsigned_abs keeps i64::MIN, which has no positive i64 twin.
        let mut magnitude = value.unsigned_abs();
        let mut limbs = Vec::new();
        while magnitude > 0 {
            limbs.push((magnitude % BASE) as u32);
            magnitude /= BASE;
        }
        BigInt::from_parts(value < 0, limbs)
    }

    /// The value as an i64, or `None` when it does not fit.
    pub fn to_i64(&self) -> Option<i64> {
        if self.limbs.len() > 3 {
            return None;
        }
        // Three limbs are under 10^27, which fits an i128 with room to spare.
        let mut magnitude: i128 = 0;
        for limb in self.limbs.iter().rev() {
            magnitude = magnitude * BASE as i128 + *limb as i128;
        }
        let value = if self.negative { -magnitude } else { magnitude };
        i64::try_from(value).ok()
    }

    /// Read `[+-]?digits`, nothing else. `None` for any other text, or for
    /// more than MAX_DIGITS digits once leading zeros are dropped.
    pub fn parse(text: &str) -> Option<BigInt> {
        let (negative, digits) = match text.as_bytes().first() {
            Some(b'-') => (true, &text[1..]),
            Some(b'+') => (false, &text[1..]),
            _ => (false, text),
        };
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        let digits = digits.trim_start_matches('0');
        if digits.len() > MAX_DIGITS {
            return None;
        }
        let bytes = digits.as_bytes();
        let mut limbs = Vec::with_capacity(bytes.len() / LIMB_DIGITS + 1);
        let mut end = bytes.len();
        while end > 0 {
            let start = end.saturating_sub(LIMB_DIGITS);
            let mut limb: u32 = 0;
            for digit in &bytes[start..end] {
                limb = limb * 10 + (digit - b'0') as u32;
            }
            limbs.push(limb);
            end = start;
        }
        Some(BigInt::from_parts(negative, limbs))
    }

    /// A bigint literal from generated code. The parser has already checked
    /// the digits, so a failure here is a bug in the emitter, not the program.
    pub fn literal(digits: &str) -> BigInt {
        match BigInt::parse(digits) {
            Some(value) => value,
            None => panic!("invalid bigint literal {digits:?}"),
        }
    }

    /// Ten to the given power: a one and `exponent` zeros.
    pub fn pow10(exponent: usize) -> BigInt {
        let mut limbs = vec![0u32; exponent / LIMB_DIGITS];
        limbs.push(10u32.pow((exponent % LIMB_DIGITS) as u32));
        BigInt::from_parts(false, limbs)
    }

    /// How many decimal digits the magnitude has; zero has none.
    pub fn digit_count(&self) -> usize {
        match self.limbs.last() {
            None => 0,
            Some(top) => (self.limbs.len() - 1) * LIMB_DIGITS + top.to_string().len(),
        }
    }

    /// Fault unless the value is within the ceiling.
    pub fn checked(self, operation: &str) -> BigInt {
        if self.digit_count() > MAX_DIGITS {
            crate::fault(
                "overflow",
                &format!("{operation} result has more than {MAX_DIGITS} digits"),
            );
        }
        self
    }

    pub fn is_zero(&self) -> bool {
        self.limbs.is_empty()
    }

    pub fn is_negative(&self) -> bool {
        self.negative
    }

    pub fn add(&self, other: &BigInt) -> BigInt {
        if self.negative == other.negative {
            return BigInt::from_parts(self.negative, add_magnitudes(&self.limbs, &other.limbs));
        }
        // Opposite signs: the larger magnitude wins, and keeps its sign.
        match compare_magnitudes(&self.limbs, &other.limbs) {
            Ordering::Equal => BigInt::default(),
            Ordering::Greater => {
                BigInt::from_parts(self.negative, sub_magnitudes(&self.limbs, &other.limbs))
            }
            Ordering::Less => {
                BigInt::from_parts(other.negative, sub_magnitudes(&other.limbs, &self.limbs))
            }
        }
    }

    pub fn abs(&self) -> BigInt {
        BigInt::from_parts(false, self.limbs.clone())
    }

    pub fn neg(&self) -> BigInt {
        BigInt::from_parts(!self.negative, self.limbs.clone())
    }

    pub fn sub(&self, other: &BigInt) -> BigInt {
        self.add(&other.neg())
    }

    pub fn mul(&self, other: &BigInt) -> BigInt {
        BigInt::from_parts(
            self.negative != other.negative,
            mul_magnitudes(&self.limbs, &other.limbs),
        )
    }

    /// Quotient truncated toward zero and remainder with the dividend's sign,
    /// so that a == q * b + r. The caller has already refused a zero divisor.
    pub fn div_rem(&self, other: &BigInt) -> (BigInt, BigInt) {
        let (quotient, remainder) = divide_magnitudes(&self.limbs, &other.limbs);
        (
            BigInt::from_parts(self.negative != other.negative, quotient),
            BigInt::from_parts(self.negative, remainder),
        )
    }
}

impl BigInt {
    /// The square root rounded down, by Newton's method on whole numbers. The
    /// caller has already refused a negative value. Starting at or above the
    /// root, each step lands closer and never below it, so the first step that
    /// fails to go lower has found it.
    pub fn isqrt(&self) -> BigInt {
        if self.is_zero() {
            return BigInt::default();
        }
        let two = BigInt::from_i64(2);
        let mut root = BigInt::pow10(self.digit_count().div_ceil(2));
        loop {
            let next = root.add(&self.div_rem(&root).0).div_rem(&two).0;
            if next >= root {
                return root;
            }
            root = next;
        }
    }
}

impl BigInt {
    /// The magnitude times a small factor, plus a small addend: one step of
    /// reading digits in a base. The result is never negative.
    pub fn mul_small_add(&self, factor: u32, addend: u32) -> BigInt {
        let mut limbs = Vec::with_capacity(self.limbs.len() + 1);
        let mut carry = addend as u64;
        for limb in &self.limbs {
            let value = *limb as u64 * factor as u64 + carry;
            limbs.push((value % BASE) as u32);
            carry = value / BASE;
        }
        if carry > 0 {
            limbs.push(carry as u32);
        }
        BigInt::from_parts(false, limbs)
    }

    /// The magnitude divided by a small divisor: the quotient, never negative,
    /// and the remainder. One step of writing digits in a base.
    pub fn div_rem_small(&self, divisor: u32) -> (BigInt, u32) {
        let mut quotient = vec![0u32; self.limbs.len()];
        let mut remainder: u64 = 0;
        for (index, limb) in self.limbs.iter().enumerate().rev() {
            let value = remainder * BASE + *limb as u64;
            quotient[index] = (value / divisor as u64) as u32;
            remainder = value % divisor as u64;
        }
        (BigInt::from_parts(false, quotient), remainder as u32)
    }
}

impl Ord for BigInt {
    fn cmp(&self, other: &BigInt) -> Ordering {
        match (self.negative, other.negative) {
            (false, true) => Ordering::Greater,
            (true, false) => Ordering::Less,
            (false, false) => compare_magnitudes(&self.limbs, &other.limbs),
            (true, true) => compare_magnitudes(&other.limbs, &self.limbs),
        }
    }
}

impl PartialOrd for BigInt {
    fn partial_cmp(&self, other: &BigInt) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl std::fmt::Display for BigInt {
    /// Base 10, a leading '-' for negatives: the same as Python's `str(int)`.
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let Some((top, rest)) = self.limbs.split_last() else {
            return f.write_str("0");
        };
        if self.negative {
            f.write_str("-")?;
        }
        write!(f, "{top}")?;
        for limb in rest.iter().rev() {
            write!(f, "{limb:09}")?;
        }
        Ok(())
    }
}

// -- magnitudes: little-endian base-10^9 limbs, no trailing zero limbs -------

fn trimmed(mut limbs: Vec<u32>) -> Vec<u32> {
    while limbs.last() == Some(&0) {
        limbs.pop();
    }
    limbs
}

fn compare_magnitudes(a: &[u32], b: &[u32]) -> Ordering {
    if a.len() != b.len() {
        return a.len().cmp(&b.len());
    }
    for (x, y) in a.iter().rev().zip(b.iter().rev()) {
        if x != y {
            return x.cmp(y);
        }
    }
    Ordering::Equal
}

fn add_magnitudes(a: &[u32], b: &[u32]) -> Vec<u32> {
    let mut out = Vec::with_capacity(a.len().max(b.len()) + 1);
    let mut carry = 0u64;
    for i in 0..a.len().max(b.len()) {
        let sum = carry + *a.get(i).unwrap_or(&0) as u64 + *b.get(i).unwrap_or(&0) as u64;
        out.push((sum % BASE) as u32);
        carry = sum / BASE;
    }
    if carry > 0 {
        out.push(carry as u32);
    }
    out
}

/// a - b, where a >= b.
fn sub_magnitudes(a: &[u32], b: &[u32]) -> Vec<u32> {
    let mut out = Vec::with_capacity(a.len());
    let mut borrow = 0i64;
    for (i, limb) in a.iter().enumerate() {
        let mut difference = *limb as i64 - borrow - *b.get(i).unwrap_or(&0) as i64;
        borrow = 0;
        if difference < 0 {
            difference += BASE as i64;
            borrow = 1;
        }
        out.push(difference as u32);
    }
    trimmed(out)
}

fn mul_magnitudes(a: &[u32], b: &[u32]) -> Vec<u32> {
    if a.is_empty() || b.is_empty() {
        return Vec::new();
    }
    let mut out = vec![0u32; a.len() + b.len()];
    for (i, x) in a.iter().enumerate() {
        let mut carry = 0u64;
        for (j, y) in b.iter().enumerate() {
            // At most (10^9 - 1)^2 + 2 * (10^9 - 1), well inside a u64.
            let current = out[i + j] as u64 + *x as u64 * *y as u64 + carry;
            out[i + j] = (current % BASE) as u32;
            carry = current / BASE;
        }
        let mut k = i + b.len();
        while carry > 0 {
            let current = out[k] as u64 + carry;
            out[k] = (current % BASE) as u32;
            carry = current / BASE;
            k += 1;
        }
    }
    trimmed(out)
}

fn mul_small(a: &[u32], factor: u32) -> Vec<u32> {
    mul_magnitudes(a, &trimmed(vec![factor]))
}

/// Long division, one base-10^9 digit of the quotient at a time. Each digit is
/// found by binary search: the largest d with divisor * d <= the running
/// remainder. Thirty steps a digit is slow next to Knuth's algorithm D and
/// much easier to see is right.
fn divide_magnitudes(dividend: &[u32], divisor: &[u32]) -> (Vec<u32>, Vec<u32>) {
    let mut quotient = vec![0u32; dividend.len()];
    let mut remainder: Vec<u32> = Vec::new();
    for i in (0..dividend.len()).rev() {
        // remainder = remainder * BASE + dividend[i]
        remainder.insert(0, dividend[i]);
        remainder = trimmed(remainder);
        if compare_magnitudes(&remainder, divisor) == Ordering::Less {
            continue;
        }
        let (mut low, mut high) = (1u32, (BASE - 1) as u32);
        while low < high {
            let middle = low + (high - low).div_ceil(2);
            if compare_magnitudes(&mul_small(divisor, middle), &remainder) == Ordering::Greater {
                high = middle - 1;
            } else {
                low = middle;
            }
        }
        remainder = sub_magnitudes(&remainder, &mul_small(divisor, low));
        quotient[i] = low;
    }
    (trimmed(quotient), remainder)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn big(text: &str) -> BigInt {
        BigInt::parse(text).unwrap()
    }

    #[test]
    fn round_trips_through_text() {
        for text in [
            "0",
            "1",
            "-1",
            "999999999",
            "1000000000",
            "-1000000000000000000001",
        ] {
            assert_eq!(big(text).to_string(), text);
        }
        assert_eq!(big("-0").to_string(), "0");
        assert_eq!(big("+007").to_string(), "7");
    }

    #[test]
    fn i64_edges() {
        for value in [i64::MIN, i64::MAX, 0, -1] {
            assert_eq!(BigInt::from_i64(value).to_i64(), Some(value));
            assert_eq!(BigInt::from_i64(value).to_string(), value.to_string());
        }
        assert_eq!(big("9223372036854775808").to_i64(), None);
        assert_eq!(big("-9223372036854775809").to_i64(), None);
    }

    #[test]
    fn powers_of_ten() {
        for exponent in [0, 1, 8, 9, 10, 17, 18, 19, 100] {
            assert_eq!(
                BigInt::pow10(exponent).to_string(),
                format!("1{}", "0".repeat(exponent))
            );
            assert_eq!(BigInt::pow10(exponent).digit_count(), exponent + 1);
        }
    }

    #[test]
    fn division_signs() {
        let (q, r) = big("-7").div_rem(&big("2"));
        assert_eq!((q.to_string(), r.to_string()), ("-3".into(), "-1".into()));
        let (q, r) = big("7").div_rem(&big("-2"));
        assert_eq!((q.to_string(), r.to_string()), ("-3".into(), "1".into()));
    }

    #[test]
    fn long_division() {
        let a = big("123456789012345678901234567890123456789");
        let b = big("987654321987654321");
        let (q, r) = a.div_rem(&b);
        assert_eq!(q.to_string(), "124999998748437501153");
        assert_eq!(q.mul(&b).add(&r), a);
        assert!(r < b);
    }
}
