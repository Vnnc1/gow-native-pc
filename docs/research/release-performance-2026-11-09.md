# Release performance investigation â€” 2026-11-09

Status: local readiness probe and player-report diagnosis, not a new optimization
or stable-60 acceptance. Branch: fix-chore. Ledger entry: PERF-06 / GAIN-11.

## Evidence from the installed build

The latest player session, `20261109-232429-669-9f90de53`, used the actual
zzz-314 runner, Xeon E5-2666 v3, RX 580 2048SP (driver 31.0.21924.61), 16 GiB,
Release x86-64-v2 without PGO. Settings included 2x, AF16, FXAA and full timed
diagnostics. It exited normally after 64.229 seconds. Six complete performance
windows starting after 30 seconds ranged from 45.8 to 60 guest Hz; four were
below 55. Their median scoped VU time was 4626.735 ms per approximately five
seconds, versus GS 2189.360 ms. The earlier 28.98-minute session
`20261109-200055-273-3b0f68f4` had 62 positive-rate windows below 55 after the
same startup exclusion, with median scoped VU 4574.005 ms / GS 2360.345 ms.

These are uncontrolled player sessions. Menus, pauses, movie transitions and
unknown gameplay locations prevent calling their overall means combat FPS or
comparing the two executables as a regression test. The long frame gaps in the
longer session cannot be labelled spontaneous gameplay hangs without markers.

Source inspection: `ps2_perf.h` accounts exclusive wall-clock buckets per thread,
including scheduling/waits. `ps2_vu1_core.cpp` opens the Vu scope; nested GS work
is charged separately. Thus a large `vu_ms` is a useful investigation lead, not
proof of 92% CPU utilization or GPU elapsed time. `vu1n` reports zero missing
native blocks in the latest session. More captures alone are not an established
solution. Host loop 60 Hz also does not mean 60 distinct images.

The recent heavy windows around 32â€“48 seconds recorded no missing or dropped
audio frames. This does not establish full-session audio acceptance: startup
undersupply remains. Timed diagnostics are intrusive; use frames-only for FPS
comparisons, and run scoped timing or sampling separately. The launcher already
selects frames-only when detailed diagnostics are disabled; no setting was changed.

## Controlled local probe

Unlike GPU-05's interpreter-IOP/JIT-only controls, test the installed native build
with the existing frame-aligned arrival contract. This is the missing local
GAIN-11 control, not another claim about the i3 regression. Exact frame/trajectory
gates avoid the rejected drifting combat fixture. Only six seconds of arrival
are measured per run; this cannot test sustained combat, rain or thermal behavior.

Command (substitute absolute installation paths):

```powershell
python -I tools/test/gs-run-ab.py --runner <runner.exe> --elf <prepared-disc/SCUS_973.99> --collector <gow-session.exe> --output <new-output-directory> --compare pr26 --scene ship_arrival_frames --pairs 2 --seconds 120 --warmup 30 --gpu-samples
```

The arrival contract overrides wall-clock warmup with guest frames 0..360.
Order: off, on, on, off. Visible 1280x720, 1x, FXAA off, AF default/off, VSync off,
host cap 60, exact VU1, audio on, private blank cards, frames-only diagnostics,
no captures/profiler/concurrent compilation. PR26 off disables the six named
renderer switches and primitive grouping; on restores them. Later fixes remain
in both variants, so off is not a v0.5.0 executable. This is also not the player's
2x/AF16 configuration. PDH measures busiest-engine utilization, not GPU latency.

Runner SHA-256:
`147a45e3e45bf726d1ae144d18be3aecc6c99cb4d750dc87ad70f81fac682eb8`.
Each result records runner, ELF, TOC and collector hashes and effective settings.
Ignored evidence: `data/experiments/release-readiness-20261109/arrival/` and
`player-reports.json` alongside it.

## Investigation priorities

1. Capture/replay the heavy VU workload and separate exact arithmetic, chain/timing
   bookkeeping and scheduling/queue waits. Reuse the VU-01..08 rejected results;
   do not reintroduce their changes without new evidence. Replay parity precedes
   any gameplay candidate. Current scopes alone do not identify a faulty function.
2. Isolate the documented i3-10110U v0.5.0 regression using identical captured VU
   tasks and matched toolchains; then examine frontend costs if replay ties.
   Local Xeon results cannot close this notebook gate.
3. Validate first-visit stalls, sustained combat, fresh presentation and audio on
   each target machine. Use a confirmed encounter fixture or player-marked reports;
   the rejected combat trajectory remains rejected.
4. Matching PGO remains a measured historical opportunity (GAIN-09), not a promised
   percentage on this build. The installed runner has no compatible profile;
   never reuse the older incompatible profile or attribute an unmeasured benefit.

A 45.8-Hz workload needs roughly 24% less wall time per frame to reach 60; a small
isolated optimization or lowering image quality cannot be assumed sufficient.
No runtime patch, quality default, installed executable, player save or launcher
configuration was changed by this investigation. No release was published.

## Harness changes and validation

`gs-run-ab.py` now accepts explicit `--elf` and `--collector` so the checkout can
test an installed build without creating local disc metadata or copying a helper.
Defaults remain unchanged. Private-card isolation and identity checks still apply.
`gs-run-ab-tests.py` covers absent explicit inputs failing before output creation
and without reading local languages.json, alongside existing scene, interval,
CPU/GPU accounting, switch isolation and save-preservation tests. The suite passed.

## Completed probe results

All four runs passed all ten gates, including trajectory alignment, effective
scale/grouping, graceful exit and unchanged source saves. Each measured 360
consecutive guest intervals and no missing audio at the exact boundaries.

| Run | PR26 set | Guest Hz | p95 / p99 (ms) | Maximum interval (ms) | Busiest GPU engine mean (%) |
| --- | --- | ---: | --- | ---: | ---: |
| 1 | off | 59.909 | 17.579 / 18.446 | 25.475 | 41.54 |
| 2 | on | 59.996 | 17.462 / 17.815 | 21.639 | 48.64 |
| 3 | on | 59.996 | 17.570 / 17.819 | 21.045 | 47.18 |
| 4 | off | 59.996 | 17.430 / 18.028 | 21.871 | 43.67 |

The capped short scene shows no useful FPS difference. The two on runs have
slightly lower p99 than the two off runs, but p95 does not improve in both pairs.
No optimization gain or default change is accepted. GPU figures contain only
two samples per run; total system CPU activity also varied (approximately
28–38% run means). These do not establish GPU saturation, power savings, or a
controlled CPU-cost improvement. This is a readiness probe, not a statistical
performance acceptance.

Zero missing audio applies only to the measured scene. Startup logs contain
undersupply/drop counters outside that scene. Exact-boundary dropped-audio
counts are unavailable (`null`, not zero). No screenshots were taken during
these runs; scene/trajectory telemetry is not visual pixel parity or a listening
test. Full combat, physical notebook execution, GPU timing and matching PGO
remain unvalidated. The opening scene's ceiling makes it unsuitable for judging
small VU speedups: the next candidate needs a heavier verified workload.
