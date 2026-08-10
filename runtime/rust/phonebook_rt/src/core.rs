//! Area 100 — core.

use std::collections::BTreeMap;
use std::io::Write;

/// The canonical text form of a value: address 100-0000005, as a trait.
///
/// Rust has no `any`, so the contract's "renders any value" becomes a bound.
/// Note `true` / `false`: Rust already agrees with the contract here, whereas
/// Python does not. Each backend bends where it must.
pub trait PbText {
    fn pb_text(&self) -> String;
}

impl PbText for i64 {
    fn pb_text(&self) -> String {
        self.to_string()
    }
}

impl PbText for bool {
    fn pb_text(&self) -> String {
        if *self { "true" } else { "false" }.to_string()
    }
}

impl PbText for String {
    fn pb_text(&self) -> String {
        self.clone()
    }
}

impl<T: PbText> PbText for Vec<T> {
    fn pb_text(&self) -> String {
        let inner: Vec<String> = self.iter().map(|item| item.pb_text()).collect();
        format!("[{}]", inner.join(", "))
    }
}

impl<K: PbText, V: PbText> PbText for (K, V) {
    fn pb_text(&self) -> String {
        format!("({}, {})", self.0.pb_text(), self.1.pb_text())
    }
}

impl<K: PbText + Ord, V: PbText> PbText for BTreeMap<K, V> {
    fn pb_text(&self) -> String {
        let inner: Vec<String> = self
            .iter()
            .map(|(key, value)| format!("{}: {}", key.pb_text(), value.pb_text()))
            .collect();
        format!("{{{}}}", inner.join(", "))
    }
}

/// 100-0000005 TO_TEXT
pub fn to_text<T: PbText>(value: &T) -> String {
    value.pb_text()
}

/// 100-0000001 PRINT — a single U+000A, never CRLF.
pub fn print_value<T: PbText>(value: &T) {
    let stdout = std::io::stdout();
    let mut handle = stdout.lock();
    let _ = handle.write_all(value.pb_text().as_bytes());
    let _ = handle.write_all(b"\n");
}

/// 100-0000002 PRINT_LINES — an empty list writes nothing at all.
pub fn print_lines<T: PbText>(lines: &[T]) {
    let stdout = std::io::stdout();
    let mut handle = stdout.lock();
    for line in lines {
        let _ = handle.write_all(line.pb_text().as_bytes());
        let _ = handle.write_all(b"\n");
    }
}

/// 100-0000003 SELECT — eager; both arms already exist as values.
pub fn select<T: Clone>(condition: &bool, when_true: &T, when_false: &T) -> T {
    if *condition {
        when_true.clone()
    } else {
        when_false.clone()
    }
}

/// 100-0000004 IDENTITY
pub fn identity<T: Clone>(value: &T) -> T {
    value.clone()
}

/// 100-0000006 ASSERT
pub fn assert_(condition: &bool, message: &str) {
    if !*condition {
        crate::fault("assertion_failed", message);
    }
}
