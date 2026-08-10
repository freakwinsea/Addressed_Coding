# The audit model

What `dial audit` proves, how it proves it, and — just as important — what it
does not claim.

## The two structural facts

Everything here rests on two properties of the language, neither of which is
available in an ordinary one:

1. **Every global address has a frozen contract that declares its effects.**
   `500-0000001 READ_TEXT_FILE` says `filesystem-read`, and it cannot stop
   saying that without a contract version bump, which the immutability ledger
   enforces in CI. So a program's capability set is *computed* from the
   registry, never inferred from names or guessed at by reading code.

2. **Local `000` extensions are the only place user-defined behavior can live.**
   There are no lambdas, no anonymous functions, no dynamic dispatch, no `eval`.
   A predicate is an address. Which means the set of code a human has to read is
   finite, enumerable, and printable.

Together those give you a capability report and a bounded review surface, from
static text, without running anything.

## What the report contains

```
CAPABILITIES        computed from contract.effects, grouped by capability.
                    Categories with no v0 addresses (network, process) still
                    appear, so "not used" is a statement rather than a silence.

INTENT              the program's calls in order, with addresses resolved to
                    names and literal arguments shown. Readable without knowing
                    any target language.

LOCAL EXTENSIONS    every 000 address, with its complete source. This is the
                    review surface, in full.

NOTES               findings that deserve a human's attention:
                      dynamic-path   a file operation whose path is computed at
                                     run time rather than written literally
                      nested-local   a local extension that calls other local
                                     extensions

VERSION POLICY      which addresses resolve with @latest and could therefore
                    change behavior when an implementation is upgraded.

VERDICT             needs review, or pure computation and console output.
```

`--strict` exits non-zero when a program has any local extension or any
capability beyond the console. That makes it usable as a gate: *this program is
pure computation plus stdout, and CI can prove it.*

## What it claims

- The capability list is **complete**. A program cannot touch the filesystem
  without dialing an address whose contract declares it, and there are four such
  addresses in the whole registry.
- The review surface is **bounded and enumerated**. Custom behavior has nowhere
  to live except a `000` address, and every one is printed.
- Intent is **legible without reading code**. `READ_TEXT_FILE → SPLIT_LINES →
  FILTER → MAP → WRITE_TEXT_FILE` means what it says, in any language the
  program is later compiled to.
- Obfuscation by naming does **not** work. Renaming a binding changes nothing:
  the address is the identity, and the report prints the address.

## What it does not claim

**It does not claim a local extension is safe.** A `000` extension can be as
convoluted as its author likes. The report tells you there are exactly two of
them and shows you both; it does not tell you they are fine. That is a human's
job, and the value of the model is that the job is small and cannot silently get
bigger.

**It does not claim the program is secure.** Nothing here reasons about what
data flows where, whether a file path is sensitive, or whether writing a file is
appropriate. It reports capability and intent, not risk.

**It is not a sandbox.** The audit is static. Running the program still runs it.

**It says nothing about the runtime.** The contracts describe what each address
promises; whether a backend implementation keeps that promise is what the
conformance suite is for, not the auditor.

These limits are stated in the tool's own output, and `tests/test_audit.py`
asserts the wording stays honest. Overclaiming would be the fastest way to make
the whole idea untrustworthy — a report that says "safe" and is wrong once is
worse than no report.

## Worked example

`examples/audit_demo.phone` is written to look like a log tidier. Reassuring
names, a plausible shape. Run the auditor on it:

```bash
dial audit examples/audit_demo.phone --strict
```

The report shows a read of `credentials.txt`, a write to a dotfile under a
different name, and two local extensions — one of which turns out to be doing
character substitution on every line. None of that is hidden anywhere, because
there is nowhere to hide it: the effects come from frozen contracts and the
custom logic has an address.

The "encoding" is a joke cipher on a fake file. The point is the report.

## Using it in CI

```yaml
- run: dial audit path/to/program.phone --strict
```

Fails when the program gains a local extension or a filesystem capability it did
not have before. For a program that is meant to stay pure computation, that is a
meaningful regression gate — and unlike a lint rule, it cannot be worked around
by restructuring the code, because the capability comes from the address.
