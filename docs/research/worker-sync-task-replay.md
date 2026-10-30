# Worker waits and isolated VU1 tasks (patches 36–37)

These changes implement the measurement and capture/replay part of the optimization workflow. They do not enable
a speculative faster renderer, relax DMA ordering, or claim an FPS gain. The existing early-finish default is retained.
The reference idea is Ascension's capture/replay and verified native-task work:
https://github.com/arnaldolima1/gow-ascension-pc/blob/main/docs/MILESTONES.md (entries October 21–23, 2026).
No source code from that project is copied.

## Patch 36: attribute synchronization waits

`GOW_SYNC_DIAG=1` enables bounded per-memory-instance aggregates. The old `PS2X_GS_WORKER_DIAG=1` is an alias if the
new variable is absent. The launcher enables the new setting with detailed diagnostics. Normal FPS runs do not
read the high-resolution clock or update counters for each wait.

The previous diagnostics charged GS-stage time to the worker and only counted a wait when the worker was initially
busy. This missed a stage-only stall after the worker had already finished. The same synchronization now reports
worker and GS-stage wall time separately, including that case. Worker/stage self-wait guards and DMA completion are
unchanged. Time includes the respective mutex/condition-variable overhead; it is not CPU/GPU utilization.

- `[gow-sync-config] early_finish=... worker=... timing=...`: effective settings at memory-instance construction.
- `[gow-sync] site=... window=... syncs=... worker_waits=... stage_waits=... worker_ms=... stage_ms=... queue_peak=... final=...`:
  interval counters emitted at most once per five seconds per active site, plus remaining counters at destruction.
- Site `0` is the large VIF1 barrier, `1` aggregates MMIO synchronization, `2` aggregates other explicit waits.
- `queue_peak` is queued/in-flight worker jobs observed at synchronization entry, not the global queue maximum.
- `worker_waits`/`stage_waits` count initially busy conditions; time fields include synchronization overhead even
  when the condition is already satisfied. Overlapping waits from multiple callers must not be summed as frame time.
- `final=1` is a partial final interval. Abrupt termination can lose that final flush.

The collector parses both tags and records the explicit barrier/sync/pipeline environment settings. The raw capture
files introduced below are deliberately excluded from the session export allowlist.

## Controlled barrier comparison

After building the game and launcher in this checkout:

```powershell
& .\data\_tools\python\python.exe -I .\tools\test\worker-ab.py --mode fps --pairs 3 --seconds 120 --warmup 60
& .\data\_tools\python\python.exe -I .\tools\test\worker-ab.py --mode timing --pairs 1 --seconds 120 --warmup 60
```

The first command alternates on/off and off/on, using one hashed runner/ELF, fixed scale, FXAA off, dynamic scale off,
60 Hz host cap and audio on. Each run gets a private card; `--card <file>` copies a common initial card without
modifying it. Default input comes from the game profile. `--runner`, `--elf`, `--helper` and `--output` can select
explicit local paths. `--scale 2` is a separate graphics experiment. Avoid concurrent builds/other game instances.

Outputs are under `data/<game>/logs/worker-ab-<timestamp>/`: individual collector sessions, private cards and a
`summary.json`. Only complete windows after warm-up are averaged by duration; zero FPS is retained. Gameplay,
effective setting, normal exit and non-forced shutdown are required. Individual run values remain visible.
Real-time scripted inputs do not guarantee the same guest-frame trajectory; compare captures/scenes before making
a causal claim. Detailed timing is a separate diagnostic run, not an FPS comparison. The tool stops only its own
child through the collector. `--hidden` is for functional testing, not visible-gameplay acceptance.

## Patch 37: a local VU1 task corpus

The older `GOW_VU1N_RECORD/REPLAY` mechanism remains available. The new independent mechanism captures **fresh MSCAL
tasks after scheduler reset**. It intentionally excludes `resume`/MSCNT calls: those need a full in-flight scheduler
snapshot. Each task contains scalar/vector register input, flags, TOP/ITOP, cycle budget, microcode and VU data.
An isolated reconstruction records native and exact-interpreter digests separately. It does not modify the game's
VU state or submit captured GIF packets to the live renderer.

The digest covers registers/data, captured GIF packet bytes, PC/end behavior and additional cycle/control state.
Native versus exact arithmetic is not assumed bit-identical: `baseline_backend_differences` reports that difference,
and each replay backend must match its own recorded baseline. This is a repeatability/regression test, not a new
claim of bit-exact native/interpreter equivalence. Existing differential tests continue to apply.

```powershell
& .\data\_tools\python\python.exe -I .\tools\test\worker-ab.py --mode capture --seconds 120 --warmup 60
$testBuild = (Get-Content .\data\build-root.txt -Raw).Trim() + '-verify-clang'
& .\data\_tools\python\python.exe -I .\tools\test\vu1-task-replay.py "$testBuild\gow_vu1_tasks.exe" '<run directory>\tasks.bin'
```

Replay needs no disc, save, window or GPU context. It validates and loads the complete corpus before execution,
then runs hybrid, JIT, helper, SSE and exact modes in separate processes. JSON retains per-task results and the
slowest isolated samples, keyed by code hash and PC. Exit status is nonzero on invalid files or mismatches.

Manual recording settings:

| Variable | Default / bound |
| --- | --- |
| `GOW_VU1_TASK_RECORD` | Output path; absent disables recording; existing files are never overwritten |
| `GOW_VU1_TASK_LIMIT` | 128 records, maximum 1,024; zero disables |
| `GOW_VU1_TASK_STRIDE` | Every 1,024th eligible task, clamped to at least one |
| `GOW_VU1_TASK_SKIP` | Zero eligible tasks skipped |
| `GOW_VU1_TASK_DELAY` | Zero seconds; delay measured from the recorder's first initialization |

The capture harness delays 60 seconds by default and samples every 256 tasks. It also requests one game-rendered
PPM capture ten seconds after warm-up for visual inspection. Version/record-size checks, checksums, input bounds,
a maximum 200,000-cycle task and a 1,024-record cap keep the corpus bounded (under 35 MiB).
Truncation, empty input, checksum errors and trailing bytes are errors. Version 1 is a little-endian local research
format. Keep captures under ignored `data/`; they contain game-derived bytes and must not be packaged or automatically
uploaded. Capture is intrusive because it evaluates each selected input twice; its FPS is not a benchmark.

`first_us` and `warm_median_us` measure the replay execution loop, excluding input reconstruction, output hashing
and final pipeline flush. They are isolated test costs, not game frame times. `native_blocks=0` explicitly exposes an
interpreter-only sample. Native/JIT matches alone do not validate GPU rasterization, audible sound or later scenes.

## Choosing the next optimization

First compare barrier-on/off with basic FPS accounting, then locate waits with the separate detailed run. Use a
task corpus from the slow scene to establish a regression baseline and rank candidate code hashes/PCs. A handwritten
native replacement should preserve its original path, prove matching memory/GIF/control results on the captured
corpus and procedural cases, and improve repeated visible gameplay measurements before becoming a default.

Validation commands: `build.cmd -Stages verify`, then `build.cmd -Stages launcher` and
`python -I tools/test/session_diagnostics.py launcher/build-clang/deploy/gow-session.exe`.
The verify stage includes stage-only wait accounting, worker/stage self-wait guards, barrier opt-out/small packets,
configuration snapshots, capture noninterference, all replay backends, corrupted input and deliberate digest mismatch.
Actual machine results belong in `docs/tested-hardware.md`; this document describes the contract, not test outcomes.
