# Scalar scheduling replay repetition — 2026-11-05

The maintainer requested resumption of performance testing. This bounded follow-up
used the preserved reference and scalar candidate executables, without installing
the draft or changing the active runtime, launcher settings, power plan or cards.
Host: Intel Core i5-8265U; Windows enumerates Intel UHD 620 and Radeon 520. This
CPU-only replay does not identify the GPU used by gameplay.

## Reproduction and results

Run `python -I tools/test/vu1-task-ab.py --reference
data/vu1-combat-followup/replay-reference.exe --candidate
data/vu1-combat-followup/replay-scalar.exe --corpus
data/scene-bottleneck/task-capture/01-countdown-0/tasks.bin --output
data/vu1-combat-followup/scalar-replay-20261105` as one command.

Five alternating pairs, 100 repetitions per record, passed captured-baseline and
work-accounting checks for all 32 records. Median sums of per-record warm medians
were 490.9 us reference and 468.2 us candidate: 4.62% less isolated time. All five
pairs favored the candidate. This repeats the direction of the earlier 9.61%
result, with a smaller magnitude; it is not a frame-time or FPS measurement.
Executable and corpus hashes are preserved in the local summary.json.

`vu1-task-replay.py` also ran the candidate against the same corpus with ten
repetitions on hybrid, JIT, helper, SSE and exact: all five passed their respective
captured baselines. Native/exact differences remain separate; this is not proof
that the backends produce identical results to each other.
Evidence: `data/vu1-combat-followup/scalar-backends-20261105/summary.json`.

## Acceptance remains open

No source optimization was installed or promoted. The preserved draft only
extracts scalar scheduling loops from the common chain frame, but these runs do
not replace randomized generated-module/JIT equivalence, full verify, a rebuilt
game or same-scene gameplay. Combat anchoring, p95/p99, audible output, sustained
sessions and independent GPU tiers remain unvalidated. No stable-60-FPS claim.
Next: complete the checkpoint's encounter-anchor correctness gates and expanded
scalar equivalence before exporting a numbered patch or comparing gameplay FPS.

## Patch 72 implementation and validation

Implemented `engine/patches/72-vu1-scalar-outline.patch` and rebuilt the installed
Release runner. The patch extracts only scalar scheduling loops; scalar issue
order, timing and the zero-scalar fast path remain unchanged. The slot population
code stores either an inline count within capacity or the 0xFF overflow sentinel.
No generator semantics, launcher switches or experimental renderer defaults change.

`build.cmd -Stages fetch,sync,build,verify` passed: ordinal patch application,
Release build, all 13 CTest groups, generated-module/JIT/helper/SSE equivalence,
special values, self-loop budget/depth exits and procedural task replay.
Log: `data/scalar-72-validation.log`. Initial patch publication used CRLF and
failed the cached-index application check; converting the patch to LF fixed it
before the successful full run.

Gameplay acceptance did not pass. Both A/B attempts stopped on the reference:
the 90-second run failed graceful shutdown; the 60-second retry exited cleanly
but failed the trajectory gate. No paired FPS result is valid. Evidence:
`data/vu1-combat-followup/scalar-gameplay-72` and `scalar-gameplay-72-short`.

The rebuilt candidate's separate visible/audio 100-second smoke reached gameplay,
exited zero gracefully and completed 2000 VU1 checks with zero mismatches. Nine of
eleven checks passed; native/JIT metrics were absent from the collector's expected
fields, so the smoke suite returned failure. Audio metrics were present, which
does not establish audible quality or absence of underruns. Evidence:
`data/gow1/logs/session-game-20261105-133001` and `data/scalar-72-smoke.log`.

The optimization is implemented locally, not accepted for public performance
promotion. Resolve diagnostic metric collection and reproducible scene/shutdown
failures before claiming gameplay gains. Sustained combat and other GPUs remain
open. The preserved reference executable remains available for comparison.

The rebuilt verify executable also passed the 32-record corpus on hybrid/JIT/helper/SSE/exact with ten repetitions: data/vu1-combat-followup/scalar-72-rebuilt-replay/summary.json.
