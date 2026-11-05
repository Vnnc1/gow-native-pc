# Shared presentation contention and the LK report

Investigation GPU-02, 2026-11-03. Continues GPU-01 with an RX7600 report and a
new deterministic contention reproduction, not a repeat of rejected queue/VU work.

## Supplied LK session

Read-only inputs: `E:/doc/lk/{session.json,metrics.jsonl,runtime.log,events.jsonl}`.
`startup.log` is byte-identical to `runtime.log`, not a second session. Local
analysis with input hashes: `data/experiments/present61/lk-analysis.json`.

Metadata and GL renderer identify **Ryzen 5 5500 / Radeon RX7600**, launcher
0.4.0, not RX5500 XT / launcher 0.5.0. Scale 2, FXAA on, VSync off, window cap
60, precise VU1, early GS FINISH, Release O3 with PGO, patches through 55.
Shared GPU texture presentation was active. Runner SHA-256:
`e252b77f01f677edd5220b3cdbcbb9e7b38e5136c24546c88462e9ee116a3c2d`.
Session length 1116.201 seconds; normal exit code zero.

| Collector elapsed range | Logged windows | Weighted guest FPS | Minimum window guest FPS | Weighted host Hz |
| --- | ---: | ---: | ---: | ---: |
| 150–850 s | 140 | 59.718 | 49.72 | 59.902 |
| 1000 s through session end | 23 | 56.223 | 51.92 | 59.914 |

These descriptive ranges are not an optimization A/B or scene identification.
No player markers map drops to Hydra attacks. Private bytes peaked at 621.82 MiB,
unlike the multi-GiB Intel report. Large guest-probe gaps occur near MPEG activity
(including initialization around 894 s before the 33.4-second gap). Do not
automatically classify movie/loading intervals as gameplay freezes.

Collection was `GOW_PERF_DIAG=frames`: zero section times are disabled measurements.
There are no GPU utilization/VRAM/time samples, queue timings, input timestamps
or fresh-image counts. Host Hz near 60 does not prove every displayed image is
new or input-to-photon latency is low. The report cannot isolate the bottleneck.

## Reproduced source defect and candidate

`GSSharedPresent::Acquire` waited unconditionally on `s_sharedMutex`. The GS
publisher holds that mutex while allocating/copying GPU resources, creating
fences and flushing the driver. A delayed publisher therefore delays the host
window before its next event/input-poll cycle.

Candidate: try the mutex without waiting. If busy, return a host-thread snapshot
of the acquired frame; its slot remains marked `reading` and cannot be recycled
by the publisher. Without a previous frame, report unavailability as before.
Successful acquisition retains newest GPU-complete selection and fence/release
behavior. Blank frames remain blank; capture/shutdown/inactive transitions clear
the snapshot. No drawing, VU1 arithmetic, queue capacity or quality setting changes.

`tools/test/shared-present.cpp` exercises production code with fake GL fences.
A thread holds the publisher mutex until Acquire returns, with a two-second
escape deadline so the reference fails without hanging. The old implementation
took 2,007,098 us and failed the responsiveness assertion. The candidate returned
below microsecond clock resolution in all four contention cases. This is a
synthetic CPU-lock regression test, **not** physical input latency or an FPS gain.

Coverage: no first frame, retained texture/slot ownership, unsignaled newer fence,
newest completed selection, blank frames, host restart. Added to normal verify.
Source snapshots and logs remain under ignored `data/experiments/present61/`.

## Validation and retained scope

The entire host loop is not made nonblocking: frontend/backend lifetime locks,
producer queue capacity and driver swap calls can still wait. GPU completion can
also be slow while the host repeats its retained image. Do not claim that this
fixes every reported FPS drop or all input lag.

Full `build.cmd -Stages verify` passed: 12 CTest cases, guest-call/codegen,
VU1 backend equivalence/self-loop exits and task replay. Production contention
regression fails on the original implementation and passes on the candidate.
Patch 61 reverse applicability and isolated forward source equality passed.
The first forward-check attempt inside the ignored repository subtree was skipped
by Git and failed equality; rerunning outside the repository applied and matched.

Six alternating visible runs on Xeon E5-2666 v3 / RX580 2048SP, same portable
LLVM Release/PGO build, 1280x720 output, scale 2, 60 host cap, VSync off, precise
VU1, GS early FINISH on, large-VIF early finish off, stage spin 50 us, sound on.
FXAA was off in this FPS harness, so this is not an exact default-settings
performance acceptance. Each run lasted 100 seconds with 40-second warmup and
11 complete measured windows (~55 s); no simultaneous builds/profilers. Fresh
private cards and the same real-time opening-ship script; scene alignment is
not deterministic. All six runs passed exit/gameplay/settings/window checks.

| Pair | Baseline guest FPS | Candidate guest FPS | Order |
| --- | ---: | ---: | --- |
| 1 | 58.1618 | 59.5636 | candidate, baseline |
| 2 | 59.5093 | 59.1064 | baseline, candidate |
| 3 | 59.4727 | 59.5273 | candidate, baseline |

Mean of run means: 59.0479 -> 59.3991 (+0.595%), two of three pairs positive.
Minimum five-second windows: baseline 47.80/57.00/55.40; candidate
56.60/53.98/55.60. Median window p95 guest intervals stayed 16.691–16.707 ms;
no measured intervals above 100 ms in the analyzed windows. These are guest
probe intervals, not presentation or input-to-photon latency. Small, variable
FPS difference is not a confirmed general speedup or stable-60 claim.

Baseline runner SHA-256:
`6f282058309b0e6708078a8e3d210e77f6bad0df4348dce6e2cc2e5fe2eb9c15`.
Candidate runner SHA-256:
`91413ace80550c0777a0257d322c566c284c1cc2d22afcddc31bfad5d1cef346`.
Raw comparison: `data/experiments/present61/ab/summary.json` and per-run reports.

Decision: retain patch 61 for the deterministically reproduced lock wait; the
FPS comparison does not establish a reliable gain. It applies automatically in
the normal runtime patch chain and the separate prebuilt diagnostic runner.
Existing installations need an updated runner; this is not a launcher-only fix.
RX7600, RX5500 XT, NVIDIA, actual Hydra scenes and physical input latency remain
unvalidated. Visible 100-second 2x/FXAA-on smoke passed all 11 checks, including gameplay,
2000 VU1 parity runs with zero mismatches, audio/IOP metrics, frame distributions,
report export and graceful exit. The 80-second GS capture visibly contains
Kratos, ship combat and HUD; no blank output in that capture. This is not a
whole-scene visual equivalence or physical audio/input assessment. Evidence:
`data/gow1/logs/session-game-20261103-215811`.

## FSR feasibility (GPU-03, analysis only)

The user also requested FSR for older AMD/NVIDIA GPUs. The launcher's persisted
`filtro=fsr` is a legacy key: `lanzador.cpp` maps it to `GOW_SCALER=sharp`, and
`gs_host_present.cpp` implements five-tap bicubic scaling plus sharpening, not
AMD EASU/RCAS. The UI correctly calls it Sharp (bicubic + sharpening).

[AMD FSR 1 documentation](https://gpuopen.com/fidelityfx-superresolution/)
describes spatial EASU/RCAS scaling without motion vectors or frame history,
with examples on both AMD and NVIDIA GPUs. That makes FSR 1 a plausible future
presentation integration; it is not implemented or benchmarked by this change.
It must replace the existing upscale pass rather than stacking two upscalers.
Existing FXAA ordering, viewport/aspect handling, blank frames and bilinear
shader-failure fallback must remain valid. The PS2 HUD is already composed into
the source image, so low source resolution also affects text and HUD quality.

A performance claim requires lower rendering cost to exceed the new scaling
cost. Compare 2x plus current scaling, 1x plus current scaling, and 1x plus real
FSR with the same output resolution and scene; the second comparison separates
resolution savings from the upscaler itself. Measure guest pacing, fresh image
presentation, GPU timing and visual quality, including Hydra transparency and
HUD. Do not infer a gain from GPU utilization or host Hz alone. Lower resolution
cannot remove VU1 execution or CPU submission costs. Dynamic resolution also
needs a measured GPU budget and stable render-target resizing; it is not enabled
by renaming this existing option. No universal default downgrade is shipped.

This is an integration feasibility record, not another completed UI-01 scaler
benchmark or a promise of 60 FPS. The current contention correction remains
separate so its comparison is not confounded by resolution or shader changes.

## Private delivery

`data/_package/diagnostic-kit-present61-20261103/setup.exe` (50,073,898 bytes),
SHA-256 `cd7a3f8fb53839bf1dad88c217c9926cb734b91ca3518d262b92c4d7e315b770`.
`verify_setup.py` matched all 1,358 members / 12 LZMS blocks against staging.
Packaged game-selection and UI smoke returned zero; UI capture was inspected.
The kit carries the candidate runner hash above and no game disc/card files.
The 17 pipeline regression tests also passed. No normal public installer/PGO
retraining was performed; this is a separate private precompiled kit.

Packaged 100-second light game smoke also reached `state=11 levelReady=1`,
recorded the candidate runner hash and exited zero without forced termination.
Evidence: `data/experiments/present61/packaged-smoke.json`.

GPU-03 implementation follow-up: [FSR 1 experiment](fsr1-experiment-2026-11-03.md)
records the separately authorized prototype and measured retention decision.
The feasibility section above describes the state before that experiment.
