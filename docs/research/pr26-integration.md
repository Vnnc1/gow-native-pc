# PR 26 integration onto fix-chore (2026-11-06)

[PR 26](https://github.com/Vnnc1/gow-native-pc/pull/26) ("cleaned workspace upload") was one snapshot commit on top of
`fix-chore` 76882e7: 61 files added, 73 modified and 88 deleted. The deletions were not intentional removals; the
contributor's workspace simply predated a week of fix-chore work. The integration keeps the PR's renderer, VU1, mod
and launcher work and puts every fix-chore feature, fix and test back. Where the two disagreed, this document
records which version won and why.

No game data is available on the integration machine, so nothing here is a gameplay, FPS or frame-pacing result.
The notebook A/B plan at the end is what decides the open performance questions.

## Method

- **Runtime chain.** PR 59-94 stay under their names. The fix-chore runtime work is rebuilt on top of them as
  `zzz-*` patches. `zzz-001..006`, `zzz-100..103` and `zzz-261` were prepared before this session, and
  `zzz-200..205` and `zzz-300` were added in it. Each regenerated patch keeps its original header plus one
  integration line. The chain is checked by applying all patches in name order to a fresh clone of the pinned
  commit, the same way stage `fetch` does.
- **Repository files.** Each file the PR modified was merged per file. The base is the fix-chore revision closest to
  the PR's copy (the version the contributor started from); ours is fix-chore 76882e7 and theirs is the PR. Files
  where the PR only carried an old fix-chore version came back unchanged. Real conflicts were resolved by hand
  (table below).
- **Deleted files.** Every file the PR deleted was restored: CI, CHANGELOG, `build.sh`, docs, the diagnostic kit,
  the installer manifest and resources, and the tests.

## Runtime decisions

| Item | Decision | Reason |
|---|---|---|
| PR 59-72, 74-80, 84-94 | kept | The PR's renderer/VU1 work. The VU1 JIT experiments (76/78/79/88) and async submit (77) stay off by default. |
| PR 73-launcher-mod-manager, launcher/patches/81 | file removed | Both only described changes that are already in `launcher/` sources. 73 patched the runtime clone's unused Tobiichi launcher. |
| fix-chore 60, 61, 76, 77-80 | `zzz-004`, `zzz-261`, `zzz-005`, `zzz-100..103` | Fixes and features that run by default. |
| fix-chore 59, 68, 69, 70, 72-vu1, 73-logic | `zzz-203`, `zzz-200`, `zzz-201`, `zzz-204`, `zzz-202`, `zzz-205` | Regenerated with GNU patch fuzz and reviewed hunk by hunk. `zzz-204` was moved to patch 93's `FrameWindow::analyze()`. |
| fix-chore 67, 71, 72-sampler, 73-shader, 74, 75 | deferred, archived in `docs/research/pr26/deferred-fix-chore-patches/` | 39 rejected hunks against the PR's rewrite of `gs_hw_backend.cpp`. All were opt-in, and none had passed acceptance (the notebook preferred 67's reference). |
| `PS2X_GS_RUN` default | PR default kept (on) | The launcher already writes it. This is open: see AGENTS.md and the A/B below. |

## Defects found and fixed (`zzz-300`)

1. **Every compact single primitive was dropped (patch 89).** The new truncated-record guard required
   `sizeof(GSPrimitiveBatch)` for `Op::Vertices`. The compact encoder writes only `offsetof(GSPrimitiveBatch, state)`
   bytes, because the state travels in its own record. With `PS2X_GS_COMPACT_QUEUE` on (the default), anything
   submitted outside a run was discarded as "record payload truncated". In practice, `PS2X_GS_RUN=0` drew nothing
   through the threaded backend. `gow_gs_run_tests` caught it as soon as it was back in the build.
2. **Run encoder over-read (patch 66).** The zero tail of a 0/1-vertex primitive was read from one `GSVertex` as if
   it were three, and `base += kGsRunMaxPrims` in the loop header could wrap. Both were already fixed in fix-chore's
   66, and the PR shipped the pre-review version. ASan in `render-delivery-tests` (`submit_run/0`, `/1`, `/255`).
3. **Vertex-ring wraps drained the GPU.** In the PR, a wrap waited on the fence of the lap before last, which does
   not cover the memory being overwritten. `zzz-001` fixed that by fencing the current lap and waiting on it
   immediately, which is a full CPU/GPU sync every 32 MB. The ring now has 4 segments with one fence each, and a
   segment's fence is three segments old when it is waited on. Timeout, `WAIT_FAILED` and null fences still fall
   back to `glFinish`. A chunk larger than one 8 MB segment uses the existing spill buffers (the largest batch
   measured is 84 KB). Only the persistent map is fenced: `BufferSubData` is ordered by the driver.
4. **`glBufferStorage` without support.** Below a 4.4 context, a non-null entry point is not proof of support on
   every Windows driver. It is now kept only when `GL_ARB_buffer_storage` is listed. Otherwise the ring uses
   `BufferSubData`, and one `[gs-gl]` line per session says which path was taken. Intel HD 4000-4600 on Windows
   expose 4.3.
5. **`PS2X_GS_RUN` read once per process** (function static). It is read per `GS` again, as in fix-chore.

Repository-side regressions the PR carried, now reverted to fix-chore:

- `.gitattributes` deleted. On a Windows clone, `fetch` failed at patch 02, because the patches were checked out
  with CRLF.
- Installer replaced by a version without manifest, resources, GDI+ UI, version or `GOW_DIAGNOSTIC_SETUP`. Without
  `asInvoker`, Windows' installer detection asks for elevation for `*setup*.exe`.
- Regional `baseline.json`/`runtime.patch` rebased on the contributor's private snapshot (`gow_cancelar.cpp` hash
  `22f42cb...` exists in no chain).
- `verify` lost the countdown, movie-tail, logic-rate, run-encoder, shared-present and test-time suites, and the
  test build re-enabled FFmpeg.

## Hand-resolved merge conflicts

| File | Result |
|---|---|
| `AGENTS.md` | fix-chore sections restored. PR's graphics-coverage contract kept. Grouping and deferred-candidate text rewritten, plus a PR 26 section. |
| `launcher/qml/Main.qml` | PR's `dibujoHardware` property. fix-chore's reset of diagnostic/experimental options and its comments. |
| `launcher/src/session_diagnostics.cpp` | PR's allowlist plus fix-chore's `GOW_GS_STAGE_SPIN_US`. |
| `tools/pipeline/modules/game.ps1` | PR's distinct unreadable/corrupt manifest messages and `src`/`unity` identity. fix-chore's status line when a local profile is skipped. |
| `tools/pipeline/build.ps1` | PR's `pgo-check` stage text. Training build is `-O3` (the PR text said `-O1`, which the code does not do). |
| `tools/test/worker-ab.py` / `-tests.py` | fix-chore's stage-spin/build experiments plus the PR's regional frame PC and confirm button. `environment()` defaults to USA values. |
| `tools/test/regional-play-ui.py`, `session-game-smoke.py` | fix-chore: stricter reset check, host FPS argument. |
| `.gitignore`, docs indexes, `docs/tested-hardware.md`, `engine/README.md` | Union. |

## Validation on the integration machine

All of these ran against the integrated tree, using a fresh runtime clone with the full 114-patch chain, the pinned
LLVM 20261020 and Qt 6.8.3:

- Chain: 114/114 patches apply in name order with `git apply`, and the result is identical to the reviewed tree.
- `ps2_runtime`, `ps2_recomp` and 18 test targets build. `ps2EntryRunner` links only with recompiled game code
  (not available here). `src/gow_overrides.cpp` passes `-fsyntax-only` with the runner's flags and the existing
  generated headers.
- CTest: 16/16 (`codegen_tests`, `memory_tests`, `frame_metrics`, `dma_worker_tests`, `sound_regression`,
  `qte_hold_test`, four `qte_input_*`, `texture_budget`, `shader_program`, `software_reference`, `test_time`,
  `gs_run_tests`, `shared_present_tests`).
- Python: `pipeline_tests`, `pr26-integration-tests`, `import_test`, `prepare_test`, `worker-ab-tests`,
  `gs-run-ab-tests`, `render-delivery-tests` (12/12, ASan), `finish-countdown-tests`, `movie-tail-tests`,
  `logic-rate-tests`, `recompile-smoke`, `guest-calls`, `vu1-equivalence`, `vu1-task-tests`, `mod-runtime`,
  `register-region-tests`, `launcher-languages`, `launcher-env-contract` (against the new chain).
- PowerShell: `pipeline-tests`, `patch-stack-tests`, `build-progress-tests`, `pgo-eligibility-tests`.
- Launcher (real Qt): `gow-launcher`, `gow-session`, `gow-diagnostics` and `gow_region_tests` build;
  `regional-play-ui`, `disc-import-ui`, `loading-progress` and `session_diagnostics` pass.
- Release setup: `build.ps1 -Stages launcher,installer -NoReleaseProfile` produced
  `data/_package/gow-native-pc-setup.exe` (29,964,426 bytes, SHA-256 `5bb0737b...25befcc`). `verify_setup.py`:
  1697 files in 7 LZMS blocks, all identical to staging. The `asInvoker` manifest is embedded, and the 114
  packaged patches match `engine/patches` byte for byte (LF). Not installed or played here.
- Not run: `regional-overlays.py` needs the historical pre-overlay snapshot (`--runtime`), which is not on this
  machine. That is by design: fix-chore's baseline does not match the current chain either.

## Notebook A/B plan (i5-8265U / UHD 620, or any weaker PC)

Install with the normal setup and let it compile the game. Use the same disc, settings and resolution for every run.
Keep the laptop on AC power with the same power plan. The questions, in order:

1. **Does the PR help this machine at all?** `python -I tools/test/gs-run-ab.py --compare pr26 ...` alternates
   "every PR renderer switch off, grouping off" against "all on" (variant 1 is the shipped default).
2. **Grouping (open default).** `--compare grouping`. Promote or revert the default on p95/p99 and the longest slow
   run, not on mean FPS (see AGENTS.md).
3. **One switch at a time**, only if 1 is positive: `--compare ring|texreuse|depth-zbp|state-cache|run-state|warm-shaders`.
   The other switches stay at the shipped default.
4. **Resolution below 1x** (new in the PR): `PS2X_GS_HW_SCALE=0.5` and `0.75` against `1`. Graphics tab, internal
   resolution.
5. **Fast VU** (`--compare vu1-fast`). This changes VU1 float semantics, so report visual differences too.

Without a development checkout on the notebook, the same switches are in the launcher (Graphics, "Advanced
renderer options"). The session report records frame percentiles, stutter ratio, longest slow run and
`[gow-frame-spike]` lines (patch 93). Record every result, negative ones included, in
`docs/research/performance-experiments.md` and `docs/tested-hardware.md`.

Useful log lines: `[gs-gl] OpenGL 4.x: ARB_buffer_storage ...` (which ring path the driver got), `[gs-hw] ...
ringWraps=.. ringStalls=..` (`GOW_GS_HW_STATS=1`; stalls must stay at 0), `[gs-pub] ... run_drops=0
run_overflows=0` (`GOW_GS_COST=1`).
