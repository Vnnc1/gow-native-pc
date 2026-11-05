# RX 5500 XT saturation report: source investigation

Status: investigated in source, **not reproduced on the reported GPU**, no fix or
FPS gain claimed. Ledger ID: GPU-01. Date: 2026-11-03.

## Report and verified configuration

The player reports drastic FPS drops near 100% GPU utilization on an RX 5500 XT,
launcher 0.5.0, default settings, VSync disabled, during Hydra attacks above and
below the ship deck. No exact FPS range, driver version, runner hash, trace,
GPU-memory readings or scene-specific save was supplied in this report.
Do not substitute the older i3-10110U/Intel UHD reports for this GPU's evidence.

Checked `v0.5.0:launcher/qml/Main.qml`: internal resolution defaults to 2x and
VSync to false. Settings migration version 7 changes the old 120 Hz window cap
to 60. The literal initial 120 value alone does not prove a fresh install runs
at 120. Existing saved settings and the actual runner still need log confirmation;
the launcher version does not uniquely identify the installed game executable.
The tag pins runtime commit `471c83180a8df575cff4abd3fae6c043b5096925` plus its
patch chain; current downloaded runtime source was also inspected.

2x increases both render-target dimensions, approximately quadrupling pixel
count relative to 1x. It does not imply four times total frame time: VU1 work,
draw submission and fixed costs do not scale that way. Reaching 100% utilization
alone identifies neither a defect nor which GPU operation dominates. Sustained
60 FPS requires the critical frame workload to fit approximately 16.67 ms.

## Concrete mechanisms found

Paths below are relative to `engine/runtime/PS2Recomp/ps2xRuntime/`.

| Path / symbol | Confirmed source behavior | What it does and does not establish |
| --- | --- | --- |
| `src/lib/gs/gpu/gs_hw_backend.cpp`, `Impl::draw` / `drawOne` | Shadow-volume counting has a fixed-function fast path for qualifying untextured flat-color passes. Consecutive color runs are split to preserve that path. | The optimization already exists; do not propose it as a new fix. Whether Hydra drops leave this fast path is unknown. |
| Same file, `softBlend && !zAliasWrite && !(s.colclamp & 1)` | Fallback issues one `DrawArrays(..., 3)` per triangle, with `TextureBarrier` between triangles. | A batch of N triangles can become N draws and N-1 inter-triangle barriers. Removing barriers or merging overlapping triangles changes destination-dependent blending; correctness must be preserved. Actual frequency in the reported scene is unmeasured. |
| Same file, alpha-test failure pass | Some draws require a second pass with different color/depth write masks. | Can add work beyond the batch count. Disabling it is not an acceptable general optimization. |
| Same file, `reportStats` | `stats.batches` increments once after the draw path; it does not count each triangle draw, every barrier or the extra alpha-fail draw. | Existing `[gs-hw]` output cannot by itself confirm or exclude a draw-call explosion. CPU batch counts are not GPU elapsed time. |
| `src/lib/gs/gs_threaded_backend.cpp`, `PublishLocked` | Producer waits when the bounded pending-chunk queue is full. | Slow rendering/driver calls can propagate waits upstream toward VU1/EE. Queue wait time does not distinguish CPU submission, scheduling and GPU execution. Enlarging the queue cannot remove the rendering cost. |
| `src/lib/gs/gs_host_present.cpp`, `GSHostPresentation::renderFrame` | The HostWait scope wraps `EndDrawing`, including swap/pacing behavior. | High host wait alone is not proof of a GPU stall: the normal frame limiter also contributes. Correlate with guest/host rates and GPU completion. |
| `src/lib/gs/gpu/gs_gl.cpp`, `completed` / `PublishSharedTexture` | Shared presentation uses eight slots; fences are polled with zero timeout. Publication returns false if no slot is available. | This code does not explicitly wait indefinitely on its fence poll. Eight slots are not a global bound on all driver/GPU commands. Swap or other GL calls can still block implicitly. |
| `gs_hw_backend.cpp`, `Present` | Shared presentation copies on the GPU; the non-shared fallback uses `ReadPixels`. | Verify which path the affected runner actually takes. Do not assume all gameplay performs CPU readback, or remove required readbacks without tracking consumers. |

## Relevant existing evidence, not a reproduction

The [hardware history](../tested-hardware.md) records Waffle batching commits
`00bda7f`, `09ea6cb`, `91ac954`, `c558c21` producing approximately 62 game FPS
but only 0.2–2 Hz window presentation on RX 580, with a saturated GPU queue and
SwapBuffers blocking. They were excluded from patch 04. See also
[handoff section 8](handoff-2026-10-25-performance-phases.md).
This establishes a historical failure mode, not that these excluded changes are
present in the user's build or that the RX 5500 XT has the same cause.

VSync is reportedly off, so a VSync-specific explanation is not the leading
hypothesis. Investigate actual rendering load and presentation independently.
Driver behavior, VRAM pressure, clocks/thermal limits and scene-dependent shader
costs remain alternatives; none is diagnosed from utilization alone.

## Next discriminating measurements and acceptance gates

This is a new workload/hardware investigation, not a repeat of SYNC-01 through
SYNC-04 or the rejected VU chain experiments. Before any optimization:

1. Obtain the affected runner hash and effective scale/window/FXAA/VSync settings,
   actual GL renderer and driver, scene marker and guest/host FPS from the RX 5500 XT.
   Compare the above-deck and below-deck events separately. No fresh ISO recompilation
   is needed merely to collect a compatible prebuilt diagnostic runner's report.
2. If guest FPS remains high but host FPS collapses, prioritize presentation,
   driver submission and completed-frame availability. If both fall with backend
   queue waits, trace the GS critical path; this still does not prove pure GPU cost.
3. Add bounded, opt-in counters for actual main draws, per-triangle fallback draws,
   texture barriers, fast-path shadow passes and alpha-fail passes. Existing batch
   metrics are insufficient. Use asynchronous GPU timestamp queries with an
   availability check and bounded pending slots for GPU durations; never synchronously
   fetch every result or insert `glFinish` into the normal frame loop.
4. In an isolated diagnostic comparison, hold the scene/window settings fixed and
   compare 1x/2x. Strong scale sensitivity would support pixel/render-target pressure;
   unchanged stalls with high fallback counts would prioritize submission/barriers.
   This is an investigation control, not a requirement for players to tune settings.
5. Only then test a targeted change: extend an exact shadow fast path for the observed
   state, eliminate proven redundant passes/copies, or reduce presentation work while
   preserving game timing. Adaptive resolution would be a separate quality-policy
   change needing real GPU timing and validation, not a switch that currently exists.
6. Validate images/shadows/water/transparency, sound, guest pacing, host presentation
   and long-session memory on the same RX 5500 XT scene. RX580 testing is additional
   coverage, not acceptance for this board. Keep only measured improvements and make
   retained behavior automatic in the normal install/play flow.

## Primary references checked

- [Khronos synchronization](https://wikis.khronos.org/opengl/Synchronization): implicit
  synchronization and the distinct roles of flush, finish and buffer swapping.
- [Khronos sync objects](https://wikis.khronos.org/opengl/Sync_Object): zero-timeout
  client waits poll completion; they do not wait for the fence to become signaled.

This initial investigation changed documentation only. The subsequent
[LK report and shared-presentation contention work](shared-present-input-2026-11-03.md)
records a separate reproduced lock stall and correction candidate. It does not
establish the cause of the RX5500 XT saturation report or a universal FPS guarantee.
