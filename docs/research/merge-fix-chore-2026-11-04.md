# Local main / fix-chore integration — 2026-11-04

Merged local main `37290ba` (four commits after origin/main `d28a63d`) into
fix-chore `2e0b023` (four independent commits after the same base). Both histories
are retained by a merge commit. No push or main reset was performed.

## Resolution

- Preserve both branches' AGENTS.md instructions and hardware evidence.
- Register and execute both branches' regression targets in guest-calls.cmake and verify.ps1.
- Rebase patch 67 context over patch 60: the texture-budget include, cache counters
  and trailing members now appear in its context. Its added/deleted code lines are
  byte-identical to the original patch. The initial fetch rejected this overlap
  before applying new patches; the corrected complete chain passed fetch.
- Every file changed on only one branch matches that branch's committed content.
- Preserve patch 66/67/68/71 opt-in defaults and all research drafts outside the
  ordinal patch chain. No rejected experiment is promoted by this merge.

## Validation

- `build.cmd -Stages fetch,verify`: passed, including 15 CTest groups, pipeline,
  patch-stack, methodology/save isolation, 560 countdown boundary/register/clock
  cases, codegen, VU1 backend/self-loop equivalence and bounded task replay.
- `python -I tools/disc/prepare_test.py`: 3 tests passed.
- `python -I tools/test/linux_pipeline_tests.py`: 7 tests, 1 platform skip, passed.
- Staged diff whitespace check passed outside patch files. Existing patch context
  blank lines are intentionally preserved rather than stripped as whitespace.

Local logs: `data/merge-fix-chore/verify.log` (initial context failure),
`verify-rebased.log`, `disc-prepare.log`, and `linux-pipeline.log`.

This is source integration and correctness validation, not a new FPS measurement.
The existing game runner and installers were not rebuilt. Combined visible gameplay,
GPU rasterization, frame pacing and notebook performance remain unmeasured; the
prior hardware-specific reports retain their original scope.
