# Arrays, standard libraries and qualifiers

Approved scope: inferred one-dimensional array sizes, local variable-length arrays, no application element-count limits; stdlib numeric conversion and string.h/cstring functions; const/volatile/restrict parameters. Dynamic allocation is deferred to the next version. No upload requested.

Implementation uses sparse copy-on-write array pages, lazy structure order, viewport-only array drawing and scaled scroll offsets. Capacities remain positive integers representable by the interpreter/host; actual exhaustion is reported instead of an arbitrary element cap. const applies both to parameter storage and pointed-to data, preserved across pointer copies and calls; volatile/restrict are accepted in this single-threaded model, without hardware behavior or optimizer simulation.

- [x] Regression tests for inferred/VLA/large arrays and snapshot isolation.
- [x] Sparse array storage and viewport rendering with scroll access past element 64.
- [x] Qualifier validation and read-only pointer/storage enforcement.
- [x] String and numeric standard library operations with bounds and readonly checks.
- [x] Examples, user documentation, full tests and installed-package verification.

Verification: 297 tests passed. Installed wheel exercised 12 examples. Qt screenshots checked for string operations and the last element of a million-element array. Review findings on VLA parameter dimensions and extreme scroll precision were reproduced and fixed with regression tests (including signed-64 maximum array capacity). Dynamic allocation remains deferred; changes remain local.
