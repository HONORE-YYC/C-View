# Typedef and structures implementation plan

**Goal:** Execute typedef and structure-based teaching code, expose structure fields in the existing visualizer, and order the right rail as red structure names, purple function names, then variables.

**Architecture:** Normalize typedefs and scoped structure tags in a dedicated type registry before existing language validation. Runtime structure instances own member Cells with independent identities. Snapshot leaf fields reuse ordinary scalar/array rendering and event transfer keys; structure metadata supplies the red owner label. Existing arrays, matrix snapshots, pointers and function playback remain compatible.

**Tech stack:** Python, pycparser, PySide6, pytest.

## Constraints and interfaces
- Preserve unrelated compatibility/ and do not commit or upload unless requested for this update.
- Keep gray uninitialized/green initialized fields, purple function detail, green copy arrows and red pointers. Red small owner text appears at the upper left of member cards. Right rail: structure definitions, functions, variables. Both regions retain scrolling.
- Program.structs: mapping canonical type string to StructSpec(name: display name, fields: normalized ast.Decl list). Canonical structure types start with `struct `; identity may be encoded internally for scoped tags. Program.structure_names: ordered display-name list.
- Program._scalar_type(type_node, allow_void=False) handles normalized struct and numeric declarations and pointers. Aliases must be expanded before validation, retaining const placement and declarator binding. Struct reference nodes carry canonical tag keys so resolution is unambiguous.
- Runtime snapshot includes aggregate roots with `is_struct=True` and flattened member cells named `instance.member` or `instance.nested.member`. Leaf metadata: `struct_owner` (direct owning type display name), `struct_root` (outer instance variable name). Existing value/type/identity/declaration keys remain unchanged. UI skips is_struct roots and renders leaf cells. Arrays of structures may expose materialized member leaves with corresponding paths.
- Structure fields need distinct object identities, correct initialization, by-value copies and const protection; member pointers must survive whole-object assignment and fail after scope exit. Self-referential pointer fields allowed, recursive by-value members rejected. No dynamic allocation added.
- Unsupported aggregates/unions/bitfields/flexible arrays/function pointers produce CError rather than Python exceptions. Never accept a declaration that later breaks normal execution.

## Tasks
- [x] Type registry and language: tests first for scalar/array/pointer aliases, chained/scoped aliases, named/anonymous structs, const and self-reference; normalize AST, validate complete types and preserve source display. Files: type_registry.py, language.py, tests/test_typedef_language.py.
- [x] Runtime: tests first for declaration and aggregate initialization, member reads/writes, arrays inside structs, nested fields, dot/arrow, pointer aliasing, scanf, copies, parameters/returns and snapshot rollback. Files: struct_runtime.py, runtime.py, function_execution.py, engine.py as needed, tests/test_struct_runtime.py.
- [x] UI integration: tests first for red definition cards and rail order, leaf green/gray + owner label, array member owners, copying and theme. Files: views.py, window.py, motion.py, pointer_visuals.py, tests/test_struct_view.py. Carry structure_names in view data while preserving render positional API.
- [x] Example/docs: add one editable structure stack example showing typedef, an array member and top member, pointer parameter update; update catalogue numbering and user README supported boundaries.
- [x] Verification: run focused and complete suite, inspect light/dark actual snapshots and arrow placement, fresh package smoke, independent code review and resolve findings.

## Verification command
From workspace root use bundled Python with work/run_checks.py, e.g. `work/run_checks.py tests/test_struct_runtime.py -q --tb=short -p no:cacheprovider` with a fresh workspace basetemp. Full suite: `work/run_checks.py tests -q --tb=short -p no:cacheprovider`.

## Delivery verification — 2026-10-19
- Full regression suite: 470 passed. A pre-existing seek test was corrected to allow multiple UI time slices instead of assuming completion within one 12 ms slice.
- Fresh wheel/sdist built successfully; all 15 installed examples and installed Qt structure cards, matrix animation, bool/theme smoke checks passed.
- Inspected main-window light/dark screenshots, structure definition ordering, red member owners, array fields, and purple function detail with green transfers and red pointer markers.
- Independent review found three issues (structure-array member addresses, returned-structure member reads, parameter tag scope). All have regression tests and fixes; primary agent reviewed final fixes. Independent follow-up review was unavailable due to agent usage limit.
- Typedef runtime array bounds and temporary returned-structure array access are explicitly rejected and documented. Aggregate member creation/copy obeys the existing step budget, preserving sparse array capacity.
- Local changes only; no commit or upload for this feature.
