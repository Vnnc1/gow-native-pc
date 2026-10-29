# Tested hardware and results

## Loading progress correction (2026-10-29)

The install log contained nested CMake dependency counters (`7/7`) followed by the real game build (`1/558`).
Those were incorrectly mapped to the same weighted stage, showing about 78% and then 37%. The pipeline now ignores
regeneration counters until the outer CMake build resumes; raw logs and build commands are unchanged. The overall
loading bar retains its highest valid weighted value and reaches 100% only on a successful pipeline exit.

Validation: 14 Python pipeline tests, the PowerShell pipeline suite (including mocked Build-Game output, no-op and
failure cases), and the actual LoadingScreen QML driven by fake signals pass. QML checks cover intermediate
property updates, stage transitions, revised totals, malformed counters, retries, failures, PGO and success.
The tests did not invoke a game build or modify/restart the installation already compiling in `Documents/test2`.
This is source-level validation; the previously delivered installer and the running launcher are unchanged.

## Patches 30–35 integration (2026-10-29, Xeon; synthetic checks)

Checkout: `C:/Users/dzvini/Documents/gow-claude/gow-native-pc`, with the supplied changes adapted as documented in
`docs/research/patches-30-35-integration.md`. Hardware: Xeon E5-2666 v3; the synthetic GS initialization reports an
RX 580 2048SP. Compiler: pinned llvm-mingw Clang 23.1.4. Regression build:
`C:/gow-build-c75e3561-verify-clang`, Release, x86-64-v2, ThinLTO off, object cache disabled.

- All patches through 35 replay from the pinned runtime commit and reproduce the runtime working tree exactly.
- `build.cmd -Stages verify -CompilerCache none` passes: Python and PowerShell pipeline regressions, synthetic ELF
  generation/synchronization, guest-call parity/diagnostic modes, 81 memory/DMA tests, 68 codegen tests and frame metrics.
- The separate VIF1 worker regression passes explicit enable/disable, asynchronous-FINISH fallback, per-instance
  configuration and the small-packet bypass, while preserving the count of two DMA submissions.
- VU1 generated DLL, inline x64, helper x64, forced SSE and no-speculation digests match for seeds 1, 4, 7, 11 and 23
  (one procedural image and three measured trials per seed, 24 programs per image). Special-value inputs also match
  with speculation enabled/disabled. Deterministic self-loops at 7 and 20,000 cycles match generated unchained code,
  generated chained code and both JIT tiers, including native-block counts (9 and 20,001 over three trials).
- A separate two-translation-unit executable and static library compile, link and run successfully with explicit
  ThinLTO, hidden visibility, the new math flags and lld's two-job limit. This is a toolchain smoke check, not a full
  game ThinLTO build or a build-time comparison.

Local evidence: `data/verify-patches-30-35-final.log`, `data/gow1/logs/vu1-equivalence/vu1-equiv-k06j7ngc/`, and
`data/thinlto-probe/`. This checkout has no prepared discs or generated EE game sources. Full game/launcher rebuild,
visible gameplay, sound, first-visit stalls and FPS are not validated for this series. No hardware support tier or
performance improvement is claimed.

## Branch review (2026-10-28, Xeon / RX 580)

`prototipo-claude` at `2e0f0cf`, plus the local review corrections below. Hardware: Xeon E5-2666 v3
(10 cores / 20 threads), 17,012,953,088 bytes of RAM, Radeon RX 580 2048SP, driver 31.0.21924.61.
The existing Maximum Performance power plan was read, not changed. This is separate from the laptop evidence.
The recorded build directory was absent; other available builds belonged to different checkouts. All game tests
here use the newly built `C:/gow-build-44a8e3b6-clang/ps2xRuntime/ps2EntryRunner.exe` and the prepared USA disc.

### Review corrections and checks

- Generated-file synchronization failed twice with Windows error 5 on different files. Bounded atomic-replacement
  retries resolve transient Windows denials while preserving targets and propagating persistent failures.
  All 14 Python pipeline regressions pass, including recovery/failure preservation.
- Windows tar could not extract the Qt XZ archives without an external `xz` executable. The pinned Python now
  streams XZ into a temporary plain tar. The PowerShell fixture and all three real Qt source extractions pass.
- The collector omitted real `[vu1n]` / `[vu1x]` rows from structured metrics. Both tags now parse; seven deployed
  collector integration tests pass, including the new assertions, redaction, export, crashes and parent exit.
- The implemented Saves page had no sidebar entry. Page 7 is now reachable and renders without QML errors.
  Previewing it did not create, import, delete or restore player saves.
- Runtime `verify` passes: 80 memory/DMA cases, 68 code-generator cases, guest-call/codegen scenarios, synthetic
  ELF generation, frame metrics and the PowerShell pipeline suite. The patch chain applies through 29f.
- AOT, JIT-only and forced-SSE4.1 JIT checks each reach gameplay, verify 2,000 runs without mismatches and exit 0
  without forced termination. Both JIT-only runs compile 623 blocks with zero unsupported blocks. These checks used
  intrusive diagnostics; the JIT-only checks overlapped Qt compilation and are not FPS benchmarks.
- Standalone startup using only the boot file passes gameplay/parity/exit checks and restores byte-identical boot
  contents. The real-game collector check passes all 11 assertions, including native/JIT metrics and marker export.
- Qt's 24 sorting compatibility cases pass. The deployed launcher starts with only Windows directories on PATH,
  recognizes the game as installed and exits 0 after its screenshot, with empty stderr. The deployed collector
  remains byte-identical to the binary that passed its integration tests after the sidebar rebuild.
- The real compiler-cache fixture hits with identical output, and replacing PGO data at the same path misses the
  cache and matches uncached compilation. This small fixture is not a game-build speedup measurement.

### Build observations

Clang 23.1.4, Release, existing PGO profile `54e4abaf0077464918e0e34425c4c03ce23542193331a72a22645eb27cdb33fa`,
ThinLTO off, seven parallel compilers and 9,480 existing VU1 images. New native analysis generates 1,897 blocks;
one unsupported block retains its fallback. No whole-game native-coverage claim is made.

| Operation | Seconds | Scope |
|---|---:|---|
| Real EE generation | 55.329 | 6,418 C++/header files; first attempt before the synchronization correction |
| Successful game compile/link | 1,041.542 | New build directory, existing PGO/native inputs; not a comparison against an older compiler |
| Successful recomp/sync/build invocation | 1,136.719 | Includes the post-fix EE generation and synchronization |
| Unchanged recomp/sync/build | 28.731 | Sum of successful stages before the independent Qt extraction failure; zero copied files or compilation |
| First launcher invocation with matching Qt | 2,559.033 | Includes source bootstrap of QtBase, QtShaderTools and QtDeclarative, launcher build and deployment |
| Incremental launcher/sidebar rebuild | 30.975 | Reuses the completed Qt SDK |

Unchanged EE hash validation takes 3.951 s; the unchanged Ninja game stage takes 1.359 s. Most remaining no-op time
is synchronization/hash I/O (18.061 s), a candidate for further profiling. Compilation-process working sets sampled
every five seconds peak at 4,108,992,512 bytes; sampled private bytes peak at 3,692,318,720. Sampling began during
the C++ stage, so this is not a guaranteed peak for the entire dependency/bootstrap pipeline.

### Visible/audio FPS comparison

Six 120-second runs, alternating lean/full order, fresh private-card paths, 60 seconds of warm-up per run,
1280x720 visible window, fixed 1x scale, 16:9, FXAA/VSync off, hardware GS worker and asynchronous FINISH.
Host cap: 120 Hz. Frame accounting/distributions and audio statistics are enabled; per-call timing, detailed VU1/IOP
counters, verification and captures are disabled. No compiler or build process is active during these runs.
Each run supplies eleven warmed five-second FPS windows and exits 0 without forced termination.

| Call mode | Run means (guest FPS) | Mean | Five-second range |
|---|---|---:|---|
| Lean (default) | 57.77 / 54.66 / 57.54 | 56.66 | 50.58–59.79 |
| Full dispatch reference | 58.36 / 57.24 / 58.18 | 57.93 | 53.37–59.99 |

The default mode is 2.19% lower in this observation. This does not demonstrate an FPS gain or establish a causal
regression: input follows real time, simulation progress differs, three runs provide limited repeatability, and
temperatures/clocks were not collected. The same executable's dispatch switch does not recreate main or the entire
older patch stack. **Stable 60 guest FPS is not achieved by this test.** All warmed audio windows have zero missing
or dropped samples; none of the warmed guest-frame intervals exceed 100 ms. These are guest intervals, not GPU or
display latency. There is no listening-test or whole-game audio certification.

Across the warmed windows, median p95/p99 guest intervals are 20.049/27.002 ms (lean) and 19.869/26.042 ms
(full). Worst intervals are 41.663 / 36.505 ms respectively. These are medians of individual five-second-window
percentiles, not a percentile computed from all raw frames in the session.

The local benchmark driver initially rejected the first run because its gameplay matcher expected adjacent fields;
the raw line contains `pending` and `stage` between them. Its matcher was corrected, the raw logs validated, and
the remaining runs resumed with unchanged settings/binary; the first measurements were retained.

### Remaining review findings and acceptance limits

- **Open: cross-instance save protection.** `Lanzador::jugando()` sees only its own `QProcess`. Closing the launcher
  leaves the game/collector alive, but a fresh launcher has no such process object. `restaurarPartida()` therefore
  does not reject that running game, and `iniciar()` can also start another instance. This violates the closed-game
  restore requirement. Add a reliable running-session/card guard before treating Saves as fully accepted. This is
  a source-review finding; no restore was attempted against a running player's card.
- A host back-buffer snapshot omitted the HUD in both a JIT run and an AOT control, while other internal/host
  snapshots show it. The captures are not the same guest frame and the omission is not isolated to JIT/AVX.
  HUD correctness/fade behavior remains an observation to investigate, not a confirmed new regression.
- No classic/locals frame-exact GS differential, Athens/heavy-area coverage, PT-BR movie check, 30-minute sustained
  session, installation/uninstallation registration or NVIDIA validation was performed. The roadmap gates remain open.

Local evidence (ignored): `data/gow1/logs/branch-review-20261028/` (settings, six session directories, FPS summary,
build-memory samples and launcher captures), `review-20261028-*.log`, `jit-hybrid-20261028-201103/`,
`jit-jit-20261028-203017/`, `jit-jit-20261028-203334/`, `standalone-20261028-204257/` and
`session-game-20261028-210121/`. Review changes remain local and uncommitted; no game-derived assets belong in Git.

## Next-phase memory gate and gameplay checks (2026-10-28, i5-8265U laptop)

Branch `claude/keen-dirac-42wd1y`, base `4283ea2` plus patches 29d–29f. Same prepared PT-BR disc, Intel UHD 620,
fixed 1x rendering, visible 1280x720 window, audio enabled, scripted ship sequence and a private card per run.
These are correctness/profiling checks, not a controlled before/after performance comparison.

- The old memory suite initially failed to compile against removed native-DMA APIs. Restoring compilation exposed
  20 failing cases out of 79. Migrating obsolete DMAC/CPU-rasterizer expectations preserved texture uploads and
  primitive state/vertices through the real texture store and backend boundary. Two actual bugs remained:
  scratchpad chain completion restored STR, and MMIO VIF/GIF submissions inflated the DMA counter.
- Patches 29e/29f correct those defects. The isolated memory suite now passes **80/80**, including both scratchpad
  directions, single completion, preserved mode, direct/empty/chained/MMIO counter paths and reinitialization.
  This is not a claim that the entire upstream `ps2x_tests` executable is repaired.
- `build.cmd -Stages fetch,verify,build` passes: the complete patch chain matches the working runtime, 11 Python
  pipeline tests plus PowerShell cases, synthetic ELF generation, ten guest-call scenarios, 68 codegen cases,
  frame metrics and the 80 memory cases. Incremental game build/link: **11.602 s**; whole pipeline: **54.848 s**.
  Existing dependencies/cache were reused; this is not a cold build or EE recompile measurement.
- Two 100-second visible gameplay runs (frames-only and intrusive timing) both reach `state=11, levelReady=1`,
  verify 2,000 VU1 executions with zero mismatches, export valid local reports and exit 0 without forced termination.
  Report checks also cover process memory, audio/IOP metrics and the player marker. No compiler ran during gameplay.

Frames-only run: over eleven complete five-second windows starting after 40 seconds, weighted guest frequency was
**23.36 Hz**, with window averages **16.58–27.96 Hz**. Window p95 was **54.227–91.896 ms**, p99 **65.053–166.130 ms**.
The 60 fps gate remains open. This visible/audio run cannot establish a regression or gain against the earlier
hidden/audio-off 42.90 Hz measurement. No listening assessment, image-parity comparison, thermal sensors or
three-run reproducibility are claimed. Frames-only audio windows collected after 40 seconds have zero missing or
dropped frames; startup did report missing frames.

The separate intrusive run averaged per five-second window: VU **4148 ms**, EE **2241 ms**, GS **2270 ms**, IOP
**917 ms**, guest wait **1850 ms** and host wait **4785 ms**. These are wall-time scopes on overlapping threads,
including scheduler waits, not additive CPU percentages or GPU timings. It also logged **11,822 missing audio
frames** after 40 seconds (zero dropped): detailed timing is not a transparent performance probe or an audio pass.
The smoke harness checks presence of audio metrics, not zero underruns. Reproduce this separately before attributing
the underrun to a particular subsystem.

Both runs report zero native VU1 misses in the sampled interval. In the frames-only run, self-loops account for
about **31.6% of native pairs** and **12.7% of native blocks**. Prioritize profiling VU1 execution/chain timing and
EE/VU1 synchronization (roadmap 34/35); a larger JIT coverage effort is not justified by this ship trace. Keep the
patch 30 address-boundary/MMIO differential gate and require repeated comparisons before enabling a new fast path.

Evidence under `data/gow1/logs/`: `phase-next-validation.log`, `pipeline-20261028-164743-172.json`,
`phase-next-summary.json`, and `session-game-20261028-164759` / `session-game-20261028-164946` (checks, raw logs,
metrics, session metadata and exported ZIP). Runner SHA-256:
`515a5bdbf91d6fdda3fee5f953d231d33119da8fdbc1d5ff49b3996ad738d682`.

## Session diagnostics validation (2026-10-28, i5-8265U laptop)

Patch 29c and the separate Clang/Qt `gow-session` collector add local player reports. This is instrumentation,
not a performance optimization. The existing ten guest-call scenarios and 68 codegen cases pass, alongside new
frame-window checks for nearest-rank percentiles, invalid values, budget boundaries, fixed-storage overflow and reset.
The full 01–29c patch chain applies and matches the runtime; game and launcher builds succeed.

Seven real child-process integration cases cover crash code `c0000005`, nonzero exit, failed startup, process metrics,
audio parsing, path/email redaction, exclusion of saves/ISO/environment secrets, markers, stop requests, bounded log
rotation, ZIP CRC/integrity, oversized-input rejection and collection after the launching parent exits. An initial
failed-start test exposed an exit-before-event-loop race in the collector; it is fixed and covered by the suite.

A 100 s prepared PT-BR gameplay run with sound enabled and a hidden window reaches `state=11`, `levelReady=1`;
2,000 VU1 comparisons report zero mismatches. The report contains guest interval distributions, process memory,
audio and IOP windows and the player marker. The stop request exits 0 without forced termination. Exported ZIP
contents validate independently. Evidence: `data/gow1/logs/session-game-20261028-161551/checks.json` and `report.zip`.
This is functional coverage, not a listening test, a visible-presentation certification or a controlled FPS comparison.

The Portuguese Other page renders the report export and marker controls; startup with only Windows system
directories on `PATH` exits 0 with empty stderr. Evidence: `data/gow1/logs/session-diagnostics-ui.png`.
Remaining measurement limits: collector overhead has not been quantified in paired game runs; actual GPU/display
presentation latency, GPU utilization/VRAM and temperatures are not collected. See [report semantics](reporting-bugs.md).

## Build foundation validation (2026-10-28, i5-8265U laptop)

Windows, Intel Core i5-8265U, 24 GB RAM, Intel UHD 620 / Radeon 520; pinned llvm-mingw 20261020 (Clang 23.1.4).
This is a different machine from the Xeon/RX 580 gameplay measurements below. The supplied PT-BR standalone
translation (ELF CRC `D95720D3`) was identified as compatible and prepared successfully.
The owner confirms that this laptop is less powerful than the earlier RX 580 desktop. Keep hardware baselines
separate: lower absolute FPS here does not establish a regression, and elapsed build times cannot be transferred
to the desktop. Compare changes on the same machine, driver, power plan, scene and settings.

- Eleven behavioral pipeline tests pass, plus PowerShell checks for configure reuse, PGO-content invalidation,
  profile paths with spaces, cache opt-out and recording environment restoration on success/failure.
- Real generation from a synthetic MIPS ELF passes in locals/classic modes; repeated inputs skip generation,
  forced identical output preserves timestamps and synchronization makes no unnecessary copies.
  The actual supplied ELF generated 6,418 C++/header files in 134.703 s (generation/publication timer).
- `build.cmd -Stages verify` builds and passes ten isolated guest-call scenarios and all 68 codegen cases.
  The pinned general memory suite still needs an independent repair of stale API references before patch 30.
- A real one-object cache fixture measured 5.302 s cold / 0.402 s warm (cold includes daemon startup), with an
  identical object hash and one cache hit. This is **not** a full-game compile-time or FPS measurement.
  A second fixture confirms same-path PGO replacement misses the cache; output matches an uncached control after
  normalizing COFF timestamps (two hits, three misses in the combined test, no unsupported/failed compilations).
- Clang-built installer: synthetic package round-trip verifies two files, one LZMS block, 357 unpacked bytes;
  imports are Windows system/UCRT DLLs, with no Visual C++ or libc++ runtime DLL requirement.
- Invalid stage and concurrent pipeline invocations return exit code 1 through `build.cmd`; PowerShell syntax
  parsing passes.
- Final `fetch,verify,launcher` validation passes with the complete 01–29b patch chain. The Clang Qt 6.8.3 SDK
  passes 24 sequence-sort compatibility cases. The deployed launcher starts and exits 0 with compiler/SDK paths
  removed from `PATH`, displays the prepared PT-BR disc and reports the game ready; stderr is empty.
  Fixed installation-time estimates were removed because duration depends on hardware and cached artifacts.
- The first real pipeline (`fetch,discs,configure,recomp,sync,build`) completed in 2,005.895 s; the game build/link
  stage took 1,625.804 s. After cleaning the runner target's 956 build outputs with Ninja, the same build/link
  stage completed in 31.344 s with the populated local object cache (98.1% less elapsed time). This compares a
  cold and warm object cache on the same Clang code/configuration, not Clang versus MSVC or a compiler speedup.
- A stable `recomp,sync,build` invocation with unchanged inputs completed in 9.369 s: 2.721 s recompiler stage,
  5.955 s synchronization, 0.272 s game build; no generated source was copied. The first cache-hit generation
  validation itself took 2.090 s versus 134.703 s for generation/publication. Fetch/disc preparation are excluded.
  Raw reports: `data/gow1/logs/foundation-{cold,stable-noop,cache-rebuild}-pipeline.json`.
- First-install gameplay smoke: 100 s, PT-BR disc, Intel UHD 620 / OpenGL 3.3 driver 27.20.100.9664, hidden
  1280x720 window, 2x dynamic resolution, audio off, no previously recorded AOT/IOP code. Gameplay reached;
  2,000 VU1 comparisons passed, 623 JIT blocks compiled with zero unsupported, process exited 0 without forced
  termination. The 80 s capture shows the ship, characters, textures and HUD. Eight diagnostic windows at
  t >= 60 s measured 11.91–20.79 guest FPS (median 15.49). This instrumented JIT-first smoke is not a controlled
  FPS comparison with prepared native code. Evidence: `data/gow1/logs/jit-hybrid-20261028-144139/`.

After recording 109 VU1 images and eight IOP modules, the same Release executable was measured with lean/full
call dispatch (`GOW_DISPATCH_FULL=0/1`). Settings: Intel UHD 620, fixed 1x internal scale, 1280x720 hidden window,
16:9, FXAA off, audio off, hardware GS worker, async FINISH, VU1 recording/background compilation off, frames-only
diagnostics, a GS screenshot at 80 s and the profile's pad script. Each run used a fresh private memory card; order was lean/full,
full/lean, lean/full. All six 120 s runs reached gameplay and exited 0. Eleven five-second windows per run start
after the 60 s warm-up. No compiler build ran during these measurements; the existing power plan was unchanged.

| Round | Lean mean guest FPS | Full mean guest FPS |
|---|---:|---:|
| 1 | 42.64 | 42.19 |
| 2 | 44.23 | 42.53 |
| 3 | 41.84 | 40.05 |
| Mean of runs | **42.90** | **41.59** |

The observed difference is +3.2%, with overlapping ranges and visible run-to-run variation. This is a narrow
same-binary comparison of call routing, **not main versus this branch**, not a statistically established general
speedup, and not a per-frame p95/p99 measurement. Real-time scripted input does not guarantee identical guest frames
at capture times, so screenshot equality is not asserted. Prepared native coverage shows zero misses/lane failures;
the inspected lean and full captures show the ship, characters, textures and HUD. Later levels, heavy combat outside
this scene, audio, AMD/NVIDIA and an actual main-branch build still require separate coverage.

Evidence: `data/gow1/logs/perf-20261028-145147/{summary,statistics}.json` and the six run folders. The report records
the runner SHA-256, settings, CPU, memory and power-plan identity; raw logs retain the graphics-driver information.

Standalone follow-up: a 100 s no-argument launch with diagnostics supplied only by the boot file reaches gameplay,
reports guest frames, verifies 2,000 VU1 runs with zero mismatches and exits 0. The test restores the original boot
file and uses a private card. This functional test ran while Qt was building; no performance result is inferred.
Evidence: `data/gow1/logs/standalone-20261028-150433/summary.json`.

Final delivery: `launcher,package,installer` exits 0. The updated launcher capture has no fixed installation-time
estimate and starts with only Windows system directories on `PATH` (exit 0, empty stderr). The generated setup's
1,456 files / six LZMS blocks / 96,256,472 unpacked bytes independently decompress and match the staging directory.
Setup SHA-256: `9e6acf2bb8328b1f928171c3b0c7e95718e5729aba578dc47ceddfa0f4d32cfe`.
Evidence: `data/gow1/logs/foundation-delivery.log`, `launcher-clang-install-final.png` and
`python -I tools/test/verify_setup.py data/_package/gow-native-pc-setup.exe data/_package/gow-native-pc`.
This verifies the payload, not Windows registration or uninstallation. This final verification record postdates
the documentation snapshot embedded in that package.

Implementation and remaining acceptance gates: [build foundation](research/build-foundation-2026-10-28.md).

## Gameplay measurements

Frame rates of the game itself (the in-game counter, `TOBIICHI_FPS_GOSTER=1` / launcher "FPS counter"), on the
Aegean Sea ship (first level, rain, several enemies) unless noted. The game never exceeds 60: its logic follows the
PS2's 60 Hz VBlank. **These are references, not guarantees**: drivers, power plans, background programs and other
areas of the game change the numbers. Add your own results with a pull request (same columns).

## Measured in this project

### Call-path review (2026-10-28, no gameplay measurement)

Intel Core i5-8265U, 24 GB RAM, Windows, llvm-mingw clang 23.1.4 Release, LTCG off. Patches 01–29 apply cleanly.
New regressions reproduce late diagnostic-setting and worker-trace-window failures; follow-up 29a fixes both.
Final call suite: ten isolated scenarios, 162 C++ checks plus trace-window assertion, all passing. Isolated upstream
CodeGenerator suite: 68/68 after 29b updates two stale DMA/timer expectations. Pipeline verifies the complete patch chain.
The full upstream test executable still cannot build because its memory tests reference removed APIs. No ISO/prepared
disc was available, so gameplay, frame hashes and FPS gains are unverified. See [review](research/patches-28-29-review.md)
for reproduction, local evidence and acceptance work before patch 30.

### Earlier gameplay measurements

**Machine A** — Intel Xeon E5-2666 v3 (10 cores / 20 threads, 2.9-3.5 GHz, Haswell), 16 GB RAM, AMD Radeon RX 580
2048SP (driver 26.1.1, OpenGL), Windows 10 Pro 22H2 (19045), power plan "Maximum Performance", 1280×720 window,
internal resolution 2× (dynamic), hardware renderer on.

| Code combination | Result | Notes |
|---|---|---|
| Waffle565 runtime, `runtime` + `switch` branches (2026-10-18) | **unplayable** | Title, menus and 3D black: textures sample black on this AMD OpenGL driver (`GOW_GPU_BISECT`: draws happen, "no texture" phase grey). Logic ran at 60 presents/s. |
| Tobiichi runtime (2026-10-16), Release without LTCG | 34 fps (1×, combat) – 42-45 fps (2×) | Image correct. CPU-bound (1× was not faster). |
| + IOP and VU1 native code (optimize stage, 856 micro-memories) | 42-45 fps | |
| + Waffle CPU speed-ups (`engine/patches/04`) | **59-60 fps**, window 120 Hz | EE thread ~3.1 s and VU1 ~3.5 s busy per 5 s: ~30 % headroom; scenes with more enemies dip (below). |
| same, scripted ship combat (3-4 enemies on screen, `optimize` pad script, t=75-125 s) | 44-50 fps | VU1 worker 3.8 s busy per 5 s: the limit. 28 VU1 block entries had no native code (`vu1n_heads.txt` not passed to the generator), ~1.2 M interpreter fallbacks per 5 s. |
| + `engine/patches/05`-`07` and the VU1 heads in the pipeline (2026-10-24) | **55-60 fps** in the same combat | Current configuration. 0 VU1 fallbacks; image checked against the previous build. |
| + `engine/patches/08` with `-Codegen locals` (now the pipeline's default, 2026-10-25) | 55-60 fps in the same combat | EE thread 3.0-3.4 -> 2.3-2.6 s busy per 5 s (about -22 %); the VU1 worker stays the limit, so the frame rate is the same here; more headroom on slower CPUs. Scripted run only (ship): boot, gameplay, image as before. |
| Launcher defaults (full screen 1920x1080, 16:9, FXAA, 2x dynamic, sound, continuous VU1 capture), 01-08 + locals | 44-52 fps in combat (average 47.6) | The continuous capture cost ~15 % of the VU1 worker (the frame's critical path: VU1 job ~13 ms + ~3 ms of EE work in series per frame). |
| + `engine/patches/09` (2026-10-25) | **53-60 fps** in combat (average 57.6) | 4:3 instead of 16:9: +1 fps; capture off: no difference. No launcher default needs changing. |
| + `engine/patches/10`-`11` (2026-10-25) | **56-60 fps** in combat (average 58.8, minimum 56.0, against 56.5 / 51.4 measured the same day without them) | VU1 worker 3.58 -> 3.46 s busy per 5 s; sound mixing ~14 % -> ~4 % of the game thread. Verified: GOW_VU1N_VERIFY 20,000 runs 0 mismatches, 11.8 M clean-operand checks 0 failures, GOW_SND_VERIFY 5.9 M frames identical. The frame's critical path is now the VU1 worker (job ~13 ms + ~3 ms of EE work in series). |
| + `engine/patches/12`, built with llvm-mingw 20261020 (clang, static, 2026-10-25) | 50-60 fps in combat (average 55.6) | Without patch 12 the clang build ran at ~2 fps in 3D (GS states never compared equal). EE thread faster than MSVC, VU1 worker slower. Full build ~15 min instead of 45-60. |
| same + PGO (profile from the scripted ship run) | **58-60 fps** in combat (average 59.4, minimum 57.9, against MSVC 58.0 / 53.1 the same day) | EE thread -27 %, GS -21 %, VU1 worker +8 % against MSVC. The profile comes from the same scene it was measured on; other areas not measured yet. |
| + Waffle GS draw-batching commits (00bda7f 09ea6cb 91ac954 c558c21) | game 62 fps, **window 0.2-2 Hz** | The GPU queue saturated on the RX 580 (SwapBuffers blocking); left out of patch 04. |
| Release **with** LTCG (`/GL /LTCG`) | link > 2.5 h, cancelled | MSVC 14.44; the pipeline builds without LTCG by default. |

Discs on machine A with the current configuration (clean build of this repository with `build.cmd`, 2026-10-24):

| Disc (`data/gow1/discs/`) | Result |
|---|---|
| USA + a PT-BR fan translation (full) | Portuguese menus and texts, 58-60 fps, window 120 Hz |
| PT-BR fan translation ISO only (standalone) | Portuguese title menu, gameplay reached, image correct |

Other findings on machine A: fullscreen start crashed (0xC0000005) until `engine/patches/03`; without `IOP_MOD/` the
game waited on the legal screen forever (handled by `tools/disc/prepare.py`).

## Local Windows JIT validation (2026-10-26)

Branch `prototipo-claude`, commit `30b007f` (same commit as `origin/claude/keen-dirac-42wd1y`), runtime patches 01-18.
Built on machine A with llvm-mingw clang 23.1.4, Release, existing PGO profile, LTCG off, and 9,501 captured VU1 images.
Executable: `C:\gow-build-44a8e3b6-clang\ps2xRuntime\ps2EntryRunner.exe`.

- Full game build and the three documented JIT test targets completed successfully on Windows.
- `gow_vu1_jit_aot_test - 2000` and `gow_vu1_jit_test x64 2000`: both exited 0; 4,000 cases, 22,000 native blocks,
  identical digest `7c9d4a139489ff09`. Both had the same 284 known edge-input differences from the exact engine.
- Transform microbenchmark: exact engine 18.448 us, JIT 1.838 us per run (10.0x); AOT 1.135 us in its separate run.
  These are synthetic timings, not a game frame-rate improvement.
- Fuzz: seeds 1-6, 4 images x 6 trials each, `x64` versus `x64-calls`: all exited 0 with matching digest and compiled
  block count per seed (242-262 compiled blocks). Inline compile time averaged 13.7-15.0 us per block.
- Game smoke test: 100 seconds, prepared USA disc, hardware renderer, hidden 1280x720 window, audio off,
  `GOW_VU1N_X64=1`, `GOW_VU1N_VERIFY=2000`, fast boot and scripted Start/X input. Gameplay reached
  (`state=11 levelReady=1`); 2,000 native checks, 0 mismatches; gameplay diagnostics showed `missBlocks=0` and
  `laneFails=0`. Host presentation rate at t=50-95 s was 59.72-59.92 Hz. The 80-second capture showed the ship,
  Kratos, enemies, textures and HUD. The process ended after WM_CLOSE without forced termination; the PowerShell
  process wrapper did not report an exit code, so no exit-code assertion is made for this run.
- **Coverage limit:** `[vu1x] compiled=0` throughout the game smoke test: existing AOT captures covered the scene.
  Actual JIT execution was validated by the synthetic tests; newly encountered game areas beyond the ship remain
  untested. This does not establish correctness or performance throughout the game.

Local evidence (generated, not committed): `data/gow1/logs/jit-smoke-20261026-164716/`, `jit-aot-test.log`,
`jit-x64-test.log`, `jit-fuzz-<seed>-<mode>.log`, `jit-test-build.log` and `build.log` in `data/gow1/logs/`.

## Incremental build and JIT delivery (2026-10-26)

Machine A, runtime patches 01-23, clang Release with existing PGO and LTCG off; rebuilt game and Qt 6.8.3 launcher.
v2.0.0 is already an ancestor of the working branch. Full details and reproduction commands:
[JIT delivery report](research/jit-delivery-2026-10-26.md).

- Disc scan: 956 files, 6 usable images, 470 blocks; 112.088 s cold, 0.420 s cached. This is partial disc coverage.
- Native analysis: 9,480 images; 143.103 s cold, 15.154 s cached, six generated C++ files and timestamps unchanged.
- Final x64/AOT digest and six inline/helper fuzz seeds matched. The 284 documented synthetic edge-input differences
  from the exact engine remain; the new patches do not change arithmetic.
- Two 100 s real-game checks (JIT-only and normal hybrid): gameplay reached, 2,000 comparisons with zero mismatches,
  exit code 0, no forced termination. JIT-only compiled 619 blocks with zero unsupported, 16.4 us average compilation.
  Guest FPS at t=40-95 s: JIT-only 15.40-33.35, median 28.40; hybrid 32.95-59.58, median 56.55. Different simulation
  progress prevents a controlled same-frame comparison. The host's ~120 Hz is not the game frame rate.
- The ship capture showed characters, textures and HUD. Later levels and NVIDIA were not tested in this delivery.
- Final setup: 61,673,468 bytes; all 1,417 files matched staging after independent LZMS decompression (8 blocks,
  128,323,300 unpacked bytes). Setup preview exited 0 with empty stderr; launcher binaries in development and staging
  have identical SHA-256. This validates packaging/startup, not Windows install/uninstall registration end to end.
  Installer SHA-256: `95f951e5bb25ecda4db3551d33807e495f017435be3ff9d39a38a4602fdb3632`.
  This artifact checksum was recorded after packaging; the copy of this document inside that artifact predates it.

## Audio/direct-launch follow-up (2026-10-26)

Same local RX 580 machine and clang build, 2x OpenGL. Patch 24's deterministic multi-voice mixer regression fails
before the correction and passes in batch/per-frame/verification modes afterward. Original and PT-BR translated
disc runs, 100 seconds each with audio, reach opening combat and verify 2,000 VU1 runs with zero mismatches.
Both exit normally; after startup, 17 five-second windows each have zero missing/dropped output samples.
The hatch and sailor scene have not been reproduced; this is not an all-audio-bugs-fixed claim.
See [audio investigation and compatibility plan](research/audio-standalone-mods-2026-10-26.md).

## Reported by the projects this builds on (not re-tested here)

| Machine | Code | Reported result | Source |
|---|---|---|---|
| NVIDIA RTX 4050 Laptop (Linux) | Tobiichi | 2× 60 fps (GPU 49 %), 3× 47-57 fps, 1× 60 fps (ship deck) | Tobiichi-Port docs/ESTADO.md |
| AMD Radeon 680M (integrated, Linux, Mesa) | Tobiichi | 1×-2×; ship combat at 1×: 50-60 fps with the performance power profile, lower on battery | Tobiichi-Port README |
| AMD Radeon RX 5700 XT | Tobiichi (GPU renderer) | OpenGL 4.6 renderer verified (no frame rate given) | Tobiichi-Port docs/ESTADO.md |
| Dedicated NVIDIA/AMD (general) | Tobiichi | 2×-3× at 60 fps "typical" | Tobiichi-Port README |
| Waffle565's PC | Waffle runtime + switch | zones 0-4 at 60 fps | God-Of-War-Native-Port docs/status.md |
| Nintendo Switch (Cortex-A57) | Waffle `switch` branch | title menu 25 fps, gameplay 9-12 fps | God-Of-War-Native-Port docs/status.md |
| Ship, KIexster's stack | KIexster | median ~53-56 game frames/s with the camera still (in progress) | god-of-war-recomp README |

## What usually limits the frame rate

- **CPU (most machines)**: the game thread (EE) and the vector unit (VU1) — single-thread speed matters most. The
  optimize stage and "Speed up visited areas" turn recorded VU1/IOP code native; areas never visited still run the
  VU1 interpreter (slower) until their code is recorded and compiled.
- **GPU**: internal resolution (each step costs its square); dynamic resolution lowers it when the GPU falls behind.
- **Power plan / laptops**: "power saver" or battery lowers the CPU clock and the frame rate.

### Follow-up artifact validation

The updated setup is 61,683,346 bytes, SHA-256
`7300d6ffd55c5bfbd8275839c6025ceae63b765980d23eae46b234d9bbcd69f1`.
Independent decompression verified all 1,421 staged files, 8 LZMS blocks, 128,355,429 unpacked bytes.
No installation/uninstallation registration test was performed on the player's existing install.
Standalone no-argument boot reached gameplay in a 100-second test with 2,000 VU1 checks / zero mismatches and exit 0.
The 300-second empty load screen had zero missing/dropped samples after startup, 54.17-58.99 guest FPS after 20 s;
this does not validate a populated save list. The final artifact checksum and standalone result were recorded after
packaging; the embedded documentation predates those final result lines.

## Cutscene audio investigation (2026-10-26, RX 580)

Same installed clang runner and private card copies, 180 seconds per disc, new game then ATHN01D warp. A01MP02
plays in both runs, graceful exit 0, no guest branch errors. PT-BR reproduces periodic PCM channel-block corruption
before output resampling; original control matches the identical source audio at gain 0.999764 and residual RMS
1.17 (source second 4). PT-BR residual is 2244.99, with 16,813 of 46,822 distinct-channel samples matching the wrong
channel. No runtime fix is claimed. The player's card remains byte-identical to its backup.
See [reproduction evidence and correction plan](research/cutscene-audio-2026-10-26.md).
