# Guide for AI maintainers

This repository is maintained mainly by AI agents. Read this first; keep it current when you change the architecture.

## Ponytail workflow

Use the `ponytail` skill in its default `full` mode for coding tasks, as requested by the maintainer.
Source: https://github.com/DietrichGebert/ponytail (skill: `skills/ponytail/SKILL.md`).
If the skill is unavailable, follow these essentials: trace the affected code and callers, reuse existing
helpers, and make the smallest complete change that solves the request. Avoid speculative abstractions
and dependencies. Keep searches and output focused on the affected paths. Preserve all contracts and
required checks below; token savings never justify skipping validation, accessibility or error handling.
Report actual checks and remaining limitations; do not claim token savings without measurements.

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
tools/disc/chd.py           CHDv5 DVD / single MODE1 track -> verified cached ISO; optional tools pinned in
                            toolchains.json[disc_import], locked atomic publication under data/imports/chd
tools/disc/prepare.py       ISOs -> data/<id>/discs/*, languages.json, shared mc0 (see its docstring)
tools/disc/iso_extract.py   ISO9660 extractor (Waffle565), writes .disc_layout/.disc_meta
tools/disc/vu1_from_disc.py VU1 microcode (VIF MPG uploads) of the ELF and every TOC file -> micro-memory images for the
                            native VU1 build (stage vu1disc, experimental); vu1_from_disc_test.py = synthetic test
engine/runtime.toml         runtime repository + commit
engine/patches/NN-*.patch   changes to the runtime; header lines = what and why (git apply ignores them)
launcher/                   Qt 6 launcher (from the Tobiichi Launcher). src/lanzador.* = play side (Tobiichi's, Spanish
                            names), src/installer_backend.* = install side (ours, English), qml/InstallPage.qml = tab.
                            Own look (not Tobiichi's): qml/Main.qml = sidebar (NavItem) + pages, `pagina` 0 Home,
                            1 Install, 2-6 settings, 7 Saves, 8 Accessibility (AccessibilityPage.qml: input assists,
                            texture packs and visual mods); colours in qml/Tema.qml (oro* hold the crimson accent);
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

Normal setup exposes a separate build base (`/BUILDROOT=` in silent mode) and
persists UTF-8 `data/build-root.txt`. Updates retain it unless explicitly changed.
A location change requires rebuilding; never copy CMake/Ninja caches as relocatable
or delete the old build/player data automatically. Collision fallback stays beside
the selected base, with exact source ownership checks. Installer tests use the
compile-only `GOW_SETUP_TEST_IDENTITY` to isolate registration and shortcuts:
`tools/test/setup-build-location.py`; pipeline selection is covered by
`tools/test/build-root-tests.ps1` (also in pipeline-tests.ps1). See
`docs/research/player-integration-2026-11-09.md` for the agreed next features.

## Isolated regional builds

Europe SCES_531.33 and Japan SLPM_670.10 have separate Windows builds validated
through initial ship gameplay. `games/gow1/regions` stores conditional runtime
overlays, baseline source hashes, function ranges and recompiler entry hints.
Never apply these overlays to the USA runtime or put them in the global ordinal
patch chain. The USA compilation pipeline still rejects these different-code ELFs.
Use separate runtime snapshots, build roots, discs, cards and boot profiles.
`tools/pipeline/register_region.py` registers an already validated isolated build
in ignored `data/<game>/regional-builds.json`. The launcher validates ownership,
CMake source and ELF/runner hashes, merges these entries into its edition selector,
and routes gameplay, frame probes and saves per region. Regional JIT-only builds
disable unused AOT capture files. ISO identification
exposes `playable` for matching registered builds without setting USA `compatible`.
Never route these discs to the USA generation stages or auto-native/PGO actions.
Run `tools/test/register-region-tests.py`, the launcher's `gow_region_tests` target,
`tools/test/regional-play-ui.py` and `tools/test/disc-import-ui.py` after routing edits.
See `docs/research/regional-port-2026-11-02.md` for evidence and limitations.

## Experimental Linux integration

Patch `zzz-324` selects MSVC `intrin.h` versus Clang/GCC `x86intrin.h` for GS/VU1 cycle counters.
Keep x86 architecture gates and the non-x86 fallback; verify the native Linux runtime library after header changes.

`bash build.sh` runs `tools/pipeline/linux.py` with Python 3.12+, native Clang,
system/SDK Qt 6.5+ and SDL2. It shares the profile, disc preparation, transactional
recompiler and ordinal runtime patch chain, holds `data/pipeline.lock` with flock,
and builds under `data/build-linux/<game>`. The launcher reads
`data/build-root-linux.txt` and uses case-sensitive CMake source ownership checks.
Windows build roots, portable tools and PGO profiles are not reused. Linux
controller capture uses SDL2; gameplay retains raylib. The renderer and System V
VU1 JIT already have Linux paths in the runtime; do not claim GPU validation from
compiling them. Linux PGO/automated recording, IOP training, portable dependency
packaging and binary updates remain unimplemented. `tools/pipeline/package_linux.py`
creates a host-library launcher/source archive with an OS/dependency manifest and
verified member hashes; never label that archive universally SteamOS-compatible.
The Linux diagnostic collector reads bounded `/proc/<child>/stat` CPU/RSS counters;
RSS is not the Windows private-bytes metric. See `docs/linux.md` for acceptance gates.
Disc normalization preserves original IRX names and creates missing lowercase
aliases in the profile's IOP directory for Linux guest requests. Keep existing
files untouched; `tools/disc/prepare_test.py` covers reruns and case-sensitive names.
Run `tools/test/linux_pipeline_tests.py` plus `tools/test/pipeline_tests.py` for
pipeline changes. `.github/workflows/linux.yml` compiles the launcher and runtime
library without game data; Linux/Steam Deck performance remains unvalidated.

## Performance target for public builds

Before proposing or rerunning performance experiments, read
[`docs/research/performance-experiments.md`](docs/research/performance-experiments.md).
It indexes regressions, neutral/invalid comparisons and gains with missing acceptance
criteria. Reuse those results; do not repeat the same rejected experiment merely because
a new agent/chat starts. A retest must cite the previous experiment ID and document a
materially changed implementation, workload, hardware/toolchain or measurement flaw first.
For partial gains, validate the missing criterion instead of repeating completed checks.
Routine correctness regression tests still apply. Append new results and decisions to
the ledger and `docs/tested-hardware.md`; never erase negative or interrupted evidence.

Performance improvements must be part of the normal first-install build and launch defaults. Do not require
players to toggle diagnostic flags, install external tuning tools or rerun optimization stages to activate a
shipped improvement. Existing compiled installations still need a matching updated runner. RX 580 results are
local evidence only; they do not establish a gain on the i3-10110U/Intel UHD or weaker PCs.

Target stable 60 guest frames/s on modest and powerful supported PCs. The i5-8265U laptop and Xeon/RX 580 desktop
are separate validation targets; compare revisions on the same hardware/settings and never transfer their FPS or
build-time results between machines. Measure frame pacing and first-visit stalls, and require visible gameplay
with sound before claiming a tier ready. Preserve portable CPU fallbacks and account for build RAM/disk pressure.
The laptop has not yet met the 60 fps target. Follow the hardware-tier acceptance gates in
`docs/research/roadmap-2026-10-27.md`; do not promise universal performance or classify an untested tier as supported.

Patch 61 keeps shared presentation acquisition nonblocking when the GS publisher
holds its mutex. The host-thread snapshot owns the existing reading slot; never
recycle it until normal host release, and reset it on host lifecycle changes.
`gow_shared_present_tests` exercises production acquisition with fake fences and
is part of `verify`. This removes one lock wait, not all host/backend/driver waits;
see GPU-02 in the performance ledger before extending its performance claims.

## PR 26 integration (runtime chain 59-94 + zzz-*)

The runtime chain is PR 26's renderer/VU1/mod stack (59-94, `zz-workspace-final-state`) followed by the fix-chore
work rebuilt on top of it: `zzz-001..006` (ring ownership, software reference, frame order, texture budget, shader
lifecycle, mod-table bounds), `zzz-100..103` (audio, movie tail), `zzz-200..205` (finish countdown, dump clock gate,
VU1 scalar outline, queue-wait metrics, frame-aligned tests, experimental logic rate), `zzz-261` (shared present)
and `zzz-300` (review fixes on default paths: segment-fenced vertex ring, Op::Run tail over-read, Op::Vertices
guard that dropped every compact single primitive, BufferStorage only with ARB_buffer_storage below 4.4).
The `zzz-` prefix keeps them after the PR's names; a later renumbering must keep this order. `*.patch -text` in
`.gitattributes` is required: without it a Windows clone checks the patches out with CRLF and stage `fetch` fails at
patch 02. Launcher changes live in `launcher/` sources, never as patch files. Decisions, bugs found, tests and the
laptop A/B plan: [docs/research/pr26-integration.md](docs/research/pr26-integration.md).

## Player diagnostic reports

Patch `zzz-325` requires a verified current `R2ButtonPress` instance for Greek R2 replacement. The symbol's
leaf meshes also appear outside that instance; replacing by leaf identity corrupts the Spartan-style HUD.
Preserve those original draws and the existing readiness/capacity gates. `control-prompts.py` covers the
regression; private slot-3 captures and limits are in `docs/research/spartan-r2-prompt-2026-11-10.md`.

Patch `zzz-326` bounds GS worker frames in flight (`gs_frame_latency.h`, default 2, `GOW_GS_FRAME_LATENCY=0` =
reference): the worker context never swaps, so only the vertex ring limited its lead over the GPU. Its fences
guard no resource. Keep each wait bounded and never fall back to `glFinish`; the ring fences still own vertex
safety. `gow_frame_latency` covers it. It is not validated in game; see GPU-06 in the performance ledger.

Patch `zzz-318` adds the RatOne startup and six-category in-game dock. The profile's
`runtime.branding_image` supplies `GOW_BRAND_IMAGE` at Windows/Linux configure time;
keep the approved PNG byte-identical and embed it, never depend on an artist's local path.
F1/Back+Start opens the dock; F2 opens cheats; Ctrl+F1 remains the debugger.
Live keyboard/controller bindings use immutable shared snapshots; prompts use the same
getters. Capture discards queued navigation and waits for release. Preserve classic
aliases, modifier semantics, and post-close input/ExitKey release gates.
Audio gain/mute applies after diagnostic PCM in the common SPU2 callback (both devices).
Patch `zzz-319` keeps the dock inside the minimum window width and labels unbound
inputs explicitly; retain the 320-pixel layout check in the GPU menu suite.
Mods supply bounded manager-owned `GOW_ACTIVE_MODS`, reserved and cleared on deactivation.
Patches `zzz-320..322` pause EE execution at scheduler boundaries, rebase host deadlines, and freeze audio queue consumption/sample clocks. Host polling and normal shutdown remain active. Settings edits publish bounded atomic per-session transactions under launcher app data; `menu_settings.h` validates and imports only changed fields, including bindings and audio, into the existing QSettings category. Never put the private bridge path in reusable boot files or diagnostic exports. Run `menu-state.py`, `game-menu-smoke.py --pause-trace` and `menu-pause-report.py`, as well as the existing
control-prompts suite and explicit GPU `tools/test/game-menu.py` when changing this UI.
See `docs/research/menu-pause-settings-2026-11-10.md` for acceptance limits, evidence and the still-pending native save-slot work.

Patch `zzz-310` restores USA Flash button prompts with last-active input and the
production keyboard/controller mappings. Input selection is shared by buttons,
sticks and labels; never switch merely because an idle pad is connected.
Publish complete prompt batches at the guest flip, including empty frames.
Patch `zzz-311` suppresses recognized original Flash symbols, learned button
plates and shoulder-label glyphs after host replacements render successfully.
Keep original drawing before readiness, for unknown art and at batch capacity;
clear learned plates when movie discovery resets. Preserve rotation/shake diagrams.
`gow_control_prompts` in verify covers input, labels and bounded publication;
`control-prompts-smoke.py` captures the final host overlay with a private card.
Forced styles require `GOW_PAD_TEST=1` and are not hardware detection evidence.
Patch `zzz-312` replaces the USA `goMiniGameCircle` submissions at `0x158020` /
`0x158B40` only for the verified `0x157A60` callers, stack matrix layout and exact
resource identity. Preserve the original path on invalid data/readiness/capacity;
never alter creature/QTE state to replace the visual. World coordinates must not
receive Flash's additional aspect stretch. `gow_control_prompts` also tests these
production hooks. Physical Sony pads, real combat QTEs and guest-depth occlusion
remain acceptance gaps. See `docs/research/world-control-prompts-2026-11-09.md`
and `docs/research/control-prompts-2026-11-09.md`.

Patch `zzz-313` bakes prompt textures to 48 pixels high and themes Xbox badges.
Xbox world badges project the animated model plane, with readable back faces;
never add a host-clock spin that continues through guest pause. They still lack
shared guest depth. `gow_control_prompts` covers projected corners and stable
samples; `tools/test/control-prompts-render.py` is an explicit hidden GPU artwork
preview, not a combat test or part of data-free verify.

Patch `zzz-314` adds a keyboard-only mapped movement guide beneath Greek stick
QTE diagrams. Preserve original directional animations and the one-guide/frame
and four-slot capacity gates; do not turn a visual hint into automatic input.
Default/custom labels and composite leaves are covered by `gow_control_prompts`.
Aphrodite's reported silence remains unproven despite successful asset/mixer
checks; see `docs/research/aphrodite-and-keyboard-qte-2026-11-09.md`.

Patch `zzz-315` moves task-recording delay/stride/limit checks before the large
interpreter-copy frame, retaining the mutex across selection and publication.
This fixes diagnostic overhead only; the recording-disabled gameplay path is
unchanged. Run `tools/test/vu1-task-tests.py` and captured-task replay after edits.
`tools/profile/sampler.cpp` supports `SAMPLER_CPU_ONLY=1` for thread CPU counters
without suspension; instruction sampling remains intrusive and separate from
FPS measurements. See `docs/research/vu1-waits-2026-11-09.md` (VU-09).

Patch `zzz-316` specializes `chain` for ordinary versus diagnostic execution,
without changing guest timing/flags/history or the AOT/JIT ABI. Keep the detailed
path selected for cost, opcode or native counters. VU-10 records pinned replay
and three visible private-card Athn01D pairs; this is not universal 60 FPS.
`ship_altar_frames` requires an explicit card with that first-slot location;
`gs-run-ab.py --card` must copy/hash it and never launch against the source card.
Run task replay and `vu1-equivalence.py` after chain edits, including self-loop
budget/depth exits and diagnostic modes. See `docs/research/vu1-chain-2026-11-09.md`.

Patch `zzz-317` adds numbered mapped-key sequences for six rotation QTE symbols.
Resolve shared leaves through bounded USA Flash instance ancestry and the final
arrow matrix; CW/CCW names alone do not determine displayed direction. Preserve
caller/stack/vtable/movie gates, complete-guide capacity and original arrow art.
`GOW_QTE_AUTO=1` is default-off automatic pressing of recognized Greek button
prompts only, not world indicators, ordinary tutorials or stick gestures. Keep
empty-frame publication, stale/focus/conflict rejection and scripted-pad exclusion.
`gow_control_prompts` covers production recognition/input; `qte-controls.py` tests
the actual accessibility toggle. See `docs/research/keyboard-qte-sequences-2026-11-09.md`.

Patch `zzz-309` backs up USA altar saves only after `0x22E800` returns to the final
index-write caller `0x2306C0` with success, zero game error and all 68 index bytes
written. Keep entry/resume, caller, primary-slot and size/result gates; do not use
card timestamps, low-level page writes or generic MCSERV RPC as completion signals
(this game uses EE libmc2 over DBCMAN). The earlier payload write is not completion.
`runtime/gow_save_backup.h` is shared with F1 and publishes the final card name only
after closing data and metadata successfully. Host notifications consume an atomic
result; never draw on the EE thread. History uses existing paths and `source: auto`.
Run `altar-save-tests.py` (also in verify), `save-history-ui.py` and the private-card
`altar-save-smoke.py`; regional runners still need separate validated hooks.
See `docs/research/altar-save-backups-2026-11-09.md`.

Collector final metadata uses bounded atomic-write retries after child exit.
`SessionDiagnostics::sessionMetadata` reconciles incomplete active metadata only
with a valid latest-process exit event; never infer completion from silence or a
stale heartbeat. Summary, exit handling, diagnostic UI and export share this
reader. Recovery is flagged `final_metadata_incomplete` and preserves original
files; raw incomplete metadata remains excluded from retention pruning. See
`docs/research/collector-final-state-2026-11-09.md` and `session_diagnostics.py`.

Patch `zzz-307` emits host-owned shared-acquisition counters as `[gow-present]`
under existing performance diagnostics. Publication sequences are not unique
game frames or scanout; hold age is not GPU time or input latency. Preserve
lifecycle resets and hold age across report windows without adding GPU waits.
The RAM path and older runners have no such metric. `tools/test/frame_metrics.cpp`
and the deployed collector's `tools/test/session_diagnostics.py` cover accounting
and export. See `docs/research/issue-31-stutter-2026-11-09.md` for unresolved stutter.

Patch `zzz-308` sets raylib `FLAG_WINDOW_ALWAYS_RUN` at host window creation.
The guest/audio already run independently: without this flag minimization blocks
host polling and a close request cannot reach normal shutdown until restoration.
Preserve this flag across window modes. `tools/test/window-lifecycle.py` is the
Windows desktop/GPU integration gate (visible, minimized-close, restored-close),
using a private disc/card and the deployed collector. This is not an AF/rain FPS fix.

The 2026-11-05 [system audit](docs/research/system-audit-2026-11-05.md) records
confirmed defects, test failures and vendor-tool limitations. Patch 76 validates
GS raster shader links and releases temporary shader objects; `gow_shader_program_tests`
injects creation/compile/link failures in verify. Patch 77 resets audio resampling
phase with its output queue; `gow_sound_regression` checks reset/fresh-stream parity.
Neither patch establishes a gameplay FPS or audio-dropout improvement.
Patch 78 adds bounded `GOW_AUDIO_TRACE=1` events for transition diagnosis. Normal
`main` uses `_Exit`, so flush explicitly after joining the producer and stopping
audio; a destructor alone is insufficient. Dumps must remain outside callbacks.
`session-game-smoke.py --audio-trace` rejects missing end markers or overflow.
Event `t_us` is relative to the begin marker; collector dump time is not event time.
Patch 79 snapshots producer context only at publication under the output mutex;
never read producer-only pending context from the callback. Reason totals count
published audio frames, not call counts or execution time.
Patch 80 extends movie-clock catch-up only to USA `0x189A88` entered from
`0x18979C` in the final display-drain loop. Preserve both entry/caller gates,
the existing one-field cap and original/resume delegation; do not generalize
this to all sound RPC calls or regional overrides. `movie-tail-tests.py` is in verify.

Patch `zzz-305` fixes the USA movie reader's drained-EOF retry loop (issue 30,
`P04MP05`) and keeps movie completion false while decoded pictures remain.
Preserve the entry/caller, cancellation, pending-block, MPEG-format and resume
gates. Signaling EOF alone discards the last picture. `movie-tail-tests.py` covers
both wrappers; `movie-smoke.ps1 -NewGame -RequireCompletion -ExpectedLastPicture 740`
checks this clip through the intro route with a private card. See
`docs/research/issue-30-movie-eof-2026-11-09.md` for evidence and scope.

Patch `zzz-306` keeps VU1 generator images raw and decodes one at a time per pass;
retain pass/input ordering so generated C++ stays byte-identical. Validate input
length before allocation. After generator changes, run
`python -I tools/test/vu1-generator-tests.py --generator <built-generator>`;
use `--reference <baseline-generator>` for output-parity acceptance. Issue 6's
original capture set is unavailable; lower local memory usage is not proof of
closing every allocation failure. See `docs/research/community-issues-2026-11-09.md`.

`launcher/diagnostics` is the private precompiled Windows test frontend. It uses a separate application-data
identity, validates the profile ELF `.text` and packaged runner/helper hashes, copies the adjacent memory card
per session, and invokes the same detached collector. `tools/pipeline/package_diagnostics.py` packages it with
an explicitly supplied runner; `installer` option `GOW_DIAGNOSTIC_SETUP` gives it a separate uninstall key,
folder and shortcuts. Never add disc files or cards to this package. The normal launcher's CMake ownership
checks remain unchanged. `session_summary.h` derives human/JSON summaries only from bounded report files;
unknown metrics stay absent, and queue/scoped timings must not be presented as GPU frame time. Validate with
`tools/test/session_diagnostics.py`, packaged UI/game smoke and `tools/test/verify_setup.py`.

`launcher/src/session_diagnostics.*` implements the independent `gow-session` collector and local report export.
It must keep collecting when the launcher closes, preserve actual child exit codes, and stop only its own child.
Reports use bounded files under launcher app data (`registros/sessions`), distinct from pipeline logs. Export only
the explicit allowlist; never add ISOs, saves, full environment dumps or automatic uploads. Keep redaction and
truncation indicators. Basic mode uses frames-only accounting; expensive per-call timing stays opt-in.
Patch 29c supplies bounded guest-frame interval distributions with a profile-supplied frame PC. These are not
GPU/presentation latency. Run `tools/test/session_diagnostics.py` against the deployed helper after collector changes;
`verify` includes frame-metric tests. Instructions and metric semantics: `docs/reporting-bugs.md`.

## Contracts (do not break)

- **Individual saves (zzz-323)**: the launcher and in-game menu read the four valid 16-byte records of the USA
  68-byte card index, not every dataN.bin file. `launcher/src/native_save_slots.h` must match the runtime copy
  shipped by the patch. `tools/disc/save_slots.py` derives edition-specific names/previews from disc resources;
  `discs` and `sync` populate `.gow-save-slots`. Never package those copyrighted caches or player cards.
  Loading uses a session-local request and the EE's native teardown/frontend/load path, with loader state 8
  (not a transient UI dialog field) as the slot-selection gate. Validate card 0 and the native index before
  choosing; preserve original resume/error paths. Never overwrite the IOP's active card. Whole-card history
  restoration still requires a closed game; regional hooks remain unvalidated. Run `save-slots.py`,
  `native-load-tests.py`, `game-menu.py`, `save-history-ui.py` and the private-card `native-save-smoke.py`.
  Evidence: `docs/research/native-save-slots-2026-11-10.md`.

- **Pipeline output protocol** (parsed by `installer_backend.cpp`): `=== <step> ===`, `@@progress <done> <all>`,
  `@@status <text>`, anything else is log. Errors: a final `ERROR: <message>` line and exit code 1.
  `modules/build-progress.ps1` excludes Ninja glob checks and nested CMake regeneration counters from game progress.
  Resume counters only at the outer build directory's CMake completion marker. The loading screen updates its
  weighted progress after complete events, never moves backwards within a run, and reserves 100% for success.
  Regression checks: `tools/test/build-progress-tests.ps1` (also in pipeline-tests.ps1) and
  `python -I tools/test/loading-progress.py <Qt SDK bin/qml.exe> <llvm-mingw bin>` (real QML, fake pipeline signals).
- **languages.json** (`data/<id>/`): `{game, title, recompile_elf, languages: [{language, label, edition, quality,
  elf}]}`; quality = original | full | standalone. The launcher plays `elf` of the chosen language.
- **In-game menu (patch 39, redesigned by zzz-318)**: F1 or Back+Start opens the category dock in `gow_trucos.cpp`
  (Graphics, Controls, Audio, Mods, Cheats, Save); F2 opens cheats, Ctrl+F1 opens the ImGui runtime debugger.
  Remapping, master volume/mute and supported graphics changes are live and persist through the launcher settings bridge.
  The menu pauses simulation and audio consumption; it keeps host input/rendering active. Graphics changes use the header-only
  `runtime/gow_ajustes_vivo.h` (read once from GOW_SCALER, GOW_SHARPEN, TOBIICHI_FXAA, GOW_ANISO, TOBIICHI_ASPECTO,
  TOBIICHI_FPS_GOSTER); the launcher imports durable edits on its next poll/open.   TOBIICHI_PANTALLA = completa | sin_bordes |
  ventana (sin_bordes: borderless over the monitor, for capture/scaling tools). Every launcher variable must have a
  runtime reader: dynamic scale, sharp image, the renderer switch and the shader cache were removed for having none.
- **GS primitive grouping (patch 66)**: since the PR 26 integration the PR's patch 66 is in the chain and grouping
  is ON by default (`PS2X_GS_RUN=0` restores individual submissions; the launcher writes it from
  `gsAgruparPrimitivas`). This is still an open decision: fix-chore's laptop A/B improved mean FPS but regressed
  p95/p99 in its last pair, and the PR's evidence is frontend cost on an HD 4400 (366-427 -> 86-118 ns/vertex), not
  frame tails. `gs-run-ab.py --compare grouping` on the i5-8265U is the gate; if p95/p99 regress again, set the
  default back to off in both `gs_frontend.cpp` (zzz-300) and `Main.qml`, and record it in the performance ledger.
  zzz-300 restored fix-chore's review fixes to the run encoder and the per-GS read of `PS2X_GS_RUN`.
  fix-chore's opt-in GS candidates (67 alpha prune, 72 sampler cache, 73 specialized shader, 74 alpha bounds,
  75 variant counters) and 71 VU1 chain inline are not in the chain since the PR 26 integration: they conflict
  with the PR's renderer rewrite and none was a shipped default (the notebook favored 67's reference in all three
  pairs). Their patches and tests are archived in `docs/research/pr26/deferred-fix-chore-patches/`; port one only
  with its test back in verify.
  `gs-run-ab.py --compare grouping|alpha|scaler --gpu-samples` uses private disc/card roots and optional Windows PDH
  engine counters. GPU busy time is not power draw; report the busiest engine, not a sum of independent engines.
  Timing/capture runs are not FPS benchmarks; scaler comparisons change output filtering and must disclose that.
  Preserve flush ordering at state/transfer/CLUT/TEXFLUSH/FINISH/presentation/readback boundaries and GIF packet ends.
  Inactive vertex tails must use `GSVertex{}` defaults (`q=1`), never read multiple vertices from a single local.
  `gow_gs_run_tests` in `verify` compares the production frontend and worker queue against the individual path.
  `tools/test/gs-run-ab.py` uses one executable, frames-only timing and private disc/card roots for visible A/B tests.
  Window percentile medians are not pooled frame-time percentiles. Keep captures separate from FPS runs.
- **Graphics settings coverage** (`launcher/qml/PaginaGrafico.qml`): the Graphics tab exposes every picture, texture
  and renderer variable the runtime reads — the original quality controls, the texture-pack controls from patch 52
  (`GOW_TEXTURE_PACK_MB`, `_STATS`, `GOW_TEX_PCSX2_NAMES`, `GOW_GS_HW_TEXDUMP`), presentation (`GOW_PROGRESIVO`,
  `TOBIICHI_ASPECTO` with fixed ratios, `PS2X_GS_DIRECT_PRESENT`, `GOW_GL_MAX_MINOR`), the GS pipeline switches
  (patches 59/61/66/69/72/74/77) and the renderer diagnostics. Pipeline and diagnostic switches sit behind
  "Advanced renderer options" and are labelled with their variable name. Defaults reproduce the shipped build:
  on-by-default switches write "1" (the runtime only checks for "0"), set-means-on switches are removed when off,
  and numeric defaults are removed so the runtime's own value applies. A new switch needs a `Settings` property,
  `restablecer()`, the `jugar()` play map, `Lanzador::iniciar`, `Textos.js` + `idiomas/*.js`, and both
  `session_diagnostics.cpp` allowlists, and `tools/mods/gow_mods_cli.py`'s `ENV_ALLOWED` (plus an `EFFECT_PRESETS`
  entry when a mod should offer it); `tools/test/launcher-env-contract.py` and `tools/test/regional-play-ui.py`
  guard the chain. `GOW_TEX_PCSX2_NAMES` is launcher-owned and stays in `ENV_RESERVED`: a mod must not redirect
  the exported texture-name list. Never expose a variable without a `getenv` reader: `GOW_RENDER_HEIGHT`, `GOW_GS_TIER`,
  `GOW_FPS_TARGET`, `GOW_MIN/MAX_SCALE`, `GOW_TEX_PRELOAD`, `PS2X_GS_ESCALA`, `TOBIICHI_FILTRO` and
  `PS2X_GS_SHADER_CACHE_DIR` exist only in design docs or are dead; `PS2X_GS_FOG_OFF` has a reader but the game
  never draws with GS fog, so exposing it would be a switch that changes nothing. All renderer switches are read
  once at startup: changing one needs a game restart (the F1 menu only handles patch 39's live atomics).
- **Runtime env vars the launcher sets** (see `lanzador.cpp`): TOBIICHI_* (window, keys, cheats), PS2X_GS_* (renderer),
  GOW_VU1_CAPTURA (continuous VU1 recording into data/<id>/vu1_capture), GOW_ANISO (anisotropic filtering, 2..16),
  GOW_QTE_HOLD / _HZ (accessibility: a held button becomes the presses the minigames ask for, engine/patches/53; the
  logic is tested without the game by tools/test/qte_hold_test.cpp in verify).
  Shoulder-button repetition (L1/L2/R1/R2) is individually opt-in in the launcher; it can interrupt held actions.
  GOW_QTE_STICK=shake|rotate (patch 56) enables the explicitly held `qte_stick` keyboard/mouse binding (default G).
  It overrides only the left stick at the final configurable-stick read, stops on release/focus loss, and leaves
  all four connected gamepad slots alone. Off by default; no automatic QTE detection. Scripted pad tests disable it.
  The same isolated QTE suite covers gesture timing, direction coverage, release and repeated reads.
  Patch 57 preserves held button chords: a key shared with an evade modifier belongs to its gameplay button first.
  Default keyboard evade is Alt + WASD; Ctrl stays R2. Teclas.js migrates the former shared Ctrl default and marks
  modifier/button overlaps as conflicts. Shoulder auto-repeat pauses during stick movement or multi-button chords,
  restarting its delay afterwards. Patch 58 also pauses face-button repetition during chords, protecting R2 + Cross
  with the full face group enabled. Migration leaves new Alt/G shortcuts unassigned if those keys are occupied.
  Production-pad tests cover Ctrl + WASD, Ctrl + Space and both Ctrl aliases.
  GOW_VU1N_X64=1 (in-process x86-64 VU1 JIT, engine/patches/18, experimental: the Performance tab's "Compile new areas
  while playing"; docs/research/vu1-x64-jit.md). GOW_VU1N_JIT + GOW_VU1N_JIT_CXX/_PY/_GEN/_FLAGS (patch 17's background
  clang compiler, by hand: data/<id>/vu1_jit.json, which clang builds write, names the values).
  GOW_VU1_CAPTURE_MISSES=1 (patch 19): capture a context image only for a missing dispatched block, before JIT compilation;
  each image is a full 16 KB micro-memory, written once per distinct image as miss_<image hash>.bin (patch 26; before it,
  block_<key>.bin per missing block), and indirect heads are recorded even when JIT succeeds. Launcher uses it.
  GOW_PERF_FRAME_PC (the profile's [diagnostics].frame_pc, read by InstallerBackend::diagnosticsFramePc) is set with the
  Performance tab's diagnostics toggle, next to GOW_AUDIO_STATS / GOW_IOP_DRIFT / GOW_VU1N_DIAG / GOW_PERF_DIAG.
  GOW_MC0 (the memory card image: Mcd001.ps2 next to the ELF unless already set) and GOW_SAVES_DIR (data/<id>/saves):
  F1 > Save in game (Ctrl+F1 > Saves in the debugger) copies the card to GOW_SAVES_DIR/<yyyyMMdd-HHmmss>/{Mcd001.ps2, save.json} (patch 26); the Saves
  tab (PaginaPartidas.qml, Lanzador::partidas/guardarPartida/importarPartida/restaurarPartida/borrarPartida) lists,
  makes, imports, deletes and restores copies. save.json: {label, time, source: auto|F1|launcher|import|backup, card, bytes}.
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
- Launcher interface texts: `launcher/qml/Textos.js` (tr, en, es, pt inline) and `launcher/qml/idiomas/<code>.js` (fr, de,
  it, ru, zh: one file per language, the keys of Textos.js).
- Identifiers inherited from the Tobiichi Launcher stay Spanish (`lanzador`, `ajustes`, `Pagina*`...) to keep its code
  diffable with upstream; their comments are English. New code uses English names.
- The downloaded runtime keeps its authors' comments (some Spanish). Patch context lines are upstream code: never
  edit them, or the patch stops applying.

## How to change things

- **Disc formats and regions**: CHD conversion is not regional runtime support. `game.toml`'s `regions` table only
  recognizes foreign executables and excluded demos; never enable them against the USA function map/overrides.
  The Japan disc's code differs (see `docs/disc-import.md`). `chdman verify` may return zero on a hash mismatch:
  require raw and overall success confirmations. Keep source images read-only and converted ISOs out of packages.
  Run `python -I tools/disc/import_test.py --chdman <exe>` for real synthetic CHD round trips, plus
  `tools/disc/prepare_test.py` and `tools/test/disc-import-ui.py <Qt bin/qml.exe> <compiler bin>` for import changes.
  The supplied Asia ISO actually boots the byte-identical USA ELF (SCUS_973.99); its own disc layout was prepared
  and opening gameplay validated. Do not infer region compatibility from filenames or extend this to SCAJ_300.10.
  Europe SCES_531.33 has experimental generated C++ only, not a validated runtime port. See
  `docs/research/regional-port-2026-11-02.md`. `recompile.py` checks the profile ELF name and code signature before
  generation/publication, including when languages.json was edited. Preserve this gate and translation compatibility.

- **Runtime code**: edit in `engine/runtime/`, then turn the change into a new `engine/patches/NN-name.patch` (git diff
  in engine/runtime, with a header saying what/why/measured result). Patches apply in order; a later patch may depend
  on an earlier one. Keep each patch to one concern.
  Changes to the profile's `runtime.overrides` also require `sync,build`: the runner compiles owned copies under
  `ps2xRuntime/src/runner`, not `engine/runtime/src` directly. A successful `fetch,build` can leave the previous
  override in the executable. Check synchronization and runner identity before accepting a gameplay comparison.
- **Moving the patches to a newer runtime commit**: `tools/pipeline/patches.ps1 start -Onto <commit or ref>` turns
  engine/patches into a commit stack (branch gow-patches, worktree engine/runtime-patches) and rebases it with git's
  3-way merge; resolve conflicts there (`git add`, `git rebase --continue`), then `patches.ps1 export` rewrites only the
  patches whose file no longer applies exactly, removes those already upstream, updates runtime.toml's commit and checks
  the chain gives the stack's tree; `patches.ps1 drop` removes the worktree. Commit message = name, header,
  `Patch: <name>`. `git apply --3way` is no substitute: most patch files have no `index` lines.
  Test: `tools/test/patch-stack-tests.ps1` (in verify).
- **New game**: see `docs/adding-a-game.md`.
- **New translation / edition**: add an `[[editions]]` entry (elf_crc from `identify.py`); if it changes code (.text
  differs) it is not supported.
- **Launcher texts**: a new key goes in `launcher/qml/Textos.js` with tr/en/es/pt; the languages in `launcher/qml/idiomas/`
  fall back to en until the key is added there. A new language: `idiomas/<code>.js` (copy one), its `.import` and
  `archivos` entry and the `idiomas` list in Textos.js, and the file in launcher/CMakeLists.txt. `python -I
  tools/test/launcher-languages.py` (also in verify) checks keys and %1/%2 placeholders. The in-game F1 menu
  (patch 39, TOBIICHI_IDIOMA) has tr/en/es/pt only and shows English for the others.

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
- Build parallelism: one compiler per 1.0 GB above 4 GB (measured 0.5 GB average, 0.64 GB peak per compiler on the game
  build); patch 41 keeps the 12.8 MB register_functions.cpp out of unity/PCH at -O1. Release optimisation flags are
  always passed explicitly: CMakeCache.txt keeps any value once given, which silently kept a -O1 training build.
- Stage `tune` (the install's first-play preparation) = one instrumented build that records VU1/IOP code and the PGO
  profile in one run, then one final build. Keep its training build at -O3: a -O1 training build compiled 2.2x faster
  but its profile produced a build measured ~9% slower (3/3 pairs). Its step texts reuse the pgo/native ones, which
  LoadingScreen.qml and InstallPage.qml match by prefix.
- Small CPUs (`installer.cpuThreads() <= 4`) install with `build,optimize` instead of `tune`: no PGO, so one full -O3
  build fewer. Build jobs reserve 1 thread (not 2) on such CPUs (context.ps1). PGO stays available via the `pgo` stage.
- Release profile (game.ps1 `Use-ReleaseProfile`): the package ships this checkout's PGO profile as
  `games/<id>/pgo/shipped.profdata` + `.json` (never committed: `.gitignore`). Its manifest is the identity the generated
  code depends on: `engine/runtime.toml`, the patch set (ordinal order, `Get-RuntimePatches`), the `games/<id>` files
  outside `pgo/`, and the SHA-256 of the recompiled ELF's `.text` (a fan translation changes data, not code: the PT-BR
  `.text` is byte-identical to the USA one). A configure of the main build folder without a fitting local profile takes
  the shipped one; `tune` with a fitting profile skips the instrumented build and the training run (one build, then the
  optimize recording), and small CPUs' `build,optimize` get it too. A trained profile gets the same manifest
  (`Clear-StaleProfile`). The `package` stage refuses a profile without a matching manifest (`-NoReleaseProfile` to package
  without one): train with `-Stages fetch,configure,recomp,sync,pgo` on the release's runtime first. The `.profdata`
  holds function names derived from guest addresses (`sub_<address>`), counters and CFG hashes, no game code or data.
  Automatic configure also rejects missing, malformed or mismatched manifests; without a matching shipped profile,
  it preserves the rejected local profile and configures without PGO. Never silently reuse stale optimization data.
- Texture packs (runtime patch 52): PCSX2's replacement names, so PCSX2 packs work unchanged; the name code mirrors
  `GSTextureCache::HashCacheKey` (blocks or unswizzled rows, 32-bit palette, PSM/TW/TH/TEXA bits). Never commit or ship
  packs, dumps or screenshots of them. `GOW_TEX_PCSX2_NAMES=<file>` lists the names a session draws.
- Stage `xdelta` (`-Xdelta <patch> -Discs <base ISO>`, tools/disc/vcdiff.py): writes `data/mods/isos/<name>.iso` only when
  every window's checksum matched; a wrong base fails at the first window. Never ship third-party patches or ISOs.
- CPUs without SSE4.2/POPCNT (x86-64-v2) cannot run the build: the Install page blocks the install
  (`installer.cpuSupported()`) instead of compiling a game that would not start.
- Update markers: `data/needs-rebuild.txt` is removed by a successful final build only in a run that also fetched the
  runtime (a `sync,build` of the old runtime keeps it). `data/pgo-stale.txt` (written with it by update.ps1) makes
  `pgoApplied()` false so the launcher recommends PGO again; a new profile clears it when trained on the current runtime
  (`Clear-StaleProfile` in optimize.ps1).
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
- **Early FINISH (patch 40, GOW_GS_EARLY_FINISH=1, launcher default on)**: the EE scans each VIF1 packet for PATH2
  FINISH writes and raises FINISH at submission (or at job start when a job waits ahead), so it runs at most one job
  ahead; stage markers (GifPathId 0) suppress that job's real FINISH and apply display registers in drawing order.
  CSR access must not wait for the worker in this mode, and display stores must go through gsDisplayStore/setDisplay
  (direct register access resyncs and drops the shadow). Test-only VRAM dumps can catch the next frame mid-draw.
  Batching the worker's stage pushes (64 KiB) was measured slower (3/3 pairs, about -6%): the stage lost overlap with
  VU1. Keep per-packet pushes.
- The large-VIF1 barrier (patch 33) is opt-in since patch 38: only `GOW_VU1_EARLY_FINISH=1` enables it; the launcher
  and boot profile no longer set it. Despite its name it is a drain-before-submit wait, not the "early FINISH" of the
  25 October handoff (signalling FINISH sooner), which is still unimplemented. The setting is per memory instance. The 64 KiB threshold identifies packets, not exact guest frames. Preserve
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

Patch 73 is a USA-only high logic-rate experiment: `GOW_EXPERIMENTAL_LOGIC_FPS=120|240`,
unset/60/invalid means the original 60 Hz path. It changes the measured timestep
and the frame-end wait only; fixed steps, movies and other callers retain their
original waits. Presentation follows game flips in the experimental mode, while
VBlank/audio clocks stay unchanged. `EeScheduler::currentEeCycle()` is EE-executor-only.
Never enable it for regional overlays or add it to default boot profiles.
`logic-rate-tests.py` is part of verify; `gs-run-ab.py --compare logic-rate` uses
real-time input/windows, private cards and `GOW_DELTA_DIAG`. A speed ratio near
one does not validate frame-counted QTEs, combos or collision behavior. See
`docs/research/experimental-logic-rate.md` for evidence and limitations.

Patches 36–37 add opt-in `GOW_SYNC_DIAG=1` worker/GS-stage wait aggregates and bounded isolated MSCAL task replay.
`tools/test/worker-ab.py` separates FPS, intrusive timing and capture modes; it uses private cards and stops only its
own child. `tools/test/vu1-task-replay.py` validates local task corpora with `gow_vu1_tasks` from the verify build.
Task corpora contain game-derived code/data: keep them under ignored data, never package them or add them to the
collector export allowlist. Resume/MSCNT state is not captured. Native and exact replay match separate baselines;
their digests need not match each other. Timing excludes reconstruction/hashing/final flush and is not gameplay FPS. Details and commands:
`docs/research/worker-sync-task-replay.md`. Preserve worker/stage self-wait guards and the barrier's existing default.

The pipeline creates `gow-native.boot` beside the built runner; the launcher atomically refreshes it on play.
It records the selected ELF and runtime-prefixed environment variables only. No-argument runner launches restore it
and write `standalone.log` beside the executable (patch 25). Never package this machine-specific profile.
The Performance diagnostics toggle enables audio buffer/rate, IOP drift, VU1 and performance counters.
`tools/test/sound_regression.cpp` covers positive/negative SPU2 master-volume overflow (patch 24).
See `docs/research/audio-standalone-mods-2026-10-26.md` for unresolved scene, HUD and mod acceptance criteria.

Patch 68 is an opt-in CPU countdown candidate (`GOW_FINISH_COUNTDOWN=1`, default off).
It wraps only USA GoW resume PCs 0x17A328/0x17A32C and batches existing quiet
checkpoints; retain generated polling/calls and full timer/IOP/event checkpoints.
`tools/test/finish-countdown-tests.py` extracts the owned `engine/runtime/src/gow_overrides.cpp`,
not the generated runner copy, and is part of verify. `gs-run-ab.py --scene ship_guard`
checks encounter state, zone and cross-run position bounds; it is not a frozen replay.
Do not equate sampler RIP occupancy (which includes waits) with thread CPU utilization.

Patch 69 gates the timed GS dump clock read; keep its first-draw origin and eligible
first-batch trigger. `gs-run-ab.py --task-capture` is an intrusive diagnostic mode
with a 32-record cap; never present those session FPS as a benchmark or export its
local game-derived task files. See the scene-bottleneck report for rejected combat
comparisons and the separately validated exact-input VU1 corpus.

Patch 70 adds test-only `f<N>` pad/capture times and frame-window boundaries.
`ship_arrival_frames` compares the first 360 rendered arrival frames; it is not sustained combat.
The harness requires matching frame-indexed trajectories and consecutive pad observations.
Pad-observed intervals are not GPU latency; exact audio snapshots can straddle one device callback.
Missing five-second windows and unavailable exact dropped-audio counts must remain null.
Patch 71's JIT chain adapter is opt-in (`GOW_VU1X_CHAIN_INLINE=1`), default off.
`gs-run-ab.py --compare vu1-inline` forces JIT-only in both variants and checks effective markers;
do not present those results as the shipped hybrid mode. Preserve the original chain/AOT/DLL path.
Run the methodology tests, full verify and identical-task replay for changes to these contracts.

Performance continuation checkpoint (2026-11-04):
`docs/research/render-delivery-2026-11-04/resume-checkpoint.md` records the user-requested pause,
unaccepted scalar-outline/encounter-anchor drafts, evidence and pending validation. Read it before
resuming this investigation. Drafts under that report's `drafts/` are not ordinal runtime patches;
never apply/package them automatically. A later explicit user request to resume supersedes the pause.

Queue backpressure diagnostics (patch 59): `GOW_SYNC_DIAG=1` also emits `[gow-queue]`
for stage-ring capacity (queue 1, bytes) and backend capacity (queue 2, chunks).
These producer waits include scheduling and can overlap existing VU/GS timers.
Keep timing opt-in, preserve queue ordering/limits, and test the collector parser
with `tools/test/session_diagnostics.py`. Semantics: `docs/reporting-bugs.md`.

Patch 60 bounds decoded GS texture allocations by bytes (128 MiB, excluding the active oversized texture)
and reuses existing storage after invalidation. Render targets, replacement packs and driver staging are
outside this budget. `gow_texture_budget_tests` is in verify; `gow_texture_upload_test` is an explicitly
run, real-OpenGL CT32/T8/T4 pixel check, not a headless test. `session-game-smoke.py --texture-cache`
checks `[gs-cache]` counters. Keep reference validity during eviction and preserve cache-key dimensions/formats.
Detailed private-kit reports enable `GOW_GS_HW_STATS`; normal FPS collection keeps it off.

Experimental renderer patches 72–74 remain default-off: `GOW_GS_SAMPLER_CACHE`,
`GOW_GS_FAST_SHADER`, `GOW_GS_ALPHA_BOUNDS`. Preserve reference paths, upload-time
sampler invalidation, per-program uniform locations and optional shader fallback.
Alpha bounds exclude texture-alpha-dependent draws. `verify` includes sampler
state and alpha interval tests. `gow_renderer_variants_test` plus
`tools/test/renderer-variants.py` is an explicit real-OpenGL color comparison,
not headless GPU validation. Patch 75 `GOW_GS_VARIANT_DIAG` adds test-only counters.
See GS-07/08/09 in the performance ledger before proposing default promotion.
zzz-302/304 group wrapping-blend (COLCLAMP=0 shader blend) triangles whose pixel coverage is provably disjoint
(identical shared edge, or a separating line with a 1/16 GL pixel margin) into one feedback draw; anything else keeps
one draw per triangle with a barrier. Keep the shader's destination read at `gl_FragCoord` only, or the grouping is
no longer exact. `GOW_GS_WRAP_GROUP=0` is the reference path; `GOW_GS_HW_STATS` prints `[gs-hw-wrap]`.
zzz-303 prints `[gs-run-config] enabled=N` and `[gs-wrap-config] group=N`: `gs-run-ab.py` rejects a session without
the marker of its compared setting, so keep them when touching `GS::GS()` or the renderer init.
Future Vulkan/Direct3D and automatic launcher selection are proposals only in
`docs/research/graphics-api-roadmap.md`; no such backend or selector is implemented.
