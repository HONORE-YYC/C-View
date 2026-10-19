# Types, math, boolean animation and theme

**Goal:** Extend the teaching interpreter and presentation with casts, const, math, long long, bool, simplified characters, ordered examples and switchable dark mode.

**Architecture:** Preserve the interpreter and reversible event pipeline. Add bounded math builtins, token-aware C++ cast normalization, boolean result records on events, and an independent animation layer. Theme neutral surfaces centrally while retaining semantic colors.

## Constraints
- C-style casts and numeric static_cast are supported; const_cast supports existing single-level pointers without permitting writes into truly const objects. Unsupported casts must report clear errors.
- long long is signed 64-bit, with LL literals and %lld input/output; bool uses true/false in the view and numeric promotion in expressions.
- Existing const storage and pointee protection remain effective.
- math.h/cmath exposes an explicitly documented common function set, with argument/domain/overflow checks.
- Boolean evaluations animate gray to green (true) or red (false), then fade; no re-evaluation or blocking waits. Preserve short circuit and function replay semantics.
- char display omits the numeric code, including transient graphics.
- Dark mode uses black backgrounds and white neutral text; existing semantic colors stay unchanged. Toggle without resetting execution.
- Editable examples progress from fundamentals to data structures and integrate small feature demonstrations.
- Preserve unrelated compatibility/ files. No upload requested for this update.

## Tasks
- [x] Language: regression tests for casts, long long, bool, const, math and errors; implement numeric/preprocessor/runtime/I/O and event boolean recording. Verify targeted tests.
- [x] Theme: test toggle, colors and state preservation; implement central palette and all relevant editor/canvas/control neutral colors.
- [x] Animation: test gray/result/fade lifecycle, pause/stop and replay; consume Event.booleans records without evaluating code.
- [x] Examples/docs: consolidate editable examples in increasing difficulty; execute every example and document precise supported syntax/functions.
- [x] Integration: full tests, offscreen screenshots in both themes, packaging/import check and independent code review.

## Verification
- Full suite: 365 tests passed.
- Built wheel and source distribution from a fresh source copy; verified all 13 installed examples, installed Qt boolean animation and theme toggle. Removed standalone examples are absent from the wheel.
- Inspected light/dark and false-result screenshots. Dark neutral cell text retains a compact shadow for contrast against unchanged semantic fills.
- Review fixes: preserve named-cast precedence and parser-coordinate cast identity; distinguish separate equal boolean expressions while suppressing duplicate coercions; bound excessive named-cast nesting with a CError.
- This update remains local for user verification.
