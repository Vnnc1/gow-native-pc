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
tools/pipeline/build.ps1    stages fetch, discs, configure, recomp, sync, build, optimize, native, launcher
tools/disc/discfs.py        ISO / extracted folder / TOC / ELF helpers (format notes in its docstring)
tools/disc/identify.py      ISO -> {game, edition, language, compatible, problems} (JSON)
tools/disc/prepare.py       ISOs -> data/<id>/discs/*, languages.json, shared mc0 (see its docstring)
tools/disc/iso_extract.py   ISO9660 extractor (Waffle565), writes .disc_layout/.disc_meta
tools/tests/qte_hold_test.cpp  patch 17's hold-to-mash logic without the game (build line in its header)
engine/runtime.toml         runtime repository + commit
engine/patches/NN-*.patch   changes to the runtime; header lines = what and why (git apply ignores them)
launcher/                   Qt 6 launcher (from the Tobiichi Launcher). src/lanzador.* = play side (Tobiichi's, Spanish
                            names), src/installer_backend.* = install side (ours, English), qml/InstallPage.qml = tab.
                            Own look (not Tobiichi's): qml/Main.qml = sidebar (NavItem) + pages, `pagina` 0 Home,
                            1 Install, 2-6 settings; colours in qml/Tema.qml (oro* hold the crimson accent);
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

## Contracts (do not break)

- **Pipeline output protocol** (parsed by `installer_backend.cpp`): `=== <step> ===`, `@@progress <done> <all>`,
  `@@status <text>`, anything else is log. Errors: a final `ERROR: <message>` line and exit code 1.
- **languages.json** (`data/<id>/`): `{game, title, recompile_elf, languages: [{language, label, edition, quality,
  elf}]}`; quality = original | full | standalone. The launcher plays `elf` of the chosen language.
- **Runtime env vars the launcher sets** (see `lanzador.cpp`): TOBIICHI_* (window, keys, cheats), PS2X_GS_* (renderer),
  GOW_VU1_CAPTURA (continuous VU1 recording into data/<id>/vu1_capture), GOW_ANISO (anisotropic filtering, 2..16),
  GOW_QTE_HOLD / _HZ (accessibility: a held button becomes the presses the minigames ask for, engine/patches/17).
  The pipeline's own runs (optimize, pgo) add GOW_WINDOW_HIDDEN=1 (engine/patches/15) and close the game with WM_CLOSE to
  its GLFW window (Close-GameWindow in build.ps1; Process.CloseMainWindow does not see hidden windows).
- **Step texts** of build.ps1 (`=== record: ...`, `=== build the game ...`, ...) are matched by prefix in
  LoadingScreen.qml (pasoDe) and InstallPage.qml (stepLabel): change both when renaming a step.
- The runtime registers the game's overrides for the ELF **file name** (`SCUS_973.99`) in the ELF's folder, and uses
  that folder as the CD root and `mc0/` there as the memory card: every prepared disc folder keeps the original ELF
  name; `mc0` is a junction to `data/<id>/mc0`.

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
   `GOW_PERF_DIAG=1` prints `[gow-perf]` per 5 s (ee/vu/gs/iop/guest_wait ms, host_hz); `TOBIICHI_FPS_GOSTER=1` draws
   the counter in the window.
5. `clang++ -std=c++20 -I engine/runtime/PS2Recomp/ps2xRuntime/include tools/tests/qte_hold_test.cpp -o qte_hold_test`
   (needs stage `fetch`) — the hold-to-mash logic of patch 17 without the game.
6. Record results in `docs/tested-hardware.md`.
7. Profiling: `build.cmd -Stages configure,build -Pdb` (Release with ps2EntryRunner.pdb, same code), then
   `tools/profile/sampler.cpp` (build line in its header) `sampler.exe ps2EntryRunner.exe <seconds> <delay>` prints the
   hottest functions per thread (GameThread = EE, the VIF1/VU1 worker, GSThread). `GOW_VU1N_DIAG=1` prints native VU1
   counters every 5 s; `missBlocks` > 0 means block entries without native code (see vu1n_heads below).

## Known pitfalls

- PowerShell 5.1: native stderr under `$ErrorActionPreference='Stop'` throws — use the `Native` helper in build.ps1;
  `-bxor` is signed; `Set-Content -Encoding UTF8` writes a BOM.
- MSVC LTCG on this program links for hours: `PS2X_RELEASE_LTCG` stays OFF unless a user asks.
- AMD Windows OpenGL: GS draw-batching changes from Waffle's 2026-10-17/18 commits saturated the GPU; the newer Waffle
  renderer sampled textures black. Test renderer changes on AMD and NVIDIA.
- Windows `mklink /J` needs backslash paths.
- Native VU1 block entries the generator cannot find statically (jumps through a register) must be listed in
  `data/<id>/vu1n_heads.txt` (the runtime's CMake reads `<capture dir>/../vu1n_heads.txt`). The configure stage writes it
  from the profile's `runtime.vu1_native_heads` plus `vu1_capture/vu1n_heads_seen.txt` (recorded by the runtime while
  playing with the capture on). Without it, combat runs those blocks in the interpreter (44-50 instead of 55-60 fps).
- Runtime fixes taken from the God of War II port must be checked on God of War: its `SetupThread` argc/argv change
  (5b1a25a) makes this game load its IRX as `cdrom0:\...;1` and hang at boot (left out of patch 05).
