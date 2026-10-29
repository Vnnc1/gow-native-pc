# Player session review: patches 30–35

Evidence: local session `20261029-232953-466-5d1a01d1` under
`%APPDATA%/gow-native-pc/Launcher/registros/sessions`, compared read-only with the three earlier retained sessions.
The reviewed session ran on October 29, 2026, approximately 20:29–20:39 America/Sao_Paulo (23:29–23:39 UTC).
This is an observational review, not a controlled patch benchmark. No game, launcher, build or original log was changed.

## Findings

- Duration: 565.277 seconds; normal exit code 0; no collector write failure or log rotation.
- CPU: Xeon E5-2666 v3, 20 logical CPUs, approximately 15.84 GiB physical RAM. The actual OpenGL renderer identifies
  the RX 580 2048SP. Render/window size is 1280x800, initial hardware scale 2, dynamic scale on, FXAA on, VSync off,
  host cap 60. Dynamic scale settings do not establish the effective scale throughout the run.
- The executable SHA-256 is `13d9bfeb6876590298f307bb89cb125e38ec018c412f68efdd575f4b575b2ece`.
  All recorded source-patch hashes match this checkout, including 30–35. The source snapshot is not embedded binary
  provenance: matching source files alone cannot prove every optimization executed in that binary.
- Release configuration records `-O3`, `-fno-math-errno`, `-fno-trapping-math`, and `-march=x86-64-v2`.
  ThinLTO is off. This is not an x86-64-v3/AVX2-targeted C++ build. Independently, the runtime reports
  `x86-64 JIT on (inline tier on, AVX, speculation on)`; that JIT feature selection is not the C++ compiler target.
- Normal diagnostic mode uses frame accounting. Raw `ee_ms=0`, `vu_ms=0`, etc. mean timing is disabled, not zero cost.
  Structured metrics correctly omit those fields and mark `timing_scopes_enabled=false`.

## Measured performance

FPS below means `guest_flip_hz`, not `host_hz`. Means are weighted by each reported window duration.
Time ranges use runtime `t` (seconds since runtime measurement startup), rather than wall-clock time.

| Selection | Windows | Guest FPS mean | Five-second range | Host Hz mean |
| --- | ---: | ---: | ---: | ---: |
| All reported windows, including startup and pauses | 112 | 38.45 | 0–60 | 59.97 |
| Complete windows contained in t=130–485 s | 70 | 44.42 | 32.10–59.97 | 59.95 |
| Complete windows contained in t=165–440 s | 54 | 42.19 | 32.10–58.40 | 59.95 |

The 130–485 s selection contains 350.18 seconds of FPS measurements, between major gaps in the frame probe.
It is a reproducible temporal selection, not a scene-classified gameplay benchmark; there are no player markers
or gameplay-state annotations identifying every scene. Stable 60 guest FPS is not demonstrated.

For the 70 complete **frame-distribution** windows contained in t=130–485 s: 15,536 intervals, 82 above 33.33 ms,
four above 50 ms and none above 100 ms. The maximum is 82.997 ms. Median window p95 is 27.0855 ms and median window
p99 is 28.1205 ms. These are medians of per-window percentiles, not percentiles of the entire raw frame stream;
FPS and interval windows have different boundaries. They measure guest-frame intervals, not display latency.

Six intervals above 100 ms occur across the full session. Maxima include 47.962 s, 33.494 s, 8.374 s and 1.165 s.
MPEG activity precedes the largest gaps; the older session also contains approximately 48.189 s and 8.399 s gaps.
Movies, loading or transitions are plausible explanations. The probe alone cannot classify these as freezes or
attribute them to JIT compilation. The 1.165 s interval occurs near a memory-card creation message, another temporal
correlation rather than an established cause.

Sampled running-process working set peaks at 571.24 MiB and private memory at 681.03 MiB. Available system RAM stays
above 9.74 GiB in those samples. Average sampled CPU usage is about 3.70 logical-core equivalents, not 370% of the
whole CPU. These observations do not suggest RAM exhaustion, but do not rule out a saturated critical thread or
a GPU bottleneck. No GPU utilization, VRAM, clocks or temperatures were collected.

Audio device/stream initialization succeeds. There are no detailed audio underrun counters in this basic-mode
session, so sound continuity and audible quality cannot be certified from it.

## Comparison limits

Earlier sessions use runner SHA-256 `05742e3b84e1e7eb67f564be285be13b8a96da4f6b3cc600e10c0fbcdb80194a`
and record the patch stack only through 29f. The most useful earlier session is
`20261029-032432-890-4a6f31ce`: same recorded graphics settings and 60 Hz cap, but only 170 seconds long.
The other two sessions are short/startup dominated; one uses a 120 Hz host cap.

For the nine FPS records with end times between 75 and 116 seconds, the earlier session averages 52.33 FPS and
the new one 52.15 FPS. This is a descriptive observation, **not a speedup or regression measurement**:
inputs, scene alignment and background load were not controlled, and the ELF SHA-256 differs:

- Earlier: `1d292b290da4e8b69fa7ec790e042234fd6feb2ddd180674c4e559b3d088e46c`.
- New: `ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c`.

The differing whole-file hashes do not establish a different code section or explain its cause. They do prevent
assuming identical inputs. Full-session means are particularly misleading because pause fractions and durations differ.
The historical 56.66/57.93 FPS tests in `docs/tested-hardware.md` used fixed 1x scale, FXAA off, different cap and
scripted runs; they are also not a valid before/after comparison with this player's session.

## What each change establishes

| Change | Established result | Missing evidence |
| --- | --- | --- |
| 29 / 29a–29f | Direct-call paths, diagnostic and memory/DMA fixes already covered by regression tests; guest FPS and interval collection work in this session. | Per-patch gameplay speedup. |
| 30 | Memory fast paths preserve tested alias, MMIO, scratchpad and boundary behavior. | Hot-path savings or FPS attributable to the patch. |
| 31 | Explicit ThinLTO option passed the prior small toolchain smoke test. | ThinLTO was OFF here; it cannot explain this session's performance. Hidden visibility is a separate part of this patch. |
| 32 | New math flags and explicit portable CPU target appear in the launch configuration snapshot. | A controlled math-flags comparison; AVX2-tier C++ results. |
| 33 | Worker/barrier regression checks passed; asynchronous FINISH is recorded enabled. | Actual barrier enable state, invocation count and wait cost in this session. The collector omits `GOW_VU1_EARLY_FINISH`; absent an override the source inherits async FINISH. |
| 34–35 | Prior procedural tests match AOT/DLL and JIT state/accounting, including self-loop exits; JIT initialization is observed here. | Self-loop hits, saved time and per-patch FPS. Detailed VU1 counters were disabled. |
| Progress bar correction | Pipeline/QML regression tests passed. | No gameplay FPS effect; it changes preparation feedback only. |

## Next investigations, in priority order

1. Use the same ELF, save, route, graphics settings and warm-up for repeated alternating pre/post runs. Keep basic
   diagnostics for FPS and exclude explicitly marked movies/loading rather than filtering by whether FPS is high.
2. Isolate patch 33 first with its explicit `GOW_VU1_EARLY_FINISH=0/1` switch on the same executable and scene.
   Draining queued work can change overlap; its net performance effect is currently unknown. Do not disable it
   globally based on this log alone.
3. Capture a separate short detailed run in a reproducible slow scene to measure VU1 activity, worker waits and audio
   underruns. Do not mix intrusive timing results with basic-mode FPS. Compare fixed 1x/2x separately to investigate
   rendering sensitivity; the current dynamic scale obscures that variable.
4. Improve future logs with the effective early-finish setting, bounded aggregate barrier/self-loop counters,
   explicit scene/movie/loading markers, and build-time provenance tied to the executable hash. Keep expensive timing
   opt-in, preserve report allowlists and avoid per-call logging. These are proposed instrumentation changes, not
   changes implemented during this read-only investigation.
5. Evaluate x86-64-v3 and ThinLTO only as separate controlled builds after establishing the baseline. Neither setting
   is a demonstrated FPS improvement here.

Original evidence files were read once per dataset: `startup.log` and `runtime.log` are byte-identical in this
session and must not be counted twice. No benchmark or new gameplay test was run for this review.
