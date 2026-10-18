# Array interval folding

User design: fold runs of more than ten uninitialized cells between assigned cells or following an assigned cell, and runs of more than ten equal initialized values. Show `...` with an upper bracket/count. Keep leading uninitialized cells uncompressed. Preserve active statement and pointer/structure marker targets so animations remain meaningful.

Implementation: sparse-page run iterator, compact random-access display layout, original-index box keys, bracket rendering using existing Qt canvas. No runtime changes or upload requested.

- [x] Add threshold, gap/tail, leading gap, equal-value, sparse-billion and pointer tests.
- [x] Implement sparse interval folding and viewport drawing with bracket labels/tooltips.
- [x] Update scrolling test fixtures to use nonrepeated values; retain huge uncompressed scrolling coverage.
- [x] Verify full tests, actual screenshots and installed package.

Verification: 302 tests passed; actual Qt screenshot checked; wheel/source distribution and installed 12-example workflow passed. Changes remain local.
