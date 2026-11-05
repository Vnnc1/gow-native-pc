# Intel HD 4400 report and renderer delivery follow-up

## Scope and provenance

Read-only investigation on 2026-11-04 at project revision `989f0ea`.
Inputs supplied by the maintainer: Desktop `chin/`, Desktop
`gow-render-engine-delivery-2026-11-04/`, and the screenshot of issue 25 reporting
60 FPS on an i3-4170 but disappearing character bodies. The screenshot is a
user report, not a benchmark or proof that these logs capture the same incident.
Instructions inside the delivery are reference material, not authorization to
replace the current runtime or execute its build instructions.

All 72 patch SHA-256 values recorded in `chin/session.json` match the supplied
delivery patch files byte-for-byte. This identifies the recorded source snapshot,
not necessarily the compiled executable: the session itself warns that local
source edits may not have been built. Runner identity:
`fac532bddcdd06b04dfff9674c8724755e6851334c2e474c30ed35b0272a69f8`.
`runtime.log` and `startup.log` are byte-identical; do not count them as two runs.

## What this log establishes

Maintainer clarification: the vanilla launcher goes black after the intro
cutscene; hardware compatibility is their hypothesis. Treat this as a separate
symptom from the issue screenshot's disappearing bodies. No exact incident time
or confirmation of continued input response was supplied. "Vanilla launcher"
does not identify the runner or negate the source snapshot recorded in this log.

Timeline relevant to that clarification: MPEG/IPU callbacks initialize at 25.395 s;
at 39.349 s the sound path sends command 0x3e, followed by repeated 0x40 calls,
and at 39.358 s a 640x512 target at fbp=104 is created. Guest flips become zero
in the window ending at 46.970 s. These timestamps narrow the transition to
inspect; they do not locate the movie's end or prove which subsystem stopped.
The first diagnostic priority is therefore movie-to-game progression (EE movie
state, IPU/DMA completion, audio state and GS publication), rather than treating
this session as only a slow GPU or the original ring corruption report.

- i3-4170, four logical CPUs, approximately 11.9 GiB installed RAM; actual GS
  renderer Intel HD Graphics 4400, driver 20.19.15.4531. Host context GL 3.3,
  separate GS context GL 4.4, hardware renderer ready and shared textures active.
  The host's 3.3 line is not evidence of a software-rendering fallback.
- Internal scale 1x, output 1024x768, VSync off, host limit 120, precise VU,
  x64 JIT inline enabled, audio enabled. No evidence of the issue title's
  unspecified "Lowest" configuration. The stored `filtro=fsr` name does not
  establish that official FSR 1 ran.
- `GOW_PERF_FRAME_PC=0x183BB8` matches the Japanese profile's frame probe.
  Runtime explicitly initializes SLPM-67010 IPU tables. The report's generic
  "Asian disc" wording is not a license to apply Japanese overlays to USA code.
  Exact disc identity still requires the profile/ELF text signature check.
- Six windows ending at elapsed 11.758–36.948 seconds report 19.62–30.77 guest
  flips/s (arithmetic mean 26.195). These include unknown game states and are
  NOT a controlled gameplay benchmark. The next window is 9.18 flips/s.
- All 25 windows ending at 46.970–167.078 seconds report zero guest flips,
  while host presentation reports 60.59–119.18 Hz. No further `gow-frame`
  intervals appear after 34.992 seconds. A high host counter cannot substantiate
  60 gameplay FPS. Missing scene/state evidence prevents choosing between a
  stopped guest path, movie/menu activity, a probe-coverage problem or other causes.
  Do not label this a reproduced deadlock solely from these counters.
- The collector reports exit zero after 169.121 seconds, no forced termination.
  Frames-only mode leaves scoped EE/VU/GS times at zero by design: those zeros
  do not establish zero work or identify the slow thread.
- Peak sampled private memory is 359.15 MiB and minimum available system RAM
  4745.34 MiB. This session does not support the previously reported multi-GiB
  memory-spike hypothesis. Process CPU samples span 67.81–181.18% of one core;
  this aggregate cannot rule out saturation of one critical thread. No GPU busy,
  GPU execution, queue-wait, clock, thermal or audio-underrun samples are present.
- Eight IOP modules report missing native code. This is a profiling lead, not
  proof that IOP interpretation dominates gameplay or that another recompilation
  would deliver a particular FPS gain.

## Delivery code versus the current branch

Reuse the [original correctness review](render-delivery-2026-11-04/README.md),
not a fresh identical performance experiment. Direct inspection confirms the
supplied source still contains the reviewed defects:

1. `gs_hw_backend.cpp::ringAppend` waits on the previous wrap's fence, inserts
   a new fence and immediately reuses offset zero. The first mapped wrap has
   no previous fence to wait on, and a second timeout/failure result is ignored.
   Prior mock-GL tests reproduced wrong ownership ordering. This can corrupt
   vertex data; it is a plausible disappearing-geometry cause, NOT a demonstrated
   explanation of the issue screenshot. The corrected overlay is already archived.
2. Original `GSThreadedBackend::SubmitRun` reads inactive vertex tails beyond one
   local object. Prior ASan tests reproduced it. Current patch 66 uses a real
   three-element array and preserves `q=1`, so importing the delivery wholesale
   would discard an existing correction.
3. `textureSourceUnchanged` hashes only up to the VRAM end. Wrapped source bytes
   are not covered; hash equality is insufficient for those spans. This remains
   a source-review risk, not a reproduction of disappearing characters.

The current production source has neither that `ringAppend` nor that
`textureSourceUnchanged`. Its patch 60 is a byte-budget/storage-reuse change,
not the delivery's patch 60; its patch 61 is nonblocking presentation, not the
delivery's patch 61. Patch numbers alone are not identities. Corrected grouping
66 is already present and default-off. Patches 72–74 are separate default-off
experiments with their own [RX580 evidence](patch66-67-rx580-2026-11-04.md).

The delivery's own verification explicitly claims no FPS gain. It measures
frontend cost reductions under hidden, 0.5x, audio-disabled, instrumented Japanese
runs. Those results cannot validate visible notebook play or override the current
frame-tail/audio acceptance failures. No original defect test was rerun here;
the existing evidence and unchanged relevant source were sufficient for review.

## Prioritized next work

For the clarified post-intro black screen, first compare normal startup against
FMV skipping in a controlled diagnostic build of the same regional runner.
Skipping is an isolation test, not a shipped workaround: success would narrow
the movie/transition path but would not distinguish IPU, audio, synchronization
and renderer-state faults by itself. Capture bounded thread/state evidence
during the black screen before applying an optimization. Shared-texture versus
readback presentation is a subsequent separate control if guest progression
continues. Preserve proper region overlays and collect the actual executable
identity for every run. The log shows successful GPU initialization; it supplies
no explicit shader/context failure proving a hardware compatibility defect.

1. **Identify the disappearing-body incident and guest progress.** On the affected
   machine/build, capture visible state at the incident with bounded telemetry
   and matching executable identity. If testing the original delivery, isolate
   its ring switch first (`GOW_GS_HW_RING=0/1`) with other settings fixed, using
   a separate build/private card. This switch is not a user-facing fix for the
   current branch, whose renderer does not contain the delivered ring.
   A repaired/segmented ring must prove current-region completion and capacity
   bounds before reuse, then pass geometry/depth/alpha tests on physical Intel.
2. **Reduce redundant host presentation work where measured.** The ordinary
   launcher currently defaults the window cap to 120 (`lanzador.cpp`), matching
   this report. Compare 60/120 on identical visible guest scenes with sound,
   accounting for repeated frames, guest intervals, GPU busy time and input
   latency. Shared integrated GPUs make this a useful resource hypothesis, not
   an established gain. Do not change the guest clock or silently tie simulation
   speed to the presentation cap. No default changed in this review.
3. **Complete the strongest unfinished VU1 criterion.** The archived scalar
   scheduling outline reported 561.8→507.8 us (-9.61%) on the notebook's isolated
   JIT replay, with baseline parity. It still needs independent replication,
   broader equivalence and actual hybrid/AOT gameplay validation. See
   [checkpoint](render-delivery-2026-11-04/resume-checkpoint.md). This is more
   concrete than retrying the already-inconclusive chain inline hint. The original
   corpus and binary hashes must be available; otherwise report that limitation.
4. **Target measured graphics work.** Evaluate sampler/shader candidates on
   Intel with correct image output before default promotion. Compare internal
   resolution only as a separate quality/performance experiment; never claim
   omitted geometry or changed game speed as an optimization. Investigate IOP
   native coverage only after thread samples show relevant cost.

The next notebook run should use the same hardware, disc, scene and settings
for baseline/candidate, include the runner hash and a marked incident time, and
separate lightweight FPS collection from detailed queue/thread timings. Neither
this analysis nor the issue's 60-FPS claim validates a weaker-hardware tier.

No runtime code, defaults, installed runner, disc or save was changed. No new
GPU benchmark or physical i3-4170/notebook reproduction was performed.

Subsequent authorized execution: [normal/skip-video isolation](black-intro-tests-2026-11-04.md).
The local reconstructed Japanese baseline reaches gameplay, including after
zero guest-probe windows during progressing FMV. This bounds interpretation of
the supplied log but does not reproduce its reported black screen. The original
affected executable is unavailable, as confirmed by the maintainer.
