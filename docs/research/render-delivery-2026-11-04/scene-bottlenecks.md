# CPU/GPU scene isolation and FINISH countdown candidate (2026-11-04)

## Scope and safety

Notebook: i5-8265U (4 cores / 8 threads), 24 GiB, Intel UHD 620 OpenGL renderer.
The AMD adapter and the separate RX 580 desktop are not measured here. Tests run
hidden through `gow-session` with audio enabled, private blank cards, copied ELF/
TOC/modules and read-only PAK hardlinks. Player card/save hashes and timestamps
must stay unchanged; only the test's own child is stopped gracefully.

No power-plan changes, other-application termination or graphics-quality reduction
are part of the candidate. Patches 66 and 67 remain off in both countdown variants.

## Measurement corrections

- `gs-run-ab.py --scene ship_guard` reads the game profile's initial-ship encounter
  script. It holds L1, refills test health and sends no movement/camera input after
  gameplay starts. This is an animated combat encounter, **not a frozen replay**.
- Each measured run must contain at least three player samples, gameplay state 11,
  no movie, only the declared ship zones, and a cross-run position envelope within
  the declared tolerance. The current 50-unit envelope allows the small observed
  block/knockback movement; it does not establish identical enemy animation.
- Earlier exploratory runs used a stricter 25-unit envelope. The stationary guard
  pilot moved 31.3 units on Z and was rejected. A walk-to-corner experiment also
  failed across resolutions because the slower run was still settling. Their FPS
  values must not be presented as successful scene-matched A/B results.
- `--compare scale` changes only internal resolution (1x / 2x). Session provenance
  records the actual scale and the runtime's scale message is checked.
- Warmup-overlapping intervals and process teardown are excluded. Host CPU is
  measured separately from total-system CPU; 100% process CPU means one logical
  CPU. GPU numbers are PDH engine busy time, not shader execution time.
- Frame percentiles are medians of per-window percentiles, not pooled quantiles.
- The Windows sampler now reports thread CPU time separately from sampled RIP
  occupancy. Samples include sleeping/blocked threads. CPU end times are captured
  before symbol resolution; symbol lookup duration cannot inflate them. Missing
  PDB symbols retain module-relative addresses for `llvm-nm` resolution.

## Source-grounded findings

The initial, intrusive profile found substantial GameThread condition-variable
wait occupancy and a hot generated function at guest PC `0x17A2A0`. In that
function, the `0x17A32C` countdown repeatedly decrements a register while waiting
for GS completion. The existing scheduler already provides
`advanceQuietRepeated`: it stops before the earliest timer, IOP batch, event or
slice deadline and refuses batching when pending/changed-limit flags are set.

Patch 68 wraps only the countdown's resume entries (`0x17A328`, `0x17A32C`). It
folds quiet 32-cycle checkpoints, preserves signed low-register writes and upper
register halves, and delegates the last decrement, flag poll and guest calls to
the generated reference. Non-quiet checkpoints retain the full scheduler path.
`GOW_FINISH_COUNTDOWN=1` opts in; default/0 keeps the reference.

The production-body differential test covers 560 combinations of countdown values,
32-cycle boundaries, pending/changed flags and both entry PCs. It compares all
register halves, PC, quiet/deferred/EE cycles and the first full-checkpoint boundary.
This isolated test does not execute the game's flag polling or replace gameplay
and timer/IOP regression gates.

GS thread samples also include vertex conversion, command execution and Intel
OpenGL driver work. VU1 work and GS-stage queue/locking are separate CPU candidates.
The old GS capture/replay cannot yet establish a faithful hardware replay:
`GSHwBackend` does not implement the `GSBackendStateAccess` snapshot interface.
Do not use an incomplete capture as a GPU-equivalence or performance oracle.

## Evidence locations

Local, ignored evidence: `data/scene-bottleneck/`. The early `cpu-profile.txt`
thread CPU totals were collected before the end-time correction and are excluded
from utilization claims; its RIP sample locations remain exploratory evidence.
Pilot artifacts contain game images/data and are not report-export/package inputs.

## Acceptance

Keep the countdown candidate opt-in until repeated same-scene comparisons improve
frame tails and CPU cost without more missing/dropped audio frames. Hidden tests
and buffer counters cannot certify audible quality or public hardware support.
Stable 60 guest FPS, visible gameplay with sound, and independent AMD/NVIDIA tests
remain required. Do not attribute all low FPS to GPU saturation or classify lower
GPU utilization with lower FPS as an efficiency improvement.

## Diagnostic clock cleanup (patch 69)

`GSHwBackend::Impl::drawOne` read `steady_clock` on every draw even when the timed
GS dump was disabled. Patch 69 reads it only while that optional trigger is armed
and on its eligible first batch. The first-draw time origin is preserved. Draws,
GPU state, synchronization, texture quality and audio clocks are unchanged. This
removes unnecessary work by inspection; it is not a measured FPS improvement.

## Profiling result

A separate 20-second intrusive capture measured CPU time before symbol resolution.
Each percentage below is relative to **one logical CPU**, not the whole laptop:
GameThread 61.80%, VU1 worker 46.57%, GSThread 38.32%, GS-stage thread 34.16%.
GameThread wall samples include 39.77% in condition-variable waits and 6.25% in the
FINISH countdown. VU1 wall samples include 29.99% in `VU1NativeAccess::chain`.
GS samples include 12.40% vertex conversion and 7.98% render-target view mapping.
Stage samples include GIF parsing and register writes. These are sampled instruction
locations including waits; they are not CPU self-time percentages or GPU timings.

A later short combat attempt encountered 99.13% mean total-system CPU and 43.36%
mean game GPU engine load. It was rejected for position drift; its low throughput
cannot be attributed simply to GPU saturation. Do not use it as a before/after gain.

The attempted inventory pause and one-hit clearing routes do not establish a fixed
combat fixture. Their artifacts remain local, and those temporary profiles were
removed. The harness must continue to reject scene drift rather than silently
widen bounds to obtain a favorable result.

## Reproduction

The installed runner is built with the pinned llvm-mingw, Release `-O3`, portable
x86-64-v2, without PGO or ThinLTO. `fetch,build,verify` validates the ordinal stack.
Use a new output directory for every attempt:

```powershell
python -I tools/test/gs-run-ab.py --runner C:/gow-build-clang/ps2xRuntime/ps2EntryRunner.exe --output data/my-scene-ab --compare countdown --scene ship_guard --pairs 3 --seconds 120 --warmup 60 --hidden --gpu-samples
```

This command must fail if the scene contract is violated; a failed comparison is
not a performance result. `--compare scale` selects a separate 1x/2x experiment.

For exact-input CPU isolation, use `--task-capture` in a separate diagnostic run.
It records at most 32 tasks, sampled every 256 tasks after warmup, into each private
run's `tasks.bin`. That mode is intrusive and explicitly excluded from FPS claims.
Replay one corpus with `tools/test/vu1-task-replay.py`, using `gow_vu1_tasks.exe`
from the verify build. Keep the corpus under ignored data; it contains game code/
data and is never added to the diagnostic export allowlist.

## Completed exact-input replay and final validation

The final installed runner SHA-256 is
`6476be39ceb5ef33e5f0594fc0c44cb01dedd41f4bb9d02c239579913b34da35`.
Both 90-second hidden diagnostic sessions (countdown off/on) reached gameplay,
recorded exactly 32 tasks / 1,071,104 bytes, captured a GS image and exited cleanly.
They used the ordinary moving route and intrusive task/screenshot capture, so their
FPS and audio counters are **not** a matched-scene performance acceptance result.
All card/save preservation checks passed. No game process was left running after
the bounded tests completed.

One identical 32-record corpus was replayed with five repetitions per record:

| Backend | Sum of per-record warm median execution times | Reference check |
|---|---:|---|
| Hybrid native | 534.7 us | 32/32 pass |
| JIT inline | 501.4 us | 32/32 pass |
| JIT helper | 1,222.0 us | 32/32 pass |
| JIT SSE | 487.5 us | 32/32 pass |
| Exact interpreter | 12,055.7 us | 32/32 pass |

These are **isolated execution times**, excluding reconstruction, hashing and final
flush, not scene FPS. The native and exact captured baselines differ in all 32
records; each backend matched its own expected baseline, with zero new mismatches.
This small corpus does not establish whole-game accuracy or justify a new default
ISA/backend. It supplies reproducible inputs for the next VU1-chain investigation.

Final checks: ordinal patch application plus Release build and full `verify` passed,
including all 12 CTest groups, synthetic recompiler tests, memory/GS/audio/input
checks, VU1 randomized/self-loop equivalence and procedural task replay. The updated
scene/save methodology suite and all 560 countdown equivalence cases passed again.
The sampler compiled and ran against an owned test PID. `git diff --check` passed.
Evidence: `data/scene-bottleneck/patch69-build-verify.log`, `task-capture/summary.json`,
`task-replay/summary.json`, `cpu-resolved-corrected.json` and the rejected scene-run
summaries. No valid same-combat FPS delta or audible-quality improvement is claimed.
