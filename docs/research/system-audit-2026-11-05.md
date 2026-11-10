# Runtime, installation and diagnostics audit — 2026-11-05

Scope: source inspection, regression tests, official upstream documentation and
local Xeon E5-2666 v3 / RX 580 2048SP validation. This is not certification of every
game scene, stable 60 FPS, other vendors, or a sub-20-minute clean installation.
Existing negative experiments in [the ledger](performance-experiments.md) remain
authoritative. No experimental performance switch was promoted.

## Corrections supported by reproductions

| Area | Demonstrated defect | Correction and limits |
| --- | --- | --- |
| Launcher | `restablecerAjustes` diverged from first-launch defaults: skipped movies, raised anisotropy, and retained intrusive diagnostics/experimental VU options. | Restore the effective defaults and disable optional texture packs without deleting their path. Real Main.qml regression exercises reset after changing these options. Internal scale remains the established 2x; this is not a weak-GPU preset validation. |
| Shader lifecycle | Failed shaders leaked; shuffle/presentation/CLUT programs were accepted without checking link status. | Patch 76 checks all raster links, releases temporary objects and reports mandatory presentation failure. Optional rejected CLUT compilation is not retried every draw. Seven fake-driver cases cover success and creation/compile/link failure. No shader-cache or FPS claim. |
| Sound reset | Fractional output-resampler phase survived clearing the sample queue. | Patch 77 resets phase under the same mutex. The old mixer fails the new sample/count regression after a 1.05x drain; the corrected mixer matches a fresh instance. This does not diagnose reported combat/movie dropouts. |
| PGO | Configure ignored failed profile eligibility and still used an existing `.profdata`; malformed JSON could abort selection. | Apply automatic PGO only with matching identity; accept matching shipped data or build unprofiled with explicit status. Preserve rejected local data when no replacement exists. Unprofiled builds may be slower: new runtime releases still need matched training. |
| Measurement provenance | Pipeline metadata reported `pgoHash` whenever a file existed, even for verification or an unprofiled build. | Label the legacy field as available data; record ordered successful game builds with resolved mode/applied hash. `pgoApplied` remains unknown when no game build was recorded. Failed builds cannot replace successful evidence. |
| Build dependencies | A persisted FFmpeg CMake ON value could survive the normal Windows configuration. | Explicit OFF in game/verification configuration, matching Linux/default policy. This excludes the optional unchecksummed MSVC prebuilt archive from normal builds; no measured build-time saving. |

## Confirmed sensitive paths and unresolved causes

1. **GS submission and destination-dependent blending.** `gs_hw_backend.cpp::drawOne`
   can issue one draw per triangle with intervening texture barriers. `stats.batches`
   does not count those actual calls or all secondary alpha passes. Removing barriers
   without preserving overlapping-fragment semantics is incorrect. The RX 5500 XT
   Hydra incident is still GPU-01, not reproduced by a capped ship-arrival run.
2. **Shader compilation.** The renderer has a fixed main/shuffle/presentation set,
   an optional specialized program and a lazy CLUT program. No per-material shader
   generation was found. Cold initialization/first-use cost needs measurement;
   sustained drops cannot presently be attributed to shader compilation.
3. **GPU memory and synchronization.** The decoded-texture budget excludes separate
   render targets. `gs-cache` bytes therefore do not measure total VRAM. CLUT and
   certain rendering/readback paths use synchronous `ReadPixels`. Queue wait and
   host pacing durations are not GPU execution time. The backend lacks the bounded,
   availability-polled GPU duration evidence needed to separate these costs.
4. **Audio supply.** The callback fills missing produced frames with silence;
   output-rate correction drains surplus rather than repairing sustained undersupply.
   Producer insertion, queue erasure and optional logging share the output mutex.
   These are source facts, not proof of significant contention on affected PCs.
   PCM diagnostic writes/flushes must remain outside clean FPS comparisons.
5. **VU1 and CPU compatibility.** Exact/JIT/helper references must stay available.
   The scalar-outline replay gain lacks valid gameplay acceptance; native coverage
   does not prove the absence of scheduling/GS waits. x86-64-v2 and OpenGL capability
   requirements cannot be removed by hiding the install gate. A lower ISA target
   needs an audited runtime/JIT/dependency path and physical legacy-CPU validation.
6. **Regional ownership.** The regional overlay test currently rejects
   `src/gow_overrides.cpp` against both stored baselines. Do not refresh hashes just
   to make it pass: regional snapshots need deliberate rebasing and their gameplay
   gates. Registration tests passing does not establish overlay compatibility.
7. **Source/binary provenance.** The downloaded runtime initially lacked the tracked
   scalar-outline and experimental-logic-rate patches from a merged branch. Their
   affected files were backed up under `data/experiments/audit-20261105/` before
   completing the chain. A launcher version alone cannot identify compiled runtime
   behavior. Failed or old binaries/logs cannot be treated as current acceptance.

## External architecture and tools: applicable boundaries

[N64ModernRuntime](https://github.com/N64Recomp/N64ModernRuntime) separates runtime
services from the recompilation bridge; [RT64](https://github.com/rt64/rt64) owns N64
rendering with deferred work, texture decoding and specialized/fallback shaders.
The useful adaptation is explicit ownership and a testable rendering boundary.
Its RDP renderer is not a substitute for PS2 GS/VU semantics.
[OpenGOAL](https://github.com/open-goal/jak-project/blob/master/docs/project-overview.md)
uses recovered game semantics and a GOAL toolchain. A comparable game-specific
renderer here would require semantic recovery and campaign-wide correctness work,
not simply selecting another graphics API.

[OpenGL program binaries](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_get_program_binary.txt)
can reduce later startup compilation, but may become incompatible after hardware
or driver changes. Any future cache needs source/version/driver identity, bounded
storage, failed-load rejection and source fallback. A distributable universal
AMD/Intel/NVIDIA shader binary is not supported by this mechanism.

| Tool | Appropriate use and boundary |
| --- | --- |
| Existing PDH sampler + frame/queue collector | Cross-vendor Windows process CPU and busiest GPU-engine utilization, frame tails and audio supply. Utilization is not GPU milliseconds or power. |
| RenderDoc | Inspect OpenGL draws/resources/pixels; captures perturb execution and do not establish normal FPS. See [project](https://github.com/baldurk/renderdoc). |
| NVIDIA Nsight | Check API/activity and device support. [Frame debugger support](https://docs.nvidia.com/nsight-graphics/UserGuide/appendix.html) differs from [GPU Trace hardware requirements](https://docs.nvidia.com/nsight-graphics/UserGuide/gpu-trace-overview.html), which require Turing or later. No local NVIDIA available. |
| AMD RGP | [Supported API/hardware matrix](https://gpuopen.com/manuals/rgp_manual/) targets DX12/Vulkan and current supported GPUs; it is not a direct profiler for this RX580 OpenGL renderer. |
| Intel GPA | [Windows OpenGL is trace-only in the documented matrix](https://www.intel.com/content/www/us/en/docs/gpa/get-started-guide/2023-3/overview.html). Do not promise GL shader timing on an old UHD from the tool name alone. |

Vulkan remains a separate prototype in [the API roadmap](graphics-api-roadmap.md),
with OpenGL as oracle/fallback. No API guarantees 60 FPS or eliminates EE/VU cost.

## Dependency control and installation target

Runtime commit and portable-tool/Qt archives are pinned. Nine active CMake source
dependencies use version tags: ELFIO, toml11, fmt, libdwarf, rabbitizer, raylib,
imgui, rlImGui and xxhash. Studio's floating branches are excluded from the normal
build. Version tags can move; immutable source archives with SHA-256 and controlled
mirrors are a smaller independence improvement than reimplementing these libraries.
[CMake recommends commit hashes](https://cmake.org/cmake/help/v3.31/module/FetchContent.html);
changing shallow clones to arbitrary commit hashes also needs compatible fetch logic.

The recorded full tune result is 24.1 minutes on its documented Xeon/16-GB setup.
An existing 304-second fetch/build/verify result reused artifacts and is not a cold
install. Matching shipped PGO, cache reuse, stable generated timestamps and existing
RAM-aware jobs should be retained. No new evidence establishes a clean build under
20 minutes. Track downloads, Qt SDK bootstrap, generation, training and final compile
separately when measuring that target.

## Next performance acceptance work

Prioritize GPU-01's missing actual draw/barrier and GPU-duration evidence, aligned
Hydra/late-scene reproduction, and audio missing-frame correlation. Gather cold and
warm runs on the affected Intel/AMD/NVIDIA devices. Then optimize the measured path
with equal images, sound, guest timing and p95/p99 gates. Do not repeat rejected
batching, spin, FSR or VU variants without the ledger's required material change.

Local artifacts and final validation results are recorded below; captures/cards
remain ignored and are never included in packages.

## Validation record

Local hardware: 20 logical CPU threads, approximately 16 GiB physical RAM,
RX 580 2048SP driver 31.0.21924.61. Test output is under
`data/experiments/audit-20261105/`; full pipeline detail is `verify.log`.

| Check | Result |
| --- | --- |
| Python pipeline | 17 passed |
| Linux orchestration | 7 run, 1 native-Linux lock test skipped on Windows |
| PowerShell pipeline/configure | Passed, including PGO identity, FFmpeg, configure invalidation, progress and environment restoration |
| CHD/disc import with pinned real chdman | 14 passed, including synthetic round trips |
| Disc preparation | 3 passed |
| Regional registration | 4 passed |
| Regional overlay baselines | Failed for Japan and Europe at `src/gow_overrides.cpp`; repeated after completing the source chain, still rejected |
| Diagnostic package metadata | 2 passed |
| Deployed session collector | 11 passed, including native/JIT metric parsing, exit codes, redaction and export |
| A/B methodology | GS and worker suites passed (scene/frame/audio gates, process identity, private cards, invalid-run rejection) |
| Real QML | Regional play/reset, disc import, loading progress and QTE controls passed |
| Launcher language keys | Passed; 57 existing English fallback keys per supplementary language remain |
| Mixer reset differential | Old implementation fails; corrected implementation passes default/per-frame/verify modes and existing saturation/envelope cases |
| Full `fetch,verify` | Passed complete ordinal chain, 18 CTest groups, synthetic ELF/codegen/guest calls, VU1 generated/JIT/helper/SSE/special-value/self-loop equivalence and bounded task replay |

Full verification took 238.457 seconds with reused artifacts, not a cold install.
The subsequent game build explicitly rejected the old local PGO manifest. Its
functional results must not be compared as a performance A/B against the preserved
PGO runner. The available-profile hash in that run's older metadata is not proof
that PGO was applied; the configure log is explicit.

The earlier scalar-smoke raw artifacts referenced by the notebook report are
not available in this checkout. Its missing native/JIT metrics remain unresolved:
current emitter, collector and smoke field names agree, and the collector's
synthetic metric integration passes. Do not relabel that historical run successful.

The first new shader patch export used CRLF and failed application to a temporary
Git index. Converting the patch to LF fixed it; the complete ordinal chain then
passed fetch's tree comparison. This failed attempt is not omitted from the record.

## Release build, real GPU and remaining audio failure

`sync,build,launcher` completed in 706.974 s using existing tools, dependency
sources, generated EE code and Qt SDK. The game stage took 644.650 s; this is
not clean installation/training time. A subsequent no-op build exercised the
new provenance fields end to end: `mode=off`, `pgoApplied=false`, applied hash
absent, available old hash retained separately.

On the RX580, the preserved pre-audit renderer fixture and newly linked fixture
both passed seven variants of 384 frames. Every corresponding old/new color
digest matched (2,688 comparisons), including specialized-shader fallback and
nonuniform CT32/T8/T4 textures. This does not prove full-game depth/render parity.
Artifacts: `pixels-reference/`, `pixels-candidate/`, `pixel-cross-comparison.json`.

Two visible 150-second normal-boot smokes used 2x internal scale, FXAA, early GS
FINISH, audio and private cards. Both passed all 11 functional gates: gameplay,
2000 VU1 parity checks, metrics, marker, export and graceful exit zero. Inspected
GS captures show the menu and ship gameplay. The rebuilt collector's 11 integration
tests and the compiled regional ownership/hash/save/cache suite also passed.

**Audio quality did not pass a zero-missing-frame criterion.** Functional smoke
checks metric presence, not silence-free playback. Observations:

| Session | Startup missing frames | Transition missing frames | Dropped frames |
| --- | --- | --- | --- |
| `session-game-20261105-180405`, captures enabled | 7085, window ending 7.702 s | 1646, ending 87.702 s | 0 |
| `session-game-20261105-180745`, captures disabled | 6605, window ending 7.074 s | 1036, ending 87.075 s | 0 |

Each session recorded 29 audio windows and 6,960,000 requested audio frames.
These are audio sample-frame counts, not game frames. The transition failure
persisted without captures; capture overhead is not its sole explanation. Two
runs do not establish the size of a capture effect or a root cause. Native/JIT
metrics were present in both; this does not retroactively explain the notebook's
historical missing metrics.

The second run also contains a gameplay window of 57.18 guest Hz with p99 35.263 ms
around 97 s collector time. No stable-60 claim follows from these instrumented
functional runs, nor a regression attribution to a specific patch. Movies have
long intervals without this guest flip probe; do not call the FMV interval a
gameplay stall. Subjective audio listening and sustained combat were not validated.

Candidate runner: `C:/gow-p6667-clang/ps2xRuntime/ps2EntryRunner.exe`, SHA-256
`fb7c21ac35ebc7f1c1cecb073186a399bb4fe236a6e47addf731dc205064b045`.
The normal launcher was rebuilt, but its active build-root marker was restored to
`C:/gow-q59`; the previous PGO runner is preserved. Runtime source fixes require
a matching rebuilt runner and validated release profile before public delivery.

### Transition localization and next discriminating test

The no-capture deficit belongs to the **82.075–87.075 s window**, which includes
gameplay beginning at 82.384 s; it is not a timestamped event at 87.075 s.
At 48 kHz, 1036 frames equal 21.58 ms of accumulated missing audio, not necessarily
one continuous gap. The captured run's 1646 frames equal 34.29 ms accumulated.
The preceding and subsequent audio windows have no missing frames in both runs.

`sceMpegDelete` and `sceMpegReset` in `MPEG.cpp` clear/recreate MPEG state but do
not directly clear the host sound output queue. `SoundEngine::reset` does clear
that queue, and global IOP/ELF/SIF-reset paths can reach it; existing logs cannot
prove whether one was called in the transition. `initCore` preserves the output
queue. Coarse IOP grant windows remain regular but cannot exclude a short producer
pause. VU verification finished at 5.129 s in the no-capture run, and JIT compiled/
unsupported counters were zero at the transition; those observations do not point
to an active verifier or JIT compilation as its cause.

The smallest next diagnostic change is a bounded record of reset count, last
producer publication time/batch, underrun event time/deficit and output-mutex wait.
Buffer events and write outside the audio callback. This distinguishes queue reset,
producer undersupply and callback contention before changing buffering/resampling.
No such tracing or speculative buffer enlargement was installed by this audit.
