<div align="center">

# God of War — Native PC

**English** · [Português (Brasil)](README.pt-BR.md)

A native PC port of *God of War* (PS2, NTSC-U `SCUS-97399`) built by statically recompiling MIPS R5900 code to C++,
with an installer launcher, one-click build, fan-translation support and a 60 fps target.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![version](https://img.shields.io/badge/version-3.0.0-crimson)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

> [!IMPORTANT]
> This repository contains **no game files**. You need your own copy of God of War. The native runtime
> (**PS2Recomp**, as extended by Waffle565, KIexster and the Tobiichi port) is **required**; the launcher downloads it,
> it is not stored here. Full attribution: [`CREDITS.md`](CREDITS.md).

> [!WARNING]
> **The project is not finished yet.** The game is playable, but it is not 100%: a locked 60 fps is not reached in
> every scene, only the opening areas have been measured in depth, and some issues remain (see
> [Known limitations](#known-limitations)). It gets better with every release, and more will be added as the community
> needs it — **texture packs, a Linux port, ISO mods** and other features are planned (see [Roadmap](#roadmap)).
> Bug reports with the launcher's session report help a lot: [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Contents

- [What is this?](#what-is-this)
- [What's new in 3.0.0](#whats-new-in-300)
- [Required: the PS2Recomp runtime](#required-the-ps2recomp-runtime)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [In game](#in-game)
- [Updates and maintenance](#updates-and-maintenance)
- [Performance](#performance)
- [Upscaling and external tools](#upscaling-and-external-tools)
- [Translations and languages](#translations-and-languages)
- [Reporting problems](#reporting-problems)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)
- [God of War II](#god-of-war-ii)
- [Repository layout](#repository-layout)
- [Contributors](#contributors)
- [Credits and license](#credits-and-license)

## What is this?

The game's executable (`SCUS_973.99`) is translated from MIPS to C++ by **PS2Recomp** and compiled into a Windows
program. The runtime provides graphics, audio, input and memory-card services, with native VU1/IOP code, an in-process
VU1 JIT for code not compiled yet and an interpreter as the last fallback.
This project brings the work of several authors (see [`CREDITS.md`](CREDITS.md)) together behind a single installer:

- **Three-step installation**: download the portable build tools, select your ISO and install. The runtime is
  downloaded automatically; a loading screen shows overall progress, estimated time remaining and tips.
- **One ISO is enough**: the original (USA) or a recognised fan translation. With several ISOs (e.g. the original and
  a translation) every language becomes playable and the launcher **asks which language you want to play in**.
- **Built for speed**: the first-play preparation records the game's VU1/IOP code and a performance profile in one
  run and builds the final game with both (profile-guided optimisation, PGO).
- **Configurable controls**: full keyboard/mouse bindings, classic or modern gamepad layouts and button-by-button mapping.
- **In-game menu (F1)**: graphics settings changed live, cheats and memory-card copies.

## What's new in 3.0.0

Compared with 2.0.0 (details: [`docs/tested-hardware.md`](docs/tested-hardware.md) and the
[review of this release](docs/research/revisao-2026-10-30.pt-BR.md)):

| Area | Change |
|---|---|
| Performance | **Early FINISH**: the game prepares the next frame while VU1 draws the current one — about **+20% in heavy combat** (measured). On by default, switchable in Launcher → Performance. |
| Performance | **PGO included in the install**: the first-play preparation now builds with profile-guided optimisation (about +5% average, +13% in combat, measured). |
| Build | First-play preparation + PGO takes about **24 minutes** instead of about 63; more parallel compilers on machines with less RAM per core; the largest generated file builds in 10 s instead of 331 s. |
| Build | Single pinned clang (llvm-mingw) toolchain, cached code generation, `build.cmd -Stages verify` regression tests. |
| In game | **F1 game menu** with Graphics (filter, sharpness, FXAA, anisotropic filtering, FPS limit, VSync, FPS counter, stretch — all live), Cheats and Save tabs. The runtime debugger moved to Ctrl+F1. |
| Image | FXAA no longer turns off the sharp scaler; borderless full screen mode. |
| Launcher | Quick graphics profiles (Performance / Balanced / Quality), honest Upscaling and tools section, a keyboard shortcut on the Controls page, settings that did nothing removed, PGO status and recommendation. |
| Launcher | Saves page, session reports for bug reports, Portuguese texts for the in-game menu. |
| VU1 | In-process x86-64 JIT, block chaining and self-loop fast paths, capture of missing code for later compilation. |
| Fixes | Memory/DMA correctness fixes, SPU2 mix overflow, standalone launch profile, many smaller fixes listed per patch in [`engine/README.md`](engine/README.md). |

## Required: the PS2Recomp runtime

Without the runtime nothing can be recompiled or run. It is **not part of this repository**: **Install and build**
in the launcher or the `fetch` stage of `build.cmd` clones it into `engine/runtime/` as pinned in
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, which bundles ran-j's PS2Recomp with Waffle565's and
KIexster's extensions) and applies [`engine/patches`](engine/patches) (01–41 in this release).

## Requirements

| | |
|---|---|
| OS | Windows 10/11 64-bit |
| CPU | x86-64 with SSE4.2 (x86-64-v2); AVX/AVX2 are used by the VU1 JIT when present. 4 cores or more recommended |
| RAM | 8 GB (16 GB recommended while building) |
| GPU | OpenGL 4.3+ |
| Storage | **Under 10 GB as an estimate** for the prepared game files + one Release build, depending on the ISO edition. See the storage notes below. |
| Tools | Git, Python, CMake, Ninja and clang (llvm-mingw) are downloaded automatically into `data/_tools`. Visual Studio is not required. |
| Internet | Required to download the runtime, build tools, dependencies and updates |
| Game | Your **God of War (NTSC-U, SCUS-97399)** ISO or a recognised translation |

The storage estimate covers **one prepared language and one Release build**, not a fixed limit for every ISO.
The source ISO is extracted into `data/gow1/discs/`; keeping it on the same drive uses its size **in addition** to
the installed files. Downloaded tools, the runtime checkout, extra languages, the PGO training build and the Qt SDK for
launcher development also take space. The ISO is not needed to play after preparation; keep your backup separately.

Builds use a short folder on `C:` by default: `C:\gow-build-clang` for clang Release (the PGO training build uses
`C:\gow-build-clang-pgogen`). If another copy already uses that root, the pipeline chooses `C:\gow-build-<hash>-clang`.
The base path is recorded in `data/build-root.txt`; the launcher reads it automatically.

## Getting started

1. Get the launcher:
   - **Installer (easiest):** download `gow-native-pc-setup.exe` from
     [Releases](https://github.com/Vnnc1/gow-native-pc/releases), run it, **INSTALL** (no administrator rights,
     your user only). It adds Start menu / desktop shortcuts and an entry in Windows' *Apps* to uninstall it.
2. In the launcher → **Install** tab:
   1. **Download tools** — portable copies are downloaded once, with SHA-256 verification, without changing your PATH;
   2. **Add ISO…** — select one or more compatible ISOs; the launcher identifies the game and language;
   3. **Install and build** — downloads the runtime, prepares the disc and compiles the game. Leave
      **Prepare the first play (recommended)** enabled: a training copy plays itself for four minutes, **hidden and
      muted**, recording the VU1/IOP code and a performance profile, and the final game is built with both.
3. Pick a **graphics profile** (Graphics page), check **Controls** if you play on the keyboard, then **PLAY**.

Build time depends on the CPU, RAM, storage and downloads. On the test PC (Xeon E5-2666 v3, 20 threads, 16 GB) the
whole installation with first-play preparation and PGO takes **about 30 minutes**; this is a reference, not a deadline.
A game installed with an older version shows **"FPS optimisation recommended (PGO)"** on the Home page.

### From a terminal

Run these commands from the repository folder (PowerShell: prefix `build.cmd` with `.\`):

```bat
build.cmd -Discs "D:\God of War (USA).iso" -Stages tools,fetch,discs,configure,recomp,sync,tune
```

This is what the launcher does: tools, runtime, disc preparation, recompilation and the `tune` stage (training run +
final PGO build). Without first-play preparation, use the default `build.cmd -Discs "D:\God of War (USA).iso"`.
For multiple languages, pass `-Discs "D:\usa.iso|D:\ptbr.iso"`. More examples: [`build.cmd`](build.cmd).
`build.cmd -Stages verify` runs the regression tests without a disc.

### Building the launcher and setup from source

```bat
build.cmd -Stages launcher
build.cmd -Stages installer
```

The first launcher build compiles a compatible Qt once from pinned sources (it can take much longer than a game build)
and creates **`God of War Launcher.lnk`** in the repository. `installer` writes `data\_package\gow-native-pc-setup.exe`.
Players do not need Qt or a compiler for the launcher itself.

## In game

| Key | Action |
|---|---|
| **F1** | Game menu: Graphics (live), Cheats, Save |
| **F2** | Game menu on the Cheats tab |
| **F11** | Full screen / window (borderless when that mode is selected) |
| **Ctrl+F1** | Runtime debugger (for developers) |

Graphics changes made in the F1 menu last for the session; the launcher keeps your saved settings. Internal resolution
and widescreen are changed in the launcher (they need a restart).

## Updates and maintenance

The launcher checks GitHub Releases at startup and offers newer versions below the version number in the sidebar.
Updating preserves prepared discs, saves, tools and recorded code. If runtime patches change, **Install → Rebuild
everything** applies them and rebuilds the game.

Under **Install → More options**:

| Action | Purpose |
|---|---|
| Speed up visited areas | Compiles VU1/IOP code recorded during play (`build.cmd -Stages native`) |
| Quick rebuild | Syncs generated code/overrides and builds changed files (`build.cmd -Stages sync,build`) |
| Profile-guided optimisation | For a game installed without it: training run + rebuild with the profile (`build.cmd -Stages pgo`), about 20 minutes; shown as *active* or *recommended* |
| Runtime: Check / repair | Fetches the pinned runtime and applies the project's patches |

Logs are in `data/gow1/logs/`; the shared memory card is in `data/gow1/mc0/` on drives that support directory junctions
(such as NTFS). Memory-card copies: Saves page or F1 → Save ([`docs/saves.md`](docs/saves.md)). To customise the loading
screen, place PNG, JPG or WebP images in `data/gow1/loading/`.

## Performance

The game is capped at 60 frames by design (its logic follows the PS2's 60 Hz VBlank). Every measurement, with the code
and settings used: [`docs/tested-hardware.md`](docs/tested-hardware.md). Results vary between machines — treat them as
a reference.

On the project's **Xeon E5-2666 v3 / 16 GB / Radeon RX 580 2048SP** test PC (full screen 1080p, internal resolution 2×,
PGO, Early FINISH), the opening ship averages **about 55 fps**, with heavy-combat windows around **50–53 fps**; a
30-minute session from a later save averaged 48 fps with stable memory. **A locked 60 fps is not reached yet**: the
remaining limit is the VU1 work on the CPU (about 19 ms per frame in the heaviest combat, 16.7 ms are needed). Lowering
the internal resolution helps only when the GPU is the limit. Weaker CPUs (e.g. laptop i5) have not been re-measured
with this release; reports are welcome.

## Upscaling and external tools

- **Built in:** internal resolution (the game really draws 2×, 3×… more pixels), a sharp scaler (bicubic + adaptive
  sharpening), FXAA and anisotropic filtering — all in Launcher → Graphics, most also live in the F1 menu.
- **DLSS / FSR 2–3 / XeSS:** not available. They need motion vectors and a DirectX 12/Vulkan renderer; the PS2 graphics
  unit (OpenGL here) provides neither. DLSS also needs an NVIDIA RTX card.
- **External tools** such as Lossless Scaling (scaling / frame generation), ReShade (OpenGL) and OBS see the game in
  **borderless** mode (Launcher → Graphics → *Allow external tools*). They are not officially tested and may add latency;
  frame generation works best when the game already runs at a steady rate.

## Translations and languages

Compatibility is checked against the executable's **`.text` SHA-1** in [`games/gow1/game.toml`](games/gow1/game.toml).
Translations that preserve the original game code can be accepted even without a named edition entry; their language
is detected from menu text. Translations that modify code and other regions with different code are not supported.

| ISOs selected | Result |
|---|---|
| USA original | English game |
| Compatible translation | Translated game with the movies present on that disc |
| USA original + compatible translation | Original movies, including widescreen, with translated text |

The launcher asks which language to use when multiple languages are available. See [`docs/translations.md`](docs/translations.md)
for compatibility and disc preparation details.

## Reporting problems

The launcher records a bounded report for each session. Use **Other → Mark a problem during play** when an issue
occurs, then **Other → Test and bug report** after closing the game to export the ZIP. Review and attach the ZIP to your bug report with the
area and reproduction steps. Nothing is uploaded automatically; game files and saves are excluded. Detailed
diagnostics are optional and can reduce FPS. See [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Known limitations

- A locked 60 fps is not reached in heavy combat yet (see [Performance](#performance)).
- Only the opening areas (the ship) have been measured in depth; later areas may behave differently.
- Short hitches with audio gaps can occur at area transitions; the PT-BR cutscene audio has a known channel-alignment
  issue ([`docs/research/cutscene-audio-2026-10-26.md`](docs/research/cutscene-audio-2026-10-26.md)).
- If you see image glitches, turn off **Finish frames early** in Launcher → Performance and report it.
- Windows only for now.

## Roadmap

The full plan, with measurement gates for each item: [`docs/research/roadmap-2026-10-27.md`](docs/research/roadmap-2026-10-27.md).

| Priority | Focus | Status |
|---|---|---|
| 1 | Build and recompilation quality | Largely done in 3.0.0 (pinned toolchain, caching, verify, faster install with PGO); a sub-20-minute install is next |
| 2 | Stable 60 fps | Early FINISH and PGO done; next: static VU1 timing (the remaining ~14% in heavy combat), native VU1 ops still interpreted |
| 3 | Audio | PT-BR cutscene alignment and transition gaps |
| 4 | Mods and texture packs | ISO patches, file overrides and texture replacement ([`docs/research/audio-standalone-mods-2026-10-26.md`](docs/research/audio-standalone-mods-2026-10-26.md)) |
| 5 | Linux port | The runtime and launcher already have Linux code paths; the build pipeline needs porting and testing on real hardware |
| 6 | Image quality | Spatial upscaling, widescreen HUD fixes |
| 7 | God of War II foundation | Game-specific code isolated per profile ([`games/gow2/README.md`](games/gow2/README.md)) |

More will be added as the community needs it. Progress depends on correctness checks and measurements; no release
dates are promised.

## God of War II

Planned: the architecture is per game (`games/<id>/`), but a GoW II port does not exist yet. What it needs:
[`games/gow2/README.md`](games/gow2/README.md).

## Repository layout

```
engine/     runtime.toml (which runtime to download) + numbered patches (origin, reason and measurements in each)
games/      per-game profiles: gow1 (playable), gow2 (planned)
launcher/   the Qt 6 launcher: installation + play
installer/  the release setup .exe (Win32, packs launcher + tools into one file; build.cmd -Stages installer)
tools/      disc/ (identify, extract, prepare), pipeline/ (build + updates), profile/ (sampling profiler), test/
docs/       architecture, tested hardware, translations, saves, bug reports, research and reviews
data/       (generated, git-ignored) prepared discs, saves, logs, recorded code, portable tools
```

Maintainers (AI agents included): start with [`AGENTS.md`](AGENTS.md).

## Contributors

This port builds on the work of these authors and their communities:

<table>
  <tr>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/YYOzcan"><img src="https://github.com/YYOzcan.png?size=160" width="80" height="80" alt="YYOzcan avatar"><br><strong>YYOzcan</strong></a><br>
      <a href="https://github.com/YYOzcan/Tobiichi-Port">Tobiichi-Port</a><br>
      Runtime integration, Qt launcher, settings, controls, widescreen and image filters.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/Waffle565"><img src="https://github.com/Waffle565.png?size=160" width="80" height="80" alt="Waffle565 avatar"><br><strong>Waffle565</strong></a><br>
      <a href="https://github.com/Waffle565/God-Of-War-Native-Port">God-Of-War-Native-Port</a><br>
      Native GS renderer, compiled VU1/IOP, sound, input, memory cards and CPU optimisations.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/KIexster"><img src="https://github.com/KIexster.png?size=160" width="80" height="80" alt="KIexster avatar"><br><strong>KIexster</strong></a><br>
      <a href="https://github.com/KIexster/god-of-war-recomp">god-of-war-recomp</a><br>
      Patches that reached USA gameplay, recompiler configuration, function map and VU1 capture fixes.
    </td>
  </tr>
</table>

## Credits and license

- **[PS2Recomp](https://github.com/ran-j/PS2Recomp), by ran-j and contributors** — the MIPS R5900 → C++ recompiler
  and native runtime that form this project's foundation.
- **[GoW2-nativo-PS2](https://github.com/cxldsakeb/GoW2-nativo-PS2), by cxldsakeb, DaniSBR1 and Alejrr2** — runtime
  fixes adapted from their work and the [DaniSBR1/PS2Recomp fork](https://github.com/DaniSBR1/PS2Recomp).
- **[Qt](https://www.qt.io/)** — the launcher's interface toolkit, dynamically linked under LGPL-3.0.

Full attribution, reused components and their licences: **[`CREDITS.md`](CREDITS.md)**. The code in this repository
is released under the **GNU General Public License v3.0** — see [`LICENSE`](LICENSE). God of War is a trademark of
Sony Interactive Entertainment; no game files are distributed here.

[Project repository](https://github.com/Vnnc1/gow-native-pc) · [Releases](https://github.com/Vnnc1/gow-native-pc/releases)
