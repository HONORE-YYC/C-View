# Types and interactive input implementation plan

Approved design: add long/long int, char, and scanf with a modal input prompt at execution; retain double. Existing playback, functions, pointers and coloring must keep working. No GitHub upload is requested for this change.

Architecture: numeric value subclasses retain long/char metadata without changing snapshots; a separate formatted I/O module parses formats and reads a buffered input stream supplied by the UI. Input is requested only during execution, never while replaying recorded function events. Cancel restores the current action and pauses playback.

Teaching model: signed 64-bit long, 8-bit unsigned char, existing signed 32-bit int. These explicit platform-independent choices are documented. scanf supports d/ld/f/lf/c/s and field widths; printf adds ld/lf/c/s. Strings are bounded char arrays, not a new string type.

- [x] Add failing runtime tests for types, literals, formatting, scanf, pointers and function replay.
- [x] Extend language validation and numeric semantics; initialize and display char arrays.
- [x] Implement buffered formatted input with matching failure, capacity/type checks and cancellation rollback.
- [x] Connect modal input to playback, stop timer during the dialog, retain callback after reset.
- [x] Add editable example and user-facing documentation; run full tests and offscreen GUI checks.

Verification: 267 tests passed; actual Qt input/cancel/retry and screenshot checked; wheel and source distribution built, installed wheel exercised all 10 examples. Review found long array capacity handling; fixed with regression test. Large negative literal promotion also fixed with regression test. Changes remain local.
