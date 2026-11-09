# Issue 31: stutter investigation and acquisition diagnostics

Status: **reported rain/AF stutter not resolved**. On `fix-chore` after `5e843be`,
patch 307 adds diagnostic coverage; follow-up patch 308 fixes a reproducible
minimized-window close hang. This is not a proven renderer performance fix.
No quality default, AF shader, synchronization fence, or graphics setting was changed.

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

## Follow-up: minimized-window host hang

The original `guard-2x-af1` recording has no window-state trace or thread dump.
Its exact trigger cannot be established retrospectively. An unchanged-runner
180-second visible repeat (`repro-2x-af1`) exited normally, with 23 complete
post-warmup performance windows. This does not support a deterministic AF-off
hang. Host thread samples during that repeat showed normal frame-cap sleeps.

A controlled minimization reproduced the signature on the same unchanged
runner: guest/player and audio activity continued, but host/acquisition windows
stopped. A process-scoped thread snapshot located the host in:

```text
NtUserWaitMessage
_glfwWaitEventsWin32
PollInputEvents
EndDrawing
GSHostPresentation::renderFrame
PS2Runtime::run
```

The pinned raylib `rcore_desktop_glfw.c` loops in `glfwWaitEvents()` while
`FLAG_WINDOW_MINIMIZED` is set and `FLAG_WINDOW_ALWAYS_RUN` is absent.
`CORE.Window.shouldClose` is updated only after this loop. A close message wakes
the event wait but does not restore the window; it re-enters the loop, so the
runtime never reaches `WindowShouldClose()` or its normal shutdown path.
The collector's five-second fallback then kills its own child. This is a host
event-loop defect, not evidence of GPU/AF saturation or a stalled guest.

Baseline `minimized-baseline-2x-af1`: minimization confirmed with `IsIconic`,
last acquisition window at 36.988 s, close requested at 51.342 s, forced
termination at 56.345 s, exit 62097. Thread inspection briefly suspended only
the owned test process's threads and resumed each after collecting its stack.
The original run is consistent with this defect, but lacks evidence proving
that it was minimized. Keep that distinction when describing issue 31.

### Correction and regression procedure

Patch `zzz-308-minimized-window-close.patch` adds `FLAG_WINDOW_ALWAYS_RUN` in
the existing production `gowVentanaAbrir` configuration. The guest and audio
already continue independently; now the host continues polling and can close
while minimized. No external tool or player setting is needed. Background host
rendering remains active with the configured frame cap; this is not a power-saving
change. It does not fix arbitrary driver/GPU blocking calls.

`tools/test/window-lifecycle.py` runs the production runner through the deployed
collector, copies the original card into a private disc, selects only the
collector-owned child's window, confirms minimization/restoration, and checks
host progress and exit without forced termination. It requires Windows desktop,
GPU and a compatible prepared disc, so it is a manual integration gate rather
than a data-free CI test. Example (use a fresh output directory per action):

```powershell
python -I tools/test/window-lifecycle.py --runner <runner.exe> --collector <gow-session.exe> --disc <prepared-disc> --output <new-test-directory> --action minimize
```

Other actions: `restore` (minimize, restore, then close) and `visible` (normal
close). Defaults use a 40-second warmup, 2x/AF off, 1280x720 window, FXAA on,
VSync off, 60 host cap and the opening-ship script. The same scene/health
limitations above apply; these checks do not measure gameplay improvement.

Candidate runner SHA-256:
`19fa28bca81f3ae47912bceb6f42e3a8402d00349792fca9452fa36eb3f21c45`.
Only the production window flag/comment differs from the 307 baseline source.
Release rebuild and forward/reverse patch applicability passed. Evidence stays
under ignored `data/issue-triage/31`, alongside the prior failed controls.

The first automated baseline attempt (`window-test-baseline`) resumed host
reporting after an approximately nine-second pause and exited normally. That
version checked minimization only once and could accept a report spanning the
pause. It is excluded from the minimized-close regression result. The harness
now checks `IsIconic` every 500 ms throughout the hold, rejects restoration,
and requires a complete reporting window inside the minimized interval.
The repeated baseline (`window-test-baseline-2`) remained minimized and failed
as expected: forced termination, exit 62097. The corrected repeat
(`window-fix-minimize-2`) passed and closed normally in 189 ms after the
collector's stop event. The first corrected minimize control also exited
normally; both retain their logs. Guest-frame accounting tests passed again.

The first restore control (`window-fix-restore`) detected an unplanned restore
at 48.922 s and was rejected; its cleanup closed normally. After the maintainer
agreed to leave the window untouched, `window-fix-restore-2` passed the full
minimized interval, programmed restoration and normal close (195 ms from the
collector's stop event). These interrupted runs remain in the evidence folder.
The reproducible minimized-close failure and fix are established on the local
Windows/RX 580 system. Fullscreen/borderless transitions, Linux, other drivers,
visual/audio parity and the original GTX 1060 rain scenario remain unvalidated.

The first corrected visible control (`window-fix-visible`) closed its game window
and emitted `process_exit` code 0, but `session.json` retained `state=running`
without `exit_code`. The strict regression rejected this inconsistent report.
This is separate from the host hang: the exit event and collector completion
establish that the game exited. Final metadata persistence remains a diagnostic
collector limitation; its cause was not established in this window-lifecycle
change. The original inconsistent files are retained, not repaired or hidden.
The subsequent [collector persistence investigation](collector-final-state-2026-11-09.md)
reproduced atomic-replacement denial and added bounded retries plus explicitly
flagged exit-event recovery; it also validated export of this historical report.

The repeated visible control (`window-fix-visible-2`) passed with consistent
final metadata, code 0 and 206 ms from stop event to exit. Final accepted matrix:

| Runner / action | Result | Collector stop to exit |
| --- | --- | ---: |
| Baseline / continuously minimized | Expected regression failure, forced 62097 | 5062 ms |
| Patch 308 / continuously minimized | Pass, exit 0, host progress | 189 ms |
| Patch 308 / minimize then restore | Pass, exit 0, host progress while minimized | 195 ms |
| Patch 308 / visible | Pass, exit 0, consistent final metadata | 206 ms |

These durations are local shutdown observations, not frame latency benchmarks.
The full pipeline verify and packaged installer/UI suites were not rerun for
this one-flag runtime change. No files were committed or published by the agent.
