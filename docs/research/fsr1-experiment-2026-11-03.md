# FSR 1 controlled experiment (GPU-03)

User-authorized implementation following the earlier feasibility record. This is
not a rerun of UI-01: that experiment compared bicubic/FXAA; this one uses AMD's
actual EASU and RCAS algorithms. Retention requires a repeatable FPS benefit and
acceptable visual quality, not merely successful integration.

## Implementation and identity

Official [FSR 1 source](https://github.com/GPUOpen-Effects/FidelityFX-FSR), commit
`a21ffb8f6c13233ba336352bdff293894c706575`; upstream MIT notices preserved in the
embedded shaders. `data/experiments/fsr62/sources.json` records downloaded header
hashes and the baseline runner hash. Uses portable FP32, not FP16/vendor extensions.

Isolated runtime candidate inserts EASU after the existing source-resolution FXAA
pass and RCAS at final output size. It replaces bicubic/sharpening when enabled,
uses the existing aspect rectangle and leaves overlays afterwards. The PS2 HUD
is part of the game image and cannot be independently reconstructed. Blank frames,
downscaling and bilinear mode retain their existing paths. Shader failure retains
the current scaler; render targets resize with the destination and are destroyed
on shutdown. `GOW_FSR1_TEST` is an experiment-only switch, not a player requirement.
No launcher setting or normal release patch is changed by this experiment.

The first real-GPU test rejected GLSL 400: AMD's helper uses `packHalf2x16`,
requiring a newer GLSL version/extension even in the FP32 path. The candidate was
changed to GLSL 430, matching the runtime's OpenGL 4.3 requirement. That failed
run is preserved in `data/experiments/fsr62/shader-test.log`; it is not a valid
FSR benchmark. No shader-failure fallback may count as an FSR result.

## Validation design

A real-OpenGL test exercises production `drawFsr` and official shaders, checks
asymmetric quadrant orientation with positive/negative source rectangles, and
measures isolated GPU elapsed time on an identical fixed input. This is scaler
cost, not game frame time. Fixed-image exports allow visual comparison without
camera variation. A visible gameplay smoke additionally checks shader activation,
VU1 parity, host screenshot and normal exit.

FPS comparison uses the same candidate executable with the experimental switch
off/on: current filter at 2x, current filter at 1x, FSR at 1x. Three interleaved
triplets, 100 seconds/run, 40-second warmup, complete-window accounting from
`worker-ab.py`, FXAA on, sharpen 0.4, output 1280x720, cap 60, VSync off, sound on,
precise VU1, GS early FINISH on, large-VIF barrier off. Private cards and the same
opening-ship real-time script; scene alignment is not deterministic. No builds
or profilers during FPS runs. Local Xeon/RX580 evidence cannot establish a gain
on Intel UHD, RX5500 XT, RX7600, NVIDIA or weaker machines. No GPU underclock is
used as a substitute for those hardware targets.

## Results and decision

**Rejected for adoption; original runtime/filter restored.** The real FSR prototype
worked, but did not meet the requested measured-gain gate. Nine valid game runs
(three per configuration), one invalid 2x-control presentation stall and one
metadata-finalization recovery are documented below. No FSR release patch,
launcher setting or installer is retained. The previous patch-61 correction is
preserved. Prototype source, executable, test harness, fixed-image exports and
raw evidence remain under ignored `data/experiments/fsr62`, including
`candidate-not-shipped.patch`; no game-derived artifact is published.

| Triplet | Current 2x FPS | Current 1x FPS | FSR 1x FPS |
| --- | ---: | ---: | ---: |
| 1 | 59.3818 | 59.2909 | 59.0182 |
| 2 (replacement control) | 59.7818 | 59.4909 | 59.6730 |
| 3 | 59.8000 | 59.3820 | 59.3273 |
| Mean of run means | **59.6545** | **59.3880** | **59.3395** |

FSR versus current 2x: -0.528%; versus current 1x: -0.082%. These small,
cap-limited route differences do not establish a general regression, but provide
no evidence of an FPS gain. FSR lost all three comparisons against 2x and two
against 1x. Median run-level window-p95 intervals were 16.702 / 16.707 / 16.698 ms,
respectively; no meaningful pacing improvement. Lowest five-second windows were
54.0 / 52.6 / 50.8 FPS; these are not instantaneous minimum FPS. No guest intervals
over 100 ms in the valid analyzed windows (startup excluded).

Consolidated machine-readable record: `data/experiments/fsr62/comparison.json`.
Every valid run has 11 complete post-warmup windows (~55 s). Source/runner hashes,
settings, shader activation and exit checks are retained. The invalid stalled
control remains outside the mean, not erased. Replacement-control timing and the
nondeterministic real-time script limit causal interpretation.

The isolated GPU timing consistently measured extra scaler cost (~0.135 ms;
~0.107 ms current versus ~0.243 ms FSR at this output size). The lower-resolution
FSR image was softer; no clear quality advantage over the existing 1x filter was
established. Lowering resolution also failed to improve FPS on this local route,
so a default resolution reduction is not justified by these measurements.

This does **not** prove FSR cannot help a genuinely GPU-limited weaker PC. Physical
Intel UHD/NVIDIA/RX5500 XT/RX7600 and the reported Hydra attack were not tested.
Reopen only with a materially different GPU-bound workload/hardware or a cheaper
implementation, preserving the 1x-current control and visible HUD/edge quality
checks. Do not repeat these same RX580 opening-route runs as if FSR were untested.

### Early real-GPU results

GLSL 430 shaders compiled. Positive and negative source rectangle quadrant checks
passed, including nonzero destination origin. The first orientation assertion
used a too-strict blue-channel threshold for raylib's RED (230,41,55); the fixture
was corrected to pure primary colors, without a runtime change. The first image
load used PPM, unsupported by this raylib build; it was rerun with the already
converted PNG. Logs `shader-test2.log` through `shader-test4.log` preserve these
invalid fixture runs.

`shader-test5.log`: six blocks, alternating current/FSR/FSR/current/current/FSR,
100 samples each with 20 warmup samples excluded. Same 640x448 image, 1280x720
output; source was downsampled from the saved 2x capture, not a real 1x rendering.
No FXAA in this isolated scaler test. GPU query spans drawing only, excluding
swap/readback; query readback synchronizes this microbenchmark and is not used
in gameplay. Median GPU milliseconds:

| Block | Current bicubic | FSR EASU + RCAS |
| --- | ---: | ---: |
| 1 | 0.108640 | 0.235200 |
| 2 | 0.104800 | 0.234720 |
| 3 | 0.108640 | 0.258560 |

FSR added approximately 0.13 ms on this GPU. The fixed-image exports were
visually inspected: correct orientation/HUD, a softer FSR image with less edge
contrast than the current sharpened filter. The same numeric sharpening value
is not a perceptual match between algorithms; no whole-scene quality acceptance
is inferred. Both scalers retain less detail than higher-resolution rendering.

Visible 100-second 1x/FXAA/FSR smoke passed shader activation, gameplay,
2000 VU1 parity runs with zero mismatches, host capture and graceful exit.
`data/experiments/fsr62/smoke/summary.json` records checks and runner identity.
A verification build ran concurrently during part of this functional smoke;
its FPS is explicitly excluded from performance comparisons.

Full `build.cmd -Stages verify` passed before the FPS runs: 12 CTest cases,
codegen/guest calls, VU1 equivalence/self-loop exits and task replay. The temporary
real-GPU test is run explicitly, not made a headless CI requirement. Local driver:
RX580 2048SP, 31.0.21924.61. Candidate runner SHA-256:
`0dd415d375c22875f299d89a393c54a48b0a43f8743a30dc614398d82071c3dd`.

Retention requires a repeatable advantage of the 1x+FSR configuration over 2x
current rendering, with acceptable quality; the 1x current control identifies
whether FSR is actually needed for that tradeoff. Differences around the 60-FPS
cap or between nonaligned script trajectories cannot establish weak-GPU gains.
A neutral or inconclusive result means restoring the existing runtime/filter,
while preserving the experiment and negative evidence for future agents.

### Invalid control run and resumed sequence

The sixth run (`ab/06-current2`, FSR disabled) produced guest `gow-frame` data
but no usable `gow-perf` windows, failed to close normally and was terminated by
the collector five seconds after its stop request (exit 62097). Guest probe
updates continued through 100 seconds. This is consistent with a host-side
presentation/event-loop stall, but no thread stack/GPU timeline was captured to
identify its cause. It is not attributed to FSR, which was disabled and never
compiled its shaders in that process. The run is excluded by the predeclared
window/exit checks; all raw evidence is preserved. The interrupted harness stops
on a failed run instead of averaging it away.

Resume sequence: repeat that invalid current-2x control, then finish the final
current-2x/current-1x/FSR-1x triplet. This is a replacement for an invalid test,
not a rerun selected by an unfavorable FPS value. Do not discard this stability
failure when reporting the experiment.

The replacement `resume/01-current2` completed gameplay and closed its window
normally; the collector returned zero and `events.jsonl` records exactly one
`process_exit` with code 0/state completed. However `session.json` remained at
state running without an exit code, causing the harness's metadata-only check
to reject it. This is a report-finalization inconsistency, not a second game
hang; the cause of the stale metadata was not established. The raw files and
initial failed summary remain untouched. A separate recovery record validates
the actual exit against the collector return code, exit event and window-close
log. The harness now permits that explicit fallback only when the metadata exit
code is absent, the collector returns zero and one completed/zero exit event
exists. Nonzero or conflicting exit data is never overridden. The final triplet
is run separately; no favorable-score retry is selected.

### Restoration verification

The original presentation source and test CMake were restored byte-for-byte;
the experimental shader include was removed. The isolated runner was rebuilt.
Every PE section matches the saved baseline except `.buildid`, including `.text`,
`.rdata`, `.data`, `.pdata` and TLS. This verifies the original executable code
and data were restored without rerunning the same completed gameplay experiment.
Evidence: `data/experiments/fsr62/restored.json` and `restored-build.log`.
Restored runner SHA-256: `07e5cedfe449e9776efb0fc3c3845b917c2bbdbe419069c7cb5f11ab2a463dd8`.
The previously delivered patch-61 diagnostic installer was not replaced.
