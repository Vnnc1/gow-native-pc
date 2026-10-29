# Guide for AI maintainers

This repository is maintained mainly by AI agents. Read this first; keep it current when you change the architecture.

## What the system is

A PS2 game (God of War, `games/gow1`) is statically recompiled to C++ by **PS2Recomp** and run on a native runtime.
The runtime is **not in this repository**: `engine/runtime.toml` pins a repository + commit (Tobiichi-Port, which
bundles PS2Recomp with Waffle565's and KIexster's work); stage `fetch` clones it into `engine/runtime/` and applies
`engine/patches/*.patch` in name order. Everything this repository adds is around it: profiles, disc tools, pipeline,
launcher, docs.

```
games/<id>/game.toml        THE source of game-specific values (ELF name, CRC, .text SHA-1, runtime paths, disc layout,
                            editions incl. translations, optimize script, language hints). Never hard-code these.
tools/pipeline/profile.py   loads profiles (Python dict / JSON for PowerShell and the launcher)
tools/pipeline/build.ps1    entry point, parameters, checkout lock, stage selection and timing output
tools/pipeline/modules/    common/tools/context/toolchain/process, runtime/game/optimize/verify/distribution/qt
tools/pipeline/toolchains.json single pinned portable-tools + Qt source manifest (also read by the launcher)
tools/pipeline/compat/     tested Qt source compatibility adapter; modules/qt.ps1 applies it before building the SDK
tools/pipeline/recompile.py content-addressed EE generation, transactional publication, ownership-aware sync
tools/disc/discfs.py        ISO / extracted folder / TOC / ELF helpers (format notes in its docstring)
tools/disc/identify.py      ISO -> {game, edition, language, compatible, problems} (JSON)
tools/disc/prepare.py       ISOs -> data/<id>/discs/*, languages.json, shared mc0 (see its docstring)
tools/disc/iso_extract.py   ISO9660 extractor (Waffle565), writes .disc_layout/.disc_meta
tools/disc/vu1_from_disc.py VU1 microcode (VIF MPG uploads) of the ELF and every TOC file -> micro-memory images for the
                            native VU1 build (stage vu1disc, experimental); vu1_from_disc_test.py = synthetic test
engine/runtime.toml         runtime repository + commit
engine/patches/NN-*.patch   changes to the runtime; header lines = what and why (git apply ignores them)
launcher/                   Qt 6 launcher (from the Tobiichi Launcher). src/lanzador.* = play side (Tobiichi's, Spanish
                            names), src/installer_backend.* = install side (ours, English), qml/InstallPage.qml = tab.
                            Own look (not Tobiichi's): qml/Main.qml = sidebar (NavItem) + pages, `pagina` 0 Home,
                            1 Install, 2-6 settings, 7 Saves; colours in qml/Tema.qml (oro* hold the crimson accent);
                            qml/LoadingScreen.qml = the screen over the whole launcher during long pipeline runs
                            (one overall bar planned from installer.stages and the "=== <step> ===" texts of
                            build.ps1, time left, tips cargaDica1..N, the player's own pictures in data/<id>/loading);
                            screenshots: TOBIICHI_CAPTURA=<png> TOBIICHI_CAPTURA_PESTANA=<page>. icon.ico from
                            tools/make_icon.ps1 (also the installer's)
installer/setup.cpp         release setup, Win32 + GDI+ (no Qt: one self-contained exe). Same exe packs (--pack <dir>
                            <out>, LZMS blocks appended + footer), installs per user (HKCU Apps entry, shortcuts,
                            uninstall.exe + uninstall.lst) and uninstalls. Tests without clicks: /S [/D=<dir>];
                            uninstall.exe /uninstall-from <dir> /S [/purge] (purge removes the copy's build folder
                            only when its CMakeCache points into <dir>); GOW_SETUP_CAPTURE=<png> screenshot
data/                       generated, git-ignored: discs, languages.json, mc0, recomp output, vu1_capture,
                            iop_modules, logs, _tools/qt
```

Build folder: `C:\gow-build` (Release) / `C:\gow-build-dev` (RelWithDebInfo). It must stay short: the runtime's CMake
dependencies (git checkouts) exceed MAX_PATH under long paths. One folder per copy of this repository (CMake refuses a
cache made from another source folder): build.ps1 takes `C:\gow-build-<hash>` when `C:\gow-build` belongs to another
copy, and records the choice in `data\build-root.txt`, which the launcher (runner path) and the uninstaller read.
The launcher also checks CMakeCache's source root before accepting a runner, so a fresh copy cannot use another copy's build.

## Performance target for public builds

Target stable 60 guest frames/s on modest and powerful supported PCs. The i5-8265U laptop and Xeon/RX 580 desktop
are separate validation targets; compare revisions on the same hardware/settings and never transfer their FPS or
build-time results between machines. Measure frame pacing and first-visit stalls, and require visible gameplay
with sound before claiming a tier ready. Preserve portable CPU fallbacks and account for build RAM/disk pressure.
The laptop has not yet met the 60 fps target. Follow the hardware-tier acceptance gates in
`docs/research/roadmap-2026-10-27.md`; do not promise universal performance or classify an untested tier as supported.

## Player diagnostic reports

`launcher/src/session_diagnostics.*` implements the independent `gow-session` collector and local report export.
It must keep collecting when the launcher closes, preserve actual child exit codes, and stop only its own child.
Reports use bounded files under launcher app data (`registros/sessions`), distinct from pipeline logs. Export only
the explicit allowlist; never add ISOs, saves, full environment dumps or automatic uploads. Keep redaction and
truncation indicators. Basic mode uses frames-only accounting; expensive per-call timing stays opt-in.
Patch 29c supplies bounded guest-frame interval distributions with a profile-supplied frame PC. These are not
GPU/presentation latency. Run `tools/test/session_diagnostics.py` against the deployed helper after collector changes;
`verify` includes frame-metric tests. Instructions and metric semantics: `docs/reporting-bugs.md`.

## Contracts (do not break)

- **Pipeline output protocol** (parsed by `installer_backend.cpp`): `=== <step> ===`, `@@progress <done> <all>`,
  `@@status <text>`, anything else is log. Errors: a final `ERROR: <message>` line and exit code 1.
- **languages.json** (`data/<id>/`): `{game, title, recompile_elf, languages: [{language, label, edition, quality,
  elf}]}`; quality = original | full | standalone. The launcher plays `elf` of the chosen language.
- **Runtime env vars the launcher sets** (see `lanzador.cpp`): TOBIICHI_* (window, keys, cheats), PS2X_GS_* (renderer),
  GOW_VU1_CAPTURA (continuous VU1 recording into data/<id>/vu1_capture), GOW_ANISO (anisotropic filtering, 2..16).
  GOW_VU1N_X64=1 (in-process x86-64 VU1 JIT, engine/patches/18, experimental: the Performance tab's "Compile new areas
  while playing"; docs/research/vu1-x64-jit.md). GOW_VU1N_JIT + GOW_VU1N_JIT_CXX/_PY/_GEN/_FLAGS (patch 17's background
  clang compiler, by hand: data/<id>/vu1_jit.json, which clang builds write, names the values).
  GOW_VU1_CAPTURE_MISSES=1 (patch 19): capture a context image only for a missing dispatched block, before JIT compilation;
  each image is a full 16 KB micro-memory, written once per distinct image as miss_<image hash>.bin (patch 26; before it,
  block_<key>.bin per missing block), and indirect heads are recorded even when JIT succeeds. Launcher uses it.
  GOW_PERF_FRAME_PC (the profile's [diagnostics].frame_pc, read by InstallerBackend::diagnosticsFramePc) is set with the
  Performance tab's diagnostics toggle, next to GOW_AUDIO_STATS / GOW_IOP_DRIFT / GOW_VU1N_DIAG / GOW_PERF_DIAG.
  GOW_MC0 (the memory card image: Mcd001.ps2 next to the ELF unless already set) and GOW_SAVES_DIR (data/<id>/saves):
  F1 > Saves in game copies the card to GOW_SAVES_DIR/<yyyyMMdd-HHmmss>/{Mcd001.ps2, save.json} (patch 26); the Saves
  tab (PaginaPartidas.qml, Lanzador::partidas/guardarPartida/importarPartida/restaurarPartida/borrarPartida) lists,
  makes, imports, deletes and restores copies. save.json: {label, time, source: F1|launcher|import|backup, card, bytes}.
  A restore needs the game closed and first keeps the current card as a "backup" copy. There are no savestates: a copy
  holds the game's own last save (save altars), see docs/saves.md.
  GOW_VU1X_INLINE=0 selects the helper tier; GOW_VU1X_ONLY=1 is test-only (clears AOT registrations, requires JIT on).
  Patch 27 A/B switches (not set by the launcher): GOW_VU1X_AVX=0 (SSE4.1 encodings), GOW_VU1X_SPECULATE=0 (no entry-lane
  speculation), GOW_VU1X_DUMP=<dir> (block code). Any vu1n_gen.py semantic change must be mirrored in ps2_vu1_x64.inl;
  tools/test/vu1-equiv.sh proves both give the same digests, tools/test/vu1-ir-measure.sh compares their speed.
  Patch 28: static JAL calls use PS2Runtime::callGuestFunction (no per-call trace ring / dispatch history / perf hook).
  GOW_DISPATCH_FULL=1 (runtime, not set by the launcher) sends every call through dispatchGuestBranch again, e.g. to get
  JAL entries in the branch ring and the missing-function "trace=" history; PS2X_STATIC_CALLS=dispatch (ps2_recomp's
  environment) generates the old dispatchGuestBranch call for JAL and (patch 29) JALR. Generated code must be regenerated (recomp stage) after it.
  Patch 29a snapshots call diagnostics per runtime after gow-native.boot restores the environment; do not move these
  settings to pre-main static initialization. Worker trace time starts on the first dispatched call, not the first watched one.
  The pipeline's own runs (optimize, pgo) add GOW_WINDOW_HIDDEN=1 (engine/patches/15) and close the game with WM_CLOSE to
  its GLFW window (Close-GameWindow in build.ps1; Process.CloseMainWindow does not see hidden windows).
- **Configure skip** (build.ps1 `Configure -MaySkip`, used by native / pgo): skipped when the cmake arguments and the
  existence of vu1n_heads.txt match `<build>\gow-configure.sig`; Ninja re-runs CMake itself for CMakeLists and
  CONFIGURE_DEPENDS globs. Anything new read only at configure time must go into that signature.
- **Step texts** of build.ps1 (`=== record: ...`, `=== build the game ...`, ...) are matched by prefix in
  LoadingScreen.qml (pasoDe) and InstallPage.qml (stepLabel): change both when renaming a step.
- The runtime registers the game's overrides for the ELF **file name** (`SCUS_973.99`) in the ELF's folder, and uses
  that folder as the CD root: every prepared disc folder keeps the original ELF name; `mc0` is a junction to
  `data/<id>/mc0`. The memory card the IOP really uses is the PCSX2-format image `Mcd001.ps2` in that folder (or
  `GOW_MC0`), so each prepared disc folder has its own card file.

## Language conventions

- Code comments, docs, commit messages, patch headers and lines added by patches: **English**. User-facing docs may
  have translations next to them (`README.pt-BR.md`, linked from the language bar at the top of `README.md`).
- Launcher interface texts: `launcher/qml/Textos.js` (tr, en, es, pt).
- Identifiers inherited from the Tobiichi Launcher stay Spanish (`lanzador`, `ajustes`, `Pagina*`...) to keep its code
  diffable with upstream; their comments are English. New code uses English names.
- The downloaded runtime keeps its authors' comments (some Spanish). Patch context lines are upstream code: never
  edit them, or the patch stops applying.

## How to change things

- **Runtime code**: edit in `engine/runtime/`, then turn the change into a new `engine/patches/NN-name.patch` (git diff
  in engine/runtime, with a header saying what/why/measured result). Patches apply in order; a later patch may depend
  on an earlier one. Keep each patch to one concern.
- **New game**: see `docs/adding-a-game.md`.
- **New translation / edition**: add an `[[editions]]` entry (elf_crc from `identify.py`); if it changes code (.text
  differs) it is not supported.
- **Launcher texts**: `launcher/qml/Textos.js`, keys with tr/en/es/pt (missing languages fall back to en).

## How to test

1. `python -I tools/disc/identify.py <iso>` — identification.
2. `python -I tools/disc/prepare.py --game gow1 --data <tmp> <iso> [<iso>]` — disc preparation (use a scratch data dir).
3. `build.cmd -Stages build` after runtime edits; `-Stages configure,build` when VU1 microcode changed.
4. Runtime smoke test without a person: env `GOW_PAD_TEST=1 GOW_FAST_BOOT=1 GOW_SKIP_FMV=1 GOW_PAD_GUION=
   "5:start,12:x,18:x,24:x,30:x,36:x,42:x,48:x" GOW_PAD_CAPTURAS="10,80"` writes `gow_pad_test_N.ppm` (the GS output)
   in the working directory; stderr `[gow-pad2:test] state=11 levelReady=1` = gameplay reached. Frame rate:
   `GOW_PERF_DIAG=1` prints `[gow-perf]` per 5 s (ee/vu/gs/iop/guest_wait ms, guest_flip_hz, host_hz);
   use `GOW_PERF_DIAG=frames` for FPS comparisons without per-section timing overhead. Guest FPS requires the profile's
   `diagnostics.frame_pc` in `GOW_PERF_FRAME_PC`; `host_hz` counts presentation, not gameplay. `TOBIICHI_FPS_GOSTER=1` draws
   the counter in the window.
5. Record results in `docs/tested-hardware.md`.
   `tools/test/jit-smoke.ps1 -Mode hybrid|jit|calls` runs a scripted local test and writes logs, captures and summary.json.
   The game's guest-frame probe comes from `[diagnostics].frame_pc` in its profile.
   `tools/disc/vu1_analysis_cache_test.py --gen <generator> <procedural.bin>` checks cache/reference equality and invalidation.
   `tools/test/verify_setup.py <setup.exe> <staging dir>` checks every packaged byte without installing into Windows.
   `tools/test/guest-calls.py <gow_guest_calls.exe> <output>` validates JAL/JALR parity, diagnostics and classic/locals
   codegen without a disc. Build with `tools/test/guest-calls.cmake`; see `docs/research/patches-28-29-review.md`.
6. Profiling: `build.cmd -Stages configure,build -Pdb` (Release with ps2EntryRunner.pdb, same code), then
   `tools/profile/sampler.cpp` (build line in its header) `sampler.exe ps2EntryRunner.exe <seconds> <delay>` prints the
   hottest functions per thread (GameThread = EE, the VIF1/VU1 worker, GSThread). `GOW_VU1N_DIAG=1` prints native VU1
   counters every 5 s; `missBlocks` > 0 means block entries without native code (see vu1n_heads below).

## Build foundation contracts

- New builds use pinned llvm-mingw only. `-Toolchain msvc` is a migration alias, not another compiler path.
  Never link MSVC/GCC-built Qt libraries into the llvm-mingw launcher. `modules/qt.ps1` builds a compatible Qt once.
- Preserve the classic codegen, full dispatch and interpreter/slow-path references for differential testing.
- `recompile.py` owns `data/<id>/recomp/out` and records hashes/ownership. A failed generation must not destroy the
  last output; unchanged files keep timestamps; synchronization must not delete unrelated or edited files.
- Pipeline holds `data/pipeline.lock`; do not run concurrent writers in one checkout. Metrics are local JSON logs.
- Run `python -I tools/test/pipeline_tests.py` for pipeline changes, `build.cmd -Stages verify` for runtime/codegen
  changes. The latter requires downloaded runtime but no ISO; it does not establish frame equivalence or FPS.
- `verify` includes the isolated `gow_memory_tests` suite (patches 29d–29f). Native DMA completes at submission and
  reports through the completion queue; do not restore the removed DMAC pump/D_STAT model to satisfy old tests.
  Texture tests use the production texture store and inspect primitive submissions without a GL context; they do
  not validate GPU rasterization. `tools/test/session-game-smoke.py --visible` adds the separate gameplay check;
  `--detailed` enables intrusive timing and must not be used as an FPS benchmark.
- PGO generation disables object caching. Profile-use compile commands include the profile content hash so replacing
  `gow.profdata` at the same path cannot silently reuse objects trained with the old profile.
- Runtime patch ordering is ordinal, not culture-dependent `Sort-Object`: Windows PowerShell 5.1 otherwise puts
  `29a` before `29-...`. Preserve the shared `Get-RuntimePatches` helper for both application and provenance logs.
- `-Pdb` adds Clang CodeView and lld PDB flags; the upstream PDB option alone is MSVC-only. Keep symbols per executable.

## Known pitfalls

- PowerShell 5.1: native stderr under `$ErrorActionPreference='Stop'` throws — use the `Native` helper in build.ps1;
  never shadow `$global:LASTEXITCODE` with a local variable in that helper (it hides failed external commands).
  `-bxor` is signed; `Set-Content -Encoding UTF8` writes a BOM.
- ThinLTO remains opt-in (`-Ltcg`) until measured link time, RAM and gameplay justify it. Historical MSVC LTCG took hours.
- Patches 30-35 add memory fast paths, explicit Clang ThinLTO, math flags, large-VIF1 submission throttling and VU1
  self-loop optimizations. `-CpuTarget portable` (default) selects x86-64-v2; `-CpuTarget x86-64-v3` selects the AVX2
  tier explicitly. Do not restore an unconditional `-march=native` that overrides this choice. Neither tier is a new
  performance-support claim. The profile's `build.unity_batch` applies only with at least 14 GiB RAM.
- `GOW_VU1_EARLY_FINISH=0` disables the large-VIF1 barrier; otherwise it defaults to `GOW_GS_FINISH_ASINCRONO`.
  The setting is per memory instance. The 64 KiB threshold identifies packets, not exact guest frames. Preserve
  worker/stage-thread self-wait guards and DMA submission/completion semantics.
- VU1 `chainSelf` completes exit accounting even when it returns false: generated blocks must return `kVu1nDone`
  without calling `chain` again. Keep the x64 direct self-body jump and AOT/DLL behavior equivalent. Run
  `tools/test/vu1-equivalence.py` for random programs and deterministic budget/depth self-loop exits (no game data).
- AMD Windows OpenGL: GS draw-batching changes from Waffle's 2026-10-17/18 commits saturated the GPU; the newer Waffle
  renderer sampled textures black. Test renderer changes on AMD and NVIDIA.
- Windows `mklink /J` needs backslash paths.
- Native VU1 block entries the generator cannot find statically (jumps through a register) must be listed in
  `data/<id>/vu1n_heads.txt` (the runtime's CMake reads `<capture dir>/../vu1n_heads.txt`). The configure stage writes it
  from the profile's `runtime.vu1_native_heads` plus `vu1_capture/vu1n_heads_seen.txt` (recorded by the runtime while
  playing with the capture on). Without it, combat runs those blocks in the interpreter (44-50 instead of 55-60 fps).
- VU1 native code has three producers that must stay equivalent: tools/vu1/vu1n_gen.py (the build), its --dll mode (patch
  17) and the x86-64 JIT's translator (patch 18, a port of gen_block). Change vu1n_gen.py's semantics -> port it to
  ps2_vu1_x64.inl in the same change and run tests/vu1_x64_fuzz_test (docs/research/vu1-x64-jit.md, section 6).
- windows.h defines `near` and `far`: not usable as identifiers in runtime code that includes it (the VU1 JIT files).
- Runtime fixes taken from the God of War II port must be checked on God of War: its `SetupThread` argc/argv change
  (5b1a25a) makes this game load its IRX as `cdrom0:\...;1` and hang at boot (left out of patch 05).
- VU1 analysis cache (patch 22) lives in the generated build folder, contains game-derived data, and must never ship.
  Configure skips remote dependency updates on routine rebuilds; include `fetch,configure` when changing dependency
  revisions so CMake may fetch new commits. Initial downloads are still allowed.
  It is invalidated by generator contents, entry heads and image hashes; `--no-cache` is the reference path.
  Patch 21 uses stable block-key shards, so new blocks do not move unrelated functions between translation units.
- Disc scans write `vu1_capture/disc-report.json`; a cache hit requires matching source metadata, implementation/profile
  and output hashes. `--force` rescans when source bytes changed without metadata. Six images/470 blocks were found on
  the local USA disc; this does not establish whole-game coverage. Keep the experimental wording in the launcher.

## Direct launch and diagnostics

The pipeline creates `gow-native.boot` beside the built runner; the launcher atomically refreshes it on play.
It records the selected ELF and runtime-prefixed environment variables only. No-argument runner launches restore it
and write `standalone.log` beside the executable (patch 25). Never package this machine-specific profile.
The Performance diagnostics toggle enables audio buffer/rate, IOP drift, VU1 and performance counters.
`tools/test/sound_regression.cpp` covers positive/negative SPU2 master-volume overflow (patch 24).
See `docs/research/audio-standalone-mods-2026-10-26.md` for unresolved scene, HUD and mod acceptance criteria.
