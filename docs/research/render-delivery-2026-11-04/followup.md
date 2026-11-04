# Patch 66 follow-up: frame tails, audio and GPU pressure

## Scope and diagnosis

The previous background session was stopped through its own helper's `stop.request` at
2026-11-04 17:42:22 UTC, with exit code 0. No unrelated process was stopped. All subsequent
runs used another private disc root and blank cards; player cards were never passed to a runner.

The notebook is the i5-8265U / 24 GiB system with Intel UHD 620 selected by OpenGL, driver
27.20.100.9664. The Radeon 520 and historical RX 580 are not the devices measured here.
AC power, fixed 1x rendering, 1280x720 host window, audio enabled, host cap 60 and the profile's
real-time input script were retained. Hidden-window testing is the user's requested scope.

A separate intrusive timing pair used the previously installed binary
`1264ec3e54eb718a80831aa7ce019cd0b0578e1aafc3e77af7512e1ca94ec2b5`, with grouping off/on.
After 60 s warm-up, Windows GPU engine samples averaged 81.33% / 78.13%, with maxima 98% / 95%.
The game used 159.70% / 160.29% of one CPU core on average (about 20% of eight logical CPUs).
These are utilization measurements, not watts or temperature. A busy individual thread can
still limit the game while total CPU utilization is low.

The timing pair had 0 / 675 missing audio frames in complete post-warm-up windows. GS scope
wall time averaged 2794.77 / 2558.77 ms per roughly five-second window; EE 2413.41 / 2362.57 ms,
VU 4612.21 / 4615.72 ms and IOP 500.55 / 486.88 ms. Scopes can overlap and include waits:
do not add them into CPU utilization or interpret them as GPU execution time. Sync diagnostics
were enabled, but this early-FINISH route emitted no explicit synchronization-site samples.
These intrusive sessions are **not FPS benchmarks**.

The observation confirms GPU pressure also without patch 66. It does not establish that patch
66 caused the previous late-session slowdown, or distinguish thermal/power limits from scene
and scheduling differences. Clocks and temperature were not measured. Grouping remains opt-in.

## Bounded renderer change: patch 67

The hardware renderer issued both alpha-test draws even when `ATST=ALWAYS` guarantees that
the failing draw discards every fragment. Conversely, `ATST=NEVER` discards every fragment
of the passing draw. Patch 67 omits only those provably empty draws. It does not lower internal
resolution, discard visible geometry, disable effects, change frame limits or alter audio mixing.

`gs_alpha_pass.h` contains the small pass-selection predicate. Dynamic alpha tests retain the
existing shader path, surviving draws retain order, and AFAIL color/depth masks remain unchanged.
The existing `GOW_GS_HW_NOATEST` and `GOW_GS_HW_NOFAIL` debug behavior is preserved.
Pruning is **opt-in**, `GOW_GS_ALPHA_PRUNE=1`. The default/0 selects the reference in the same executable.
The notebook comparison did not justify enabling it by default. `[gs-alpha-config]` records
the selected mode; opt-in `GOW_GS_HW_STATS` emits five-second skipped-pass counters.

The new `gow_gs_alpha_tests` checks all 16,777,216 combinations of alpha/reference values,
test functions, AFAIL modes, ATE and debug overrides against an independent ordered-fragment-write
oracle. This proves pass selection, not GPU rasterization. The full `fetch,build,verify` pipeline
passed, including 12 CTest groups, code generation, memory, audio, VU1 equivalence and task replay.
Patch-chain verification confirms the runtime matches 01–58 + 66 + 67; delivery 59–65 remain excluded.

Measured executable SHA-256:
`f7c7972633d070b434a3fd9bc882b5560581963aa6ed57b13e1571ef27f5ad3e`.

## Measurement tooling

`tools/test/gs-run-ab.py --compare alpha --grouping 0 --gpu-samples` alternates the reference
and pruning paths without changing primitive grouping. The same tool still compares patch 66
and now separates intrusive `--timing` runs from FPS summaries. Audio missing/dropped frames,
process CPU usage and guest-frame tails accompany FPS.

`windows_gpu_sample.py` reads Windows PDH engine counters every two seconds, using the helper's
direct child PID. It retains only that child's engine names and system totals, never other processes'
identities. Invalid, unavailable and first rate samples remain explicit, not zero utilization.
The busiest engine is reported instead of summing independent engines into a fictitious GPU percent.
Warm-up excludes overlapping GPU sample intervals; sampling cost is recorded. No vendor tool or
new third-party dependency is required. These are local benchmark artifacts, not additions to the
player report export allowlist.

The alpha A/B sampler cost averaged 4.69–10.92 ms per roughly two-second query, with a 44.97 ms
maximum. This measures query wall time, not a proven bound on its effect on FPS. A later extension
also records classic PDH total CPU busy time, separate from the helper's process CPU metric.
CPU-counter absence does not disable GPU sampling and is represented by null.

Counter references: [Microsoft PDH array API](https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhgetformattedcounterarrayw)
and [GPU utilization semantics](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/).

Evidence is under ignored `data/patch66-followup/`: `timing/`, `system-samples.jsonl`,
`build-verify.log` and `alpha-ab/`. Game captures and private cards are not packaged or exported.

## Alpha pruning comparison: rejected as a default

Six 120-second runs, 60-second warm-up, alternating 0/1, 1/0, 0/1. Every run reached gameplay
before warm-up and exited gracefully with code 0. Original save inventories remained unchanged.
Each contributed 11 complete guest-frame windows and 2,640,000 requested audio frames.

| Run | Prune | Guest FPS | Median window p95 / p99 ms | CPU, % of one core | Mean busiest GPU engine % | Missing audio frames |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | off | 42.063 | 29.107 / 32.596 | 148.970 | 78.661 | 10,039 |
| 2 | on | 38.737 | 36.565 / 52.007 | 155.036 | 74.982 | 0 |
| 3 | on | 32.372 | 56.281 / 88.285 | 186.237 | 49.052 | 3,143 |
| 4 | off | 41.413 | 34.248 / 45.461 | 147.682 | 79.445 | 0 |
| 5 | off | 47.179 | 34.372 / 38.622 | 81.296 | 51.162 | 0 |
| 6 | on | 37.262 | 36.318 / 50.002 | 153.262 | 73.304 | 4,752 |

Mean run FPS was 43.552 off versus 36.124 on; all three pairs favored the reference. The on
runs skipped 2,143 / 1,754 / 2,045 empty passing draws in post-warm-up counter windows, but no
failing draws in this route. Eliminating proven redundant work did **not** establish a performance
benefit on this driver/workload. Lower GPU utilization with lower FPS is not an efficiency win.
Patch 67 is retained only as an opt-in experiment; both 66 and 67 are disabled by default.

Substantial run-to-run variation remains. In reference run 1, guest FPS fell from 50.76 to
13.54 in the final windows, while its GPU busy samples fell from over 80% to roughly 32–37%.
Missing audio frames appeared in the same late period. This episode cannot be explained as
the GPU simply remaining saturated at 99%. System load, scheduling, driver waits and power/
clock behavior remain candidates, not established causes. No user process or power setting
was changed to force a favorable benchmark.

A later WMI snapshot during the scaler experiment reported 100% system processor time, while
the completed game runs averaged roughly 2.4–2.6 cores out of eight. Other active processes
were observed consuming CPU. These sessions include competing system load and cannot establish
an isolated renderer speedup. Windows also recorded a firmware frequency-limit event at
11:10:32 local time, well before this comparison; it is not evidence of throttling during a
particular measured frame. Maximum processor state was 100% on AC. The custom power plan was
left unchanged. See local `processor-power-events.json` and `cpu-late-snapshot.json`.

CPU values above were recomputed in `alpha-ab/analysis.json` from complete, duration-weighted
helper intervals, excluding teardown. The raw summary retains its original unweighted values;
the harness and its regression tests now use the corrected aggregation. Percentiles remain
medians of per-window percentiles, never pooled percentiles. No completed run was discarded.

## Lighter filter comparison: no automatic settings change

The same six-run protocol then compared the existing sharp bicubic filter (0) with bilinear
(1), with both experimental optimizations explicitly off, unchanged 1x internal resolution,
FXAA off and audio enabled. Bilinear changes the appearance of the enlarged image; it is not
an image-identical optimization. Both modes used the same binary and GPU/process sampler.

| Run | Filter | Guest FPS | Median window p95 / p99 ms | CPU, % of one core | Mean busiest GPU engine % | Missing audio frames |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | sharp | 24.922 | 71.620 / 102.145 | 257.306 | 55.364 | 5,140 |
| 2 | bilinear | 24.444 | 71.696 / 140.048 | 238.875 | 46.170 | 34,753 |
| 3 | bilinear | 13.572 | 110.326 / 148.264 | 165.200 | 34.457 | 628 |
| 4 | sharp | 30.292 | 64.080 / 90.641 | 177.327 | 56.153 | 1,391 |
| 5 | sharp | 29.967 | 53.629 / 73.550 | 241.115 | 63.982 | 9,449 |
| 6 | bilinear | 29.121 | 64.766 / 86.493 | 216.012 | 56.333 | 3,915 |

All six sessions passed gameplay, graceful exit and private-save checks. Mean FPS was
28.394 sharp versus 22.379 bilinear; average busiest-engine utilization was 58.50% versus
45.65%. This does **not** meet the request to reduce utilization without losing FPS. No
launcher filtering setting was changed. Missing audio totals were 15,980 / 39,296 frames;
these are delivery counters, not an audio listening assessment.

Continuous classic PDH CPU sampling was added for the final pair after the initial high-load
snapshot: complete post-warm-up intervals averaged 83.0% / 81.2% system CPU and reached 100%.
Earlier runs lack this counter; no missing values are filled with zero. Sampling and scene
variation prevent treating these results as an isolated causal cost of bilinear filtering.
The real-time input route does not guarantee identical scenes across runs. A quieter baseline
and a reproducible scene are prerequisites for a release performance claim.

Final installed executable, after changing only alpha pruning's default to opt-in:
`6635147d6d41398e020b21d2e2dcef2ba837ae4f0306ba42b443aa41e343942b`.
This is the scaler-test binary; explicit alpha 0/1 paths are unchanged from the earlier binary.
The complete `fetch,build,verify` stage passed again (`final-verify.log`). Subsequent Python
methodology tests and live PDH readings checked the added total-CPU counter.

## Next acceptance gates

1. Repeat with a stable scene and record competing system load, per-thread CPU/driver waits,
   GPU busy time and power/clock/thermal evidence on the same time axis. Do not close the
   player's other applications or alter their power plan automatically.
2. Optimize the measured critical path. Require at least three comparable pairs with no FPS,
   p95/p99 or audio regression before promoting an experimental path or a hardware preset.
3. Validate visible play with sound and heavy combat, then AMD/RX 580 and NVIDIA separately.
   Hidden tests do not close those gates. This notebook still has no stable 60 FPS result.

## Bounded background observation

After the comparisons, one separate hidden session was started with the final binary, audio,
sharp output filtering and no explicit grouping/pruning environment overrides. Startup confirmed
`[gs-run-config] enabled=0` and `[gs-alpha-config] prune=0`, validating the installed defaults.
It reached gameplay at collector elapsed 24,545 ms; the approximately 70-second capture showed
Kratos and enemies on the ship, with `state=11 pending=0 levelReady=1`. This GS capture is a
functional check, not visible-window validation or an FPS benchmark. Original save inventory was
checked again after capture and remained unchanged.

Artifacts and control are under `data/patch66-followup/background/`. The independent monitor
collects CPU/GPU samples and requests a graceful stop after 600 seconds. It can also be stopped
early through `stop-test.ps1`, which signals only this helper. `control.json` and the session
metadata report eventual completion; no completed ten-minute stability result is claimed while
it is still running. The original card/save paths are never passed to this test.
