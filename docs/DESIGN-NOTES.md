# Design notes

Which objection produced which decision. The two sessions this project came out
of are committed verbatim in [origins/](origins/); this file is the part worth
reading, which is where the idea got pushed on and had to change.

---

## 1. The memory chasm

> *"Python uses garbage collection; Rust uses a borrow checker. If you have a
> shared token `FILTER[lines, not_empty] -> filtered`, does `filtered` borrow
> from `lines` or clone it? To satisfy a shared contract without compilation
> errors, your generator will be forced to write highly unoptimized, clone-heavy
> Rust."*

Correct, and the suggested fix — encode mutability and ownership in the
contracts — would have been the wrong one. It moves a Rust-specific concern into
the layer that is supposed to be language-neutral, and every future backend
inherits it.

**Decision.** The v0 kernel is pure, immutable, first-order dataflow. No
mutation, no loops, no aliasing. Iteration exists only as `MAP` / `FILTER` /
`REDUCE` / `SORT` / `UNIQUE`. With no aliasing there is no ownership question to
answer, so the contracts never have to mention memory.

**What it costs.** The generated Rust does clone. Every runtime function takes
`&T` and returns an owned value, and each local extension clones its parameters
on entry. That is real, and it is the honest price of a registry that describes
values rather than storage.

**What is still open.** Widening the kernel — mutation, in-place update,
streaming — is where the objection comes back with full force, and nothing here
solves it. It is deferred, not answered.

## 2. The DNS problem

> *"Humans are terrible at memorizing 7-digit numbers. We invented DNS because
> remembering 142.250.190.46 is miserable. The IDE plugin isn't step 3 of this
> project; it is step 1."*

Half right, and the half that is right is the important half.

The counter-argument from the session — that people once memorized hundreds of
phone numbers and used a phonebook for the rest — is true but beside the point.
The real answer is that you should never have to read a raw number *anywhere*,
including in places an IDE cannot reach: terminal output, logs, diffs, code
review, an audit report someone pastes into a ticket.

**Decision.** Name resolution is a property of the toolchain, not of one editor.
`dial show`, `dial search`, `dial next`, and `dial annotate` shipped before the
interpreter did, and `dial run --trace` prints resolved names for every call.

**Where the trace goes.** stderr, never stdout. A trace that changed a program's
output would make the cross-backend comparison meaningless.

**Still true.** An editor extension would help a lot, and there isn't one.

## 3. Leaky ecosystems

> *"How do you map `OPEN_WINDOW_WITH_WEBGL` in Python versus Rust? True
> write-once portability will be confined to a very small kernel of core logic."*

Yes. This is not a problem to be solved; it is the shape of the thing.

**Decision.** The registry covers a shared semantic subset and says so. Areas
`800` and `900` are reserved for Python-native and Rust-native escape hatches
and are deliberately empty in v0 — reserving them is an admission that the
shared zone has a boundary, made in advance rather than discovered later. The
checker rejects them with a clear message.

## 4. The PBX insight

> *"Potentially we could create a declarative type that creates an address in
> any program that lets you custom write what the number does — like a local
> directory that only works in the building. The opposite of dial 9 before the
> number to call outside."*

This turned out to be the load-bearing idea, and not for the reason it was
proposed.

It was proposed as a convenience: a place to put logic the global registry does
not have. What it actually does is make local behavior **addressable**, and
therefore countable, listable, and reviewable.

**Decision.** Area `000` is the only mechanism for user-defined behavior in the
language. There are no lambdas. A predicate passed to `FILTER` is an address —
`300-0000002@[lines, 000-0000001]` — which means every piece of custom logic in
any program has a number, a name, a declared signature, and a body you can
print.

Consequences that fell out of it:

- higher-order functions exist without inventing lambda syntax;
- every extension compiles to a plain `def` / `fn` in both backends;
- recursion is rejected by the checker, so extensions terminate without a
  totality argument;
- and the audit model below becomes possible at all.

## 5. Anti-obfuscation

> *"Using deterministic immutable addresses means obfuscation of what code does
> becomes much harder. If you see a 000 you know to examine directly. Otherwise
> the phonebook-style listing lets even a person who can't read code understand
> what the program intends to do."*

This is the strongest claim in either session, and it is nearly right. The
version that survives contact with the implementation is narrower:

**What holds.** A program's capabilities are computable, not inferable. Global
addresses have frozen contracts declaring their effects, so `dial audit` reports
what a program *can* do without executing it or parsing intent out of names.
Custom behavior is confined to `000`, so the set of code a human must read is
enumerable, complete, and printed in full.

**What does not hold.** "Structurally prohibits obfuscation" is too strong. A
`000` extension can be as convoluted as anyone likes, and the auditor makes no
claim about what one does — only that there are exactly two of them and here
they are. Intent is legible at the level of the flow, not at the level of a
local function's insides.

**Decision.** The report says exactly that, in those words, and a test asserts
the wording stays honest. Overclaiming here would be the fastest way to make the
whole idea untrustworthy.

## 6. The agentic angle

> *"If manual syntax typing is the cursive of the 21st century, LLMs are wasting
> compute generating perfect cursive. Zero hallucinated syntax; context window
> efficiency; a tokenized semantic graph is easier for an agent to validate."*

Plausible, and untested here. What this repo can say concretely:

- the address space is closed and enumerable, so an invalid call is a lookup
  failure rather than a plausible-looking mistake;
- `dial check` validates a whole program against contracts without running it,
  so generated output is verifiable before execution;
- `dial audit` gives a reviewer a capability report rather than a diff to read.

Those are the properties an agent would want. Whether models actually generate
better `.phone` than Python is an empirical question nobody in either session
tested, and neither did we. It is not a claim this repo makes.

---

## Decisions nobody objected to but that turned out to matter

**One Python implementation, not two.** The interpreter and the generated Python
call the same `phonebook_rt` functions. They cannot drift, which means the only
genuinely independent implementation in the project is Rust — and that is
exactly what the conformance suite is for. Two implementations that agree is
evidence; three where two share a code path is the same evidence dressed up.

**Contracts pin behavior, not just types.** `DIV` truncating toward zero is not
a type-level fact, and neither is `ENTRIES` sorting by key. Those notes are
hashed into the immutability ledger along with the signature, because they are
equally part of the promise. Discovering this cost a re-freeze during
development: changing a note *is* changing the contract, and the ledger said so.

**Conformance written in the language it tests.** `tests/conformance/*.phone`
plus committed `.expected` files, run through all three paths. A serialized
call/response fixture format would have needed a separate harness per backend
and would not have exercised the emitters at all.

**`FIRST` and `GET` take fallbacks.** v0 has no optional type. Making the
partial operations total by construction was cheaper than introducing one, and
it means no address in the registry can fail on a missing value.
