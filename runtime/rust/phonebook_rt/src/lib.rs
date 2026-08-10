//! The Rust runtime: one function per phonebook address.
//!
//! This is the only genuinely independent implementation in the project. The
//! interpreter and the generated Python share a single set of Python functions,
//! so they cannot disagree; Rust was written separately from the same contracts.
//! When the conformance suite says the two backends agree, this crate is what
//! that statement is about.
//!
//! # Two conventions hold everywhere
//!
//! 1. **Every function takes `&T` and returns an owned value.** Nothing is
//!    consumed, so a generated program can use a binding as many times as it
//!    likes without the emitter reasoning about ownership. The cost is some
//!    cloning. That is the deliberate v0 trade: the phonebook contracts describe
//!    values and results, not memory, and keeping ownership out of the contract
//!    is what lets one registry drive both a garbage-collected and a
//!    borrow-checked backend.
//!
//! 2. **Contract errors call [`fault`].** If an address can fail, the phonebook
//!    already said how, and the code string here is the one from
//!    `contract.errors`.

pub mod collections_;
pub mod core;
pub mod io_;
pub mod logic_;
pub mod numbers_;
pub mod text;

pub use crate::core::PbText;

/// Stop with a contracted failure.
///
/// The message shape matches the Python runtime's so that a program that fails
/// fails the same way in both backends, down to the text on stderr.
pub fn fault(code: &str, message: &str) -> ! {
    if message.is_empty() {
        eprintln!("fault: {code}");
    } else {
        eprintln!("fault: {code}: {message}");
    }
    std::process::exit(1);
}
