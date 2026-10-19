# Two-dimensional arrays

**Goal:** Execute ordinary two-dimensional array code and show rows as front cards with staggered element cards behind them. Accessed elements slide out, reveal values, then return.

## Shared interfaces and constraints
- `Matrix` in arrays.py is an Array/list-compatible sparse outer array. `len(matrix)` is row count; `matrix.columns` is column count; `matrix[row]` is an immutable-by-convention sparse Array row. `matrix[row, column]` reads/writes scalar storage with copy-on-write rows. Deep snapshots share immutable pages safely.
- Event reads/writes/transfers use tuple `(row, column)` for individual matrix elements, int row for row headers and None for whole matrix declarations. Cell type remains element scalar type.
- Scalar pointers into matrix rows retain Pointer.index as column and add optional Pointer.row (default None); whole matrix decay pointers use base_type such as `int[3]` with index as row. Existing one-dimensional pointer semantics remain unchanged.
- Front cards display row labels; rear cards use exact element count for 1–4 columns. Five or more columns use a small fixed stack plus column-count label. No work proportional to full capacity.
- Active read/write/transfer elements are drawn at their real row/column positions and slide out far enough to read, hold, then return on the existing animation clock. Pausing/stopping/resizing clears overlays safely. Maintain semantic gray/green/purple colors, green copy arrows and red pointer markers, dark mode and independent scroll areas.
- Fold first-axis runs using whole-row equality, strictly more than 10 rows; uninitialized gaps/tails retain the existing one-dimensional boundary rule. Protect active/index/pointer target rows from folding.
- Runtime includes nested/flat initialization, inferred first dimension, local dimensions evaluated once, nested indexing, loops, compound assignment, scanf and function array parameters `a[][N]` with compatible second dimension. Reject 3D and invalid sizes or row/column bounds with CError.
- Preserve all existing uncommitted types/math/theme changes and unrelated compatibility/. Do not upload.

## Tasks
- [x] Interpreter/storage: write failing dimension/initializer/function/pointer/snapshot regressions; implement sparse Matrix and matrix indexing/parameter support.
- [x] View/motion: write failing stacked-card/reveal/bounded-items/pause tests; implement matrix layout, tuple-target integration and reveal animation.
- [x] Integration: adapt folding, index markers, formatted values, structure binding handling and examples/README; run targeted and full regression tests.
- [x] Review: inspect light/dark snapshots, exercise loop read/write reveals, build installed package and resolve independent review findings.

## Verification (2026-10-19)

- Full regression suite: 424 passed. Updated obsolete 2D rejection checks to reject 3D.
- Fresh wheel and sdist built; 14 examples executed from the installed wheel. Installed Qt boolean/theme and matrix reveal smoke checks passed.
- Inspected light/dark snapshots of element copying, closed stacks, wide rows, first-axis folding, function result pulses and the main window. Theme changes preserve active purple result fills.
- Independent review found no blocking issues; targeted runtime/integration/view checks passed (58 tests). Bounded four-element simultaneous reveals per row are documented in README; written targets and transfers receive priority.
- Changes remain local; no commit or upload performed for this feature.
