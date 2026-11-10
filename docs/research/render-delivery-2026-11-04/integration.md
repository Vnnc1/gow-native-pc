# Patch 66 integration and laptop comparison — 2026-11-04

This follows the [delivery review](README.md). Patch 66 is rebased directly onto this project's 01–58 series.
The ring buffer, texture-reuse/shuffle changes, JIT fast arithmetic changes and cost diagnostics in delivery
patches 59–65 are not imported. The integration fixes the default-vertex tail overread and preserves
`PS2X_GS_RUN=0` as the individual-submission reference. The switch is read per GS instance after environment setup.
Grouping is **opt-in** (`PS2X_GS_RUN=1`); individual submissions remain the default because the last measured pair
regressed in p95/p99 and audio underruns. Higher mean FPS alone does not pass the frame-pacing acceptance gate.

## Validation scope

- The complete ordinal chain applies through `build.cmd -Stages fetch`.
- AddressSanitizer checks of the integrated encoder: 5/5 pass, including zero/one-vertex tails and 129 primitives.
- `tools/test/gs_run_tests.cpp` compares actual frontend/worker commands, draw states and all vertex fields with
  grouping on/off, compact queue on/off, a one-chunk queue, 64-primitive splits, publication boundaries, CLUT,
  transfers/uploads, TEXFLUSH, FINISH, presentation, VRAM access and backend replacement. It is a CPU command
  parity test, not a GPU rasterization test. It is included in the normal `verify` stage.
- `tools/test/gs-run-ab-tests.py` protects complete measurement windows and private disc/card construction.
- `build.cmd -Stages fetch,build,verify` completed successfully: all 11 CTest groups passed, along with pipeline,
  disc import, guest-call/codegen, VU1 backend equivalence and bounded task capture/replay checks.
- Two separate 100-second background capture sessions (grouping off/on) reached `state=11 levelReady=1`, produced
  ship-combat images, and exited with code 0 without forced termination or queue anomalies. Visual inspection found
  no obvious corruption. Animated poses differ; these screenshots are not byte-equivalence evidence.

The initial `configure,sync,build` took 1,794.257 seconds (70.005 configure, 11.358 sync, 1,712.374 build).
This rebuilt the older installed 01–29f-era binary onto the current base plus 66; it is not patch 66's isolated
incremental build cost. Both A/B modes below use the same newly compiled binary, so the other base updates do not
constitute an apparent patch-66 speedup.

## Measurement protocol

Use `tools/test/gs-run-ab.py` with the same final binary for both modes. Three pairs alternate 0/1, 1/0, 0/1.
Each session lasts 120 seconds; only complete windows starting after 60 seconds are summarized. Hidden window
(the user explicitly requested background testing),
audio enabled, fixed 1x internal resolution, 1280x720 output, no FXAA, optional fast arithmetic disabled,
in-process VU1 JIT enabled, asynchronous GS FINISH enabled and large-VIF1 barrier disabled.
Frames-only diagnostics use the USA/PT-BR frame PC from the game profile. Expensive cost timers and VU1
verification/capture are disabled. Screenshot sessions are separate and excluded from the FPS comparison.

Each session copies its own ELF/TOC/IRX inputs and uses empty private mc0/mc1 directories, a private `GOW_MC0`
and a private `GOW_SAVES_DIR`. Only the profile's read-only PAK inputs are hardlinked. Player cards and save
directories are excluded, and their content hashes/sizes/mtimes are checked after each session.

Report FPS from guest frames, not host presents. p50/p95/p99 values are medians of complete-window percentiles,
not percentiles of all session frames pooled together. Also report >50 ms and >100 ms interval rates per
1,000 observed intervals. Real-time scripted input does not guarantee identical animation or scene trajectories.
These results cannot be transferred to the RX 580 or used to declare universal 60 FPS support.
They also do not satisfy the separate visible-play acceptance gate.

Build, regression and measurement evidence is retained locally under ignored `data/patch66-integration/`.
Hardware: Intel Core i5-8265U (4 cores/8 threads), about 24 GiB RAM, Windows 11 Pro 22631, Intel UHD 620 driver
27.20.100.9664 selected by the game. A Radeon 520 is also installed but was not the reported rendering adapter.
The notebook was on AC with 100% battery and its existing custom power plan. Temperatures/clocks and other desktop
applications were not controlled. The RX 580 is not involved in this experiment.

## Results

All six runs passed functional checks: gameplay before warm-up ended, effective switch confirmed, 11 complete
measurement windows each, exit code 0, no forced termination, no queue anomaly and unchanged original save inventory.
Each contributed about 55 seconds of complete post-warm-up windows. No run was discarded.

| Order | Grouping | Guest FPS | Window p95 median (ms) | Window p99 median (ms) | Intervals >50 ms | >100 ms | Maximum (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Off | 38.238 | 34.441 | 43.754 | 11 | 0 | 69.230 |
| 2 | On | 39.872 | 34.332 | 39.159 | 2 | 0 | 81.130 |
| 3 | On | 36.317 | 37.287 | 45.308 | 16 | 2 | 130.196 |
| 4 | Off | 32.669 | 43.827 | 53.087 | 37 | 1 | 102.057 |
| 5 | Off | 25.413 | 50.243 | 68.690 | 171 | 15 | 176.359 |
| 6 | On | 26.116 | 63.274 | 86.469 | 164 | 11 | 215.599 |

Mean run FPS: **32.107 off → 34.101 on (+6.213%)**. The three paired FPS changes were +4.274%, +11.165% and +2.766%.
This is a descriptive result for these background runs, not a statistically isolated or universal performance gain.
The decline across the session, present in both modes, is substantial; temperature, clocks, competing desktop load
and scene differences were not isolated, so this experiment cannot establish its cause. AC status remained 1 in
every collector sample; it was not a switch to battery power.

Across all measured intervals, >50 ms rates were 41.158 → 32.235 per 1,000 intervals; >100 ms rates were
3.007 → 2.303. However, the last pair's p95 rose **50.243 → 63.274 ms (+25.936%)**, p99 rose
**68.690 → 86.469 ms (+25.883%)**, and the maximum rose **176.359 → 215.599 ms**. Aggregate improvements do not erase
this tail regression. For reference only, medians across the three per-run window summaries were p95
43.827 → 37.287 ms and p99 53.087 → 45.308 ms; neither is a pooled percentile.

Audio was enabled throughout. Complete audio-stat windows after warm-up requested 2,640,000 frames per run:
missing counts were 0, 0, 0, 0, 7,026 and 14,628 respectively. The final slower pair therefore also had worse audio
delivery with grouping enabled. These are mixer delivery counters, not a subjective listening assessment.
Stable 60 guest FPS and smooth audio were **not achieved** on this notebook.

The original project save inventory was empty and remained unchanged in every run. No player card was supplied to
the game; all writable card/save roots were private. Test-created cards, game-derived captures and disc inputs remain
under ignored `data/`; they are not added to packages or diagnostic export allowlists.

Measured binary SHA-256: `813e8923ee8dbd8f39d4585f7b4e27b4007d9e6be88c4d161c480bcb8012f5c5`.
Final binary after changing only the default switch to opt-in:
`1264ec3e54eb718a80831aa7ce019cd0b0578e1aafc3e77af7512e1ca94ec2b5`.
The measured paths use explicit 0/1 settings; the later default change does not change either path. A default-off
regression case was added to the production test before rebuilding and rerunning the full verification stage.
Raw evidence: `benchmark/summary.json`, `benchmark/analysis.json`, each run's session files, `capture/`,
`asan-final/`, `verify.log` and `final-verify.log`, all under `data/patch66-integration/`.

## Next acceptance phases

1. Reproduce the late-session slowdown with system CPU load, CPU/GPU clocks, temperature and power-limit evidence
   collected separately; distinguish competing load, thermal behavior and scene drift rather than guessing.
2. Use a separate intrusive profiling run to identify EE/VU1/GS work and queue waits around the >100 ms intervals
   and missing audio frames. Keep those measurements out of the frames-only FPS comparison.
3. Repeat paired tests with a more stable scene/route and comparable starting conditions. Require consistent p95/p99
   and audio behavior, not just higher mean FPS, before enabling grouping by default.
4. Validate visible play with sound, first visits and heavier combat, then Intel/AMD/NVIDIA hardware separately.
   RX 580 and other tiers remain untested by this change. Do not infer them from this notebook.
5. Keep delivery patches 59–65 separate. Ring capacity/lifetime and texture span/parity gates from the original review
   remain open; importing them now would confound the result and reintroduce unvalidated rendering changes.

## Background session left running at the user's request

Follow-up: this session was stopped gracefully at 17:42:22 UTC on 2026-11-04 before the next
comparison. It is no longer running. See [the subsequent investigation](followup.md) for current results.

After the benchmark and final verification, a separate session was launched with the final binary and an explicit
`PS2X_GS_RUN=1`. It reached `state=11 pending=0 levelReady=1` with its window hidden. It uses another private disc/card
root and bounded `gow-session` logs under `data/patch66-integration/background/`; its metrics are not part of the A/B
results above. `control.json` identifies the helper and stop-request path. The original project save inventory was
checked again after gameplay started and remained unchanged.

To stop only this test session gracefully, run `data/patch66-integration/background/stop-test.ps1`, which writes
the helper's `session/stop.request`. Do not kill unrelated game processes. This is ongoing observation, not a
completed long-duration stability result; the fixed input script is not a whole-game playthrough.
