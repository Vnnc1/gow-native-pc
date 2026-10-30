# Audio, standalone launch and graphics/mod compatibility

## Report and reproduction boundaries

The user reported 2-3 second missing attack/enemy/prop sounds near the opening ship fight and hatch, distorted speech
in the sailor/arrow scene, and progressive slowdown/pitch rise in save/load menus. The report concerns the PT-BR
translation, without a nearby save. Screenshots show 43 and 29 **guest FPS**, both with 60 Hz host presentation;
they cannot establish audio timing or the cause of the slowdown.

The installed copy is `Documents/test2`, using its own `C:/gow-build-c634ceb1-clang/ps2xRuntime/ps2EntryRunner.exe`.
`C:/gow-build-clang` belongs to a different checkout and is not a universal installation path. Read the launcher's
actual runner path / `data/build-root.txt` and `data/toolchain.txt` instead.

Local comparison: original ELF CRC D6385328 and translated ELF CRC 5444DDCB have the same .text SHA-1
`8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00`; all ten prepared IOP module files have identical SHA-256. Thus the runtime
fix applies to both code variants, but this does not prove that translated movie/audio assets are equivalent.
The last player log was preserved locally as `data/gow1/logs/reported-audio-translation.log`. It confirms JIT startup
but contains no audio underrun/rate statistics. It cannot retrospectively locate the missing sounds.

## Implemented corrections

Patch 24 widens the SPU2 master-volume multiplication before saturation in both `step()` and `mixBatch()`. A sum of
24 voices can exceed the range safe for a signed 32-bit multiply by a 14-bit volume. Previously the intermediate
wrapped and could invert the output polarity before the final int16 clamp. This is a demonstrated mixer defect,
not proof that every reported symptom has the same cause. `tools/test/sound_regression.cpp` exercises positive and
negative saturation with 2-48 simultaneous voices and draining the output queue. The original implementation fails;
the patched batch and `GOW_SND_PERFRAME=1` paths pass.

Patch 25 reads `gow-native.boot` beside the runner when no guest ELF argument is supplied. Explicit arguments retain
precedence. The pipeline writes initial defaults; starting through the launcher atomically saves the selected ELF
and runtime settings (only TOBIICHI_/PS2X_/GOW_ variables, never the entire environment). The standalone process logs
to `standalone.log` beside the executable. The profile contains local paths, is generated data, and must not ship.
After moving a disc or choosing another language, start through the launcher again to refresh it. A missing recorded
disc is reported in the standalone log. The game process remains the actual OpenGL renderer, not a wrapper process.

Installation now offers **Open game executable folder**. Performance offers optional **Audio and compilation
diagnostics**, enabled on the next launch: GOW_AUDIO_STATS, GOW_IOP_DRIFT, GOW_VU1N_DIAG and GOW_PERF_DIAG. It does not
enable raw audio recording or verbose per-register logs. Frame-rate validation must still distinguish guest frames
from host presentation; the scripted test gets the guest probe from the profile.

## Audio and menu issues still requiring evidence

The existing output resampler consumes a growing queue up to 5% faster, which also raises pitch. Removing it blindly
would replace sustained clock drift with periodic dropped samples. Measure `missing`, `dropped`, `rate`, buffer
levels, IOP grants and EE/VU/GS time during a long save/load dwell before changing the clock relationship. The mixer
fix does not remove this adaptation. Preserve saves and avoid automated save writes in reproduction tests.

Acceptance for the reported scenes: original and translated disc, audio enabled, opening fight -> hatch -> props ->
sailor scene; capture timestamps of each audible interruption, compare raw pre-output samples and output stats,
and repeat a >=5 minute load/save-menu dwell. Separate voice/stream starvation, output underrun, saturation, and
clock drift. The supplied screenshot alone is insufficient to select a renderer or scheduler fix.

## Widescreen / HUD

The runtime already has a real Hor+ 3D projection patch for 16:9/16:10/21:9, not just a stretched final framebuffer.
However its own `docs/LANZADOR.md` explicitly states that the HUD and 2D screens remain horizontally stretched.
The current upstream [PCSX2 patch](https://github.com/PCSX2/pcsx2_patches/blob/main/patches/SCUS-97399_D6385328.pnach)
also supplies projection/FMVs/menu-background corrections, not a complete HUD layout correction.

A safe HUD fix remains pending: trace the Flash/UI root transform and viewport separately from world projection;
preserve original 4:3 element scale, anchor left/right elements to the widescreen safe area, and transform clipping
rectangles consistently. Validate health/magic meters, boss bars, R2 prompts, subtitles, title/pause/save/load screens
and FMVs at 4:3, 16:9 and 21:9. Scaling every GS sprite or the final framebuffer would also distort world particles,
postprocessing and full-screen UI, so no such heuristic is enabled as a claimed fix.

## Driver effects and injectors (checked 2026-10-26)

| Feature | Current status | Required work / limitation |
|---|---|---|
| NVIDIA per-program profile | Select the actual runner shown by the launcher | Direct launch is supported by patch 25; selecting an executable does not change its graphics API |
| ReShade | OpenGL is supported by the upstream project; this build/injector combination is not yet tested | Target the 64-bit runner and OpenGL; start with color-only effects. Depth-based effects need testing against GS render targets |
| NVIDIA Smooth Motion | No supported native OpenGL path established | NVIDIA documents compatible DX11/DX12/Vulkan applications; investigate a renderer/presentation backend before promising support |
| OptiScaler | Not integrated | Upstream intercepts existing upscaler inputs on DX11/DX12/Vulkan. This port exposes neither that API path nor a temporal-upscaler input contract |
| DLSS 5 / third-party mods | No compatibility claim | NVIDIA describes neural rendering grounded in game-engine data. An executable name or copied DLL is not an integration; a specific mod must be evaluated separately |

Primary references: [ReShade](https://reshade.me/),
[NVIDIA Smooth Motion](https://nvidia.custhelp.com/app/answers/detail/a_id/5621),
[OptiScaler](https://github.com/optiscaler/OptiScaler/blob/master/README.md),
[NVIDIA DLSS 5](https://research.nvidia.com/labs/adlr/DLSS5/).

## Planned mod support

### ISO patches / xdelta

An ISO already patched with xdelta can pass the current importer **if** it preserves the supported ELF .text and
disc layout requirements. The PT-BR disc above already demonstrates a changed ELF CRC with unchanged .text. The
patch container does not determine compatibility: changed executable code/regions require a new port/profile and
regression tests. Do not bypass the current .text check.

Proposed installer flow: select owned base ISO + delta + new output path; verify the patch's expected base hash when
provided; decode with a pinned, checksummed [xdelta](https://github.com/jmacd/xdelta); write a temporary output without
overwriting the base; check decoder exit, output hash, SYSTEM.CNF/.text/TOC/PAK bounds; atomically publish the new ISO;
then run the existing identify/prepare pipeline. Record base/delta/output hashes and importer result in a manifest.
Test wrong base, truncated delta, cancellation, insufficient space, code-changing patches and translated FMV fallback.
This UI/decode stage is planned, not implemented in this delivery.

### Texture packs

The integration point is `gs/gpu/gs_texture_store.cpp`, after PS2 texture/CLUT interpretation and before GPU upload.
Phase 1: optional local dump with a versioned stable identity based on texels, dimensions, format, palette and mip
level; deduplicate, write asynchronously with bounded memory, exclude framebuffer/depth/feedback render targets.
Phase 2: pack manifest + PNG replacements, lazy worker decode, upload on the render thread, bounded VRAM/LRU, exact
fallback when absent/invalid; preserve alpha, indexed palettes, wrap/clamp and mip semantics. No frame-loop disk reads.
Phase 3: investigate a PCSX2-pack import mapping. Existing pack filenames/hashes must not be assumed interchangeable
with this renderer's texture keys. [PCSX2's feature history](https://pcsx2.net/blog/2023/q1-2022-progress-report/)
confirms dump/replacement support, but not cross-renderer pack compatibility.

Acceptance: original and translated assets; alpha HUD, animated CLUTs, tiled textures, mip chains and render-to-texture
scenes; invalid/oversized files; disabled-pack byte-equivalent output; measured upload stalls and VRAM budget on AMD
and NVIDIA. Ship tools/manifests, not copyrighted texture dumps. This is a roadmap, not an available replacement API.

## Local validation (RX 580, 2x OpenGL, clang Release)

- The deterministic mixer regression fails against the previous code and passes with patch 24 in batch,
  per-frame and verification modes (positive and negative 2-48 voice sums).
- Original and PT-BR translated ELF: 100 seconds each, audio enabled, scripted opening combat reached,
  2,000 VU1 comparisons / zero mismatches, graceful exit 0. Each has 17 consecutive five-second output windows
  after startup with `missing=0 dropped=0`. Fast boot has separate initial starvation/catch-up windows, excluded
  from the combat claim. The raw mixed audio and statistics are local under `data/gow1/logs/jit-hybrid-*`.
- These runs do not reach the hatch or identify the sailor clip, and do not prove the reported sounds fixed.

Reproduce with `powershell -NoProfile -ExecutionPolicy Bypass -File tools/test/jit-smoke.ps1 -Audio`;
add `-DiscElf <translated ELF>` for another prepared disc, or `-AllowMenu -Seconds 300
-PadScript "5:start,12:abajo,16:x"` for a load-screen dwell. `-Standalone` tests no-argument boot from an unrelated
working directory using the pipeline-created profile. All these tests close with WM_CLOSE and preserve saves.
For a manual reproduction, enable Performance -> Audio and compilation diagnostics, play the affected scene and
record the approximate time. Launcher logs rotate `ultimo.log` to `anterior.log` on the next run; preserve them
before starting several more sessions. Standalone uses `standalone.log` beside the actual runner instead.

The 300-second original-disc load-menu run reached the **no save data** screen (GS capture at 80 seconds), not a
populated save list. After the first 15 seconds all 56 measured five-second output windows have zero missing/dropped
samples. Guest FPS after 20 seconds: 54.17-58.99; the final six windows: 58.52, 56.60, 57.51, 57.76, 57.96, 58.31.
Exit 0, no forced termination, 2,000 VU1 comparisons with zero mismatches. No progressive collapse reproduced in
this state. A populated load/save list and the translated sailor/hatch scenes remain unvalidated.

No-argument standalone validation: 100 seconds, unrelated initial working directory, profile loaded, gameplay reached,
2,000 VU1 checks / zero mismatches, graceful exit 0. Final launcher build and Performance-page capture exit 0 with
empty stderr; the diagnostics toggle is visible without clipping at the tested window size.
