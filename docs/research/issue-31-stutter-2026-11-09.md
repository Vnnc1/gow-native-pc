# Issue 31: stutter investigation and acquisition diagnostics

Status: **not resolved**. On `fix-chore` after `5e843be`, the safe change is
diagnostic coverage, not a proven renderer performance fix. No quality default,
AF shader, synchronization fence, or graphics setting was changed.

## Supplied evidence

[Issue 31](https://github.com/Vnnc1/gow-native-pc/issues/31) reports increasing
stutter with AF, 3x rendering even in menus, temporary relief after opening the
menu, and rain near the Captain's Cabin even at 2x with AF disabled.
The [attached report](https://github.com/user-attachments/files/34577767/report-20261109-114344-368-8de5be08-5845e6df.zip)
has SHA-256 `04b3d4df541d7e3f7121f8bd33b314911f407ad967d7b9842647b28de917caa1`.
It is a live export (`running`, approximately 894 seconds), not a final exit report.

Reported hardware: Ryzen 7 7700, GTX 1060 3 GB, 32 GB RAM, 75 Hz monitor.
Runtime initialization confirms the NVIDIA GPU. Settings: 2x, AF 1/off,
1920x1080 fullscreen, FXAA on, VSync off, host cap 60. The runner hash is
`8d776496a5c3d07152cfe061719bea76ef5f456419f2a7bd8f390d88682a5794`.
The source-patch snapshot ends at 58; this describes source at launch, not proof
of the binary's patch contents or a test of today's PR 26 renderer.

The player marker is at 799.247 seconds. Only complete five-second windows
inside each interval are included below (11 guest and 11 performance windows).

| Collector interval | Weighted guest Hz | Weighted host Hz | Median window p95 / p99 | Maximum guest interval | Guest intervals >100 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 739.247–799.247 s | 54.859 | 59.222 | 20.174 / 21.875 ms | 744.774 ms | 1 |
| 799.247–859.247 s | 54.217 | 59.999 | 20.571 / 21.875 ms | 23.981 ms | 0 |

Window percentile medians are not pooled percentiles. The full session includes
five guest intervals over 100 ms, maximum 2621.293 ms, including transitions.
These aggregates do not locate the visible rain stalls or establish when the
menu was opened. Host Hz counts loop iterations, not fresh images; these numbers
therefore do not disprove the player's visible stutter. CPU process/page-fault
counters cannot establish VRAM exhaustion, GPU saturation or driver stalls.

## Source investigation and change

Reviewed GPU-01/02/03 and the PR 26 integration before changing code. The current
renderer already has segment-fenced vertex-ring ownership and nonblocking shared
presentation acquisition; neither establishes that issue 31 is fixed. The AF
shader performs additional texture samples, an expected cost rather than a
confirmed defect from this report. No evidence justifies removing fences,
lowering default quality or repeating the rejected FSR experiment.

`GSHostPresentation::prepare` can acquire the previously held shared slot again.
Patch `zzz-307-shared-acquisition-metrics.patch` adds bounded, host-owned
accounting under existing `GOW_PERF_DIAG` modes: fresh/repeated acquisitions,
blank/unavailable polls, skipped publication sequences, acquisition rate and
maximum hold age. It preserves state across five-second windows and resets on
host lifecycle/mode changes. It adds no GPU queries, readbacks or waits.

The collector now exports `[gow-present]` numeric fields into `metrics.jsonl`.
It does not relabel acquisition rate as guest FPS. Different publications may
contain identical pixels; this is not a scanout or input-latency measurement.
A blocked host emits nothing until it resumes. Old reports cannot be backfilled.

## Validation and remaining acceptance gates

Isolated Windows Release runner: current ordinal patch chain plus 305–307,
pinned LLVM 20261020, no PGO, JIT-only VU1, interpreter IOP. The installed game,
its executable and original memory card were preserved. Build sources and
artifacts are under `C:/gow-i30-src`, `C:/gow-i30-build` and ignored
`data/issue-triage/31`; these are diagnostic builds, not released packages.

- Runner and `gow-session` builds passed. Forward patch applicability against
  captured current-chain sources and reverse applicability against the built
  sources passed.
- Production frame-metric test passed: classification, skipped sequences,
  retained age across windows, replacement interval, sequence restart and reset.
- Deployed collector suite: first run hit Windows file-lock cleanup failure in
  `test_collector_survives_parent_exit`; functional assertions had passed.
  Complete retry passed all 11 tests. Both logs are retained.
- Three real-game collector controls use private discs/cards, 1280x720 window,
  FXAA on, VSync off, cap 60, exact VU1 JIT and the opening-ship guard script on
  the local Xeon E5-2666 v3 / RX 580. This is not the reported rain scene or GPU.
  Acquisition fields were emitted and exported during actual runtime execution.
- The first 2x/AF-off control stopped host performance/acquisition reporting
  around 42 seconds while guest/player reporting continued; the collector
  requested stop at 110 seconds and forced termination five seconds later
  (62097). Do not count this as a spontaneous crash or successful normal exit.
  This needs separate reproduction before attributing it to issue 31 or this patch.
- The controls' player trace reports HP zero even with the requested test god
  mode; survival/equivalent scene progression was not established. A preliminary
  run without that flag is also retained. None is an accepted FPS A/B benchmark.

All 50 exported acquisition windows satisfy
`polls = fresh + repeated + blank + unavailable`. The two normal-exit controls
each provided nine complete windows after 60 seconds:

| Setting | Exit | Acquisition windows, total / after 60 s | Guest Hz after 60 s | Acquisition Hz after 60 s | Maximum hold after 60 s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2x, AF off | forced 62097 | 8 / 0 | unavailable | unavailable | unavailable |
| 2x, AF16 | 0 | 21 / 9 | 32.191 | 45.296 | 66.940 ms |
| 3x, AF off | 0 | 21 / 9 | 25.576 | 53.905 | 56.927 ms |

These are diagnostic observations, not a comparison of AF cost: scene progression
was not matched, and the local interpreter-IOP build differs from a normal
optimized installation. Higher acquisition Hz than guest Hz demonstrates why
the two must remain separate. No visual smoothness or sound-quality conclusion
is derived from these logs. The control runner SHA-256 is
`d229fa87a66ba5859bd4cc159cc55a832abe7059283fae0736b65a12e05223e9`;
the deployed collector is
`21691e72be3cb52885d96ffc53a09178adb30d860a3a264fb9fac4d06659bd7d`.

No GTX 1060 reproduction, Captain's Cabin save, visual/audio parity capture,
GPU/VRAM trace, packaged diagnostic UI/installer regression or full pipeline
verify was completed. The next acceptance gate is the same rain scene on the
reporter's GPU with a current identified runner and completed report containing
guest intervals plus acquisition metrics. Correlate holds or missing host output
with the player marker before choosing a renderer/driver investigation. Do not
close issue 31 or advertise a stutter improvement from this diagnostic change.
