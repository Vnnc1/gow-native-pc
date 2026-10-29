<div align="center">

# God of War — Native PC

**English** · [Português (Brasil)](README.pt-BR.md)

A native PC port of *God of War* (PS2, NTSC-U `SCUS-97399`) built by statically recompiling MIPS R5900 code to C++,
with an installer launcher, one-click build, fan-translation support and a 60 fps target.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

> [!IMPORTANT]
> This repository contains **no game files**. You need your own copy of God of War. The native runtime
> (**PS2Recomp**, as extended by Waffle565, KIexster and the Tobiichi port) is **required**; the launcher downloads it,
> it is not stored here. Full attribution: [`CREDITS.md`](CREDITS.md).

## Contents

- [What is this?](#what-is-this)
- [Required: the PS2Recomp runtime](#required-the-ps2recomp-runtime)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Updates and maintenance](#updates-and-maintenance)
- [Performance](#performance)
- [Translations and languages](#translations-and-languages)
- [Roadmap](#roadmap)
- [God of War II](#god-of-war-ii)
- [Repository layout](#repository-layout)
- [Contributors](#contributors)
- [Credits and license](#credits-and-license)

## What is this?

The game's executable (`SCUS_973.99`) is translated from MIPS to C++ by **PS2Recomp** and compiled into a Windows
program. The runtime provides graphics, audio, input and memory-card services, with compiled VU1/IOP code and an
interpreter fallback for VU1 programs that have not been compiled yet.
This project brings the work of several authors (see [`CREDITS.md`](CREDITS.md)) together behind a single installer:

- **Three-step installation**: download the portable build tools, select your ISO and install. The runtime is
  downloaded automatically; a loading screen shows overall progress, estimated time remaining and tips.
- **One ISO is enough**: the original (USA) or a recognised fan translation. With several ISOs (e.g. the original and
  a translation) every language becomes playable and the launcher **asks which language you want to play in**.
- **Optimised for 60 fps**: VU1 and IOP code is compiled natively; while you play, newly met code is recorded and
  "Speed up visited areas" compiles it.
- **Configurable controls**: keyboard/mouse bindings, classic or modern gamepad layouts and button-by-button mapping.
- **Accessibility**: the minigames that ask for repeated presses can be played by holding the button instead
  ("Hold instead of mashing" in the Controls tab).
- **Launcher updates**: new GitHub Releases are offered in the sidebar; runtime patch changes prompt a game rebuild.

## Required: the PS2Recomp runtime

Without the runtime nothing can be recompiled or run. It is **not part of this repository**: **Install and build**
in the launcher or the `fetch` stage of `build.cmd` clones it into `engine/runtime/` as pinned in
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, which bundles ran-j's PS2Recomp with Waffle565's and
KIexster's extensions) and applies [`engine/patches`](engine/patches).

## Requirements

| | |
|---|---|
| OS | Windows 10/11 64-bit |
| CPU | x86-64 with **AVX2**; 4 cores or more recommended |
| RAM | 8 GB (16 GB recommended while building) |
| GPU | OpenGL 4.3+ |
| Storage | **Under 10 GB as an estimate** for the prepared game files + one Release build, depending on the ISO edition. See the storage notes below. |
| Tools | Git, Python, CMake, Ninja and clang (llvm-mingw) are downloaded automatically into `data/_tools`. Visual Studio is only required for `-Toolchain msvc` or building the launcher/setup from source. |
| Internet | Required to download the runtime, build tools, dependencies and updates |
| Game | Your **God of War (NTSC-U, SCUS-97399)** ISO or a recognised translation |

The storage estimate covers **one prepared language and one Release build**, not a fixed limit for every ISO.
The source ISO is extracted into `data/gow1/discs/`; keeping it on the same drive uses its size **in addition** to
the installed files. Downloaded tools, the runtime checkout, extra languages, PGO/debug builds and the Qt SDK for
launcher development also take space. The ISO is not needed to play after preparation; keep your backup separately.

Builds use a short folder on `C:` by default: `C:\gow-build-clang` for clang Release. If another copy already uses
that root, the pipeline chooses `C:\gow-build-<hash>-clang`. The base path is recorded in `data/build-root.txt`;
the launcher reads it automatically. Allow space on both drives if the project and build folder are on different drives.

## Getting started

1. Get the launcher:
   - **Installer (easiest):** download `gow-native-pc-setup.exe` from
     [Releases](https://github.com/Vnnc1/gow-native-pc/releases), run it, **INSTALL** (no administrator rights,
     your user only). It adds Start menu / desktop shortcuts and an entry in Windows' *Apps* to uninstall it.
   - **Portable package:** extract `gow-native-pc-windows.zip` from the same release and open
     `launcher\bin\gow-launcher.exe` inside the extracted folder.
2. In the launcher → **Install** tab:
   1. **Download tools** — portable copies are downloaded once, with SHA-256 verification, without changing your PATH;
   2. **Add ISO…** — select one or more compatible ISOs; the launcher identifies the game and language;
   3. **Install and build** — downloads the runtime, prepares the disc and compiles the game. Leave
      **Prepare the first play (recommended)** enabled: a four-minute scripted run works **hidden and muted**,
      prepares the shader cache and records VU1/IOP code, followed by an incremental rebuild.
3. **PLAY**. **Other → Game text** switches the language.

Build time depends on the CPU, storage and downloads. A full clang build took about **15 minutes on the test PC**;
first-play preparation adds the recording time and an incremental build. This is a reference, not an installation deadline.

### From a terminal

Run these commands from the repository folder (PowerShell: prefix `build.cmd` with `.\`):

```bat
build.cmd -Discs "D:\God of War (USA).iso"
build.cmd -Stages optimize
```

The first command downloads the tools/runtime, prepares the disc and builds the game. The second runs the first-play
recording and native-code rebuild; it is **not** part of the default terminal command. For multiple languages, pass
`-Discs "D:\usa.iso|D:\ptbr.iso"`. More examples: [`build.cmd`](build.cmd).

### Building the launcher from source

Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with **Desktop
development with C++**. If Qt is not installed, a full [Python](https://www.python.org/downloads/windows/) installation
with pip is also needed for `aqtinstall`. Then run:

```bat
build.cmd -Stages launcher
```

The pipeline downloads Qt 6 when needed (about 1 GB) and creates **`God of War Launcher.lnk`** in the repository.
The release launcher already includes its Qt libraries, so players do not need the Qt SDK or Visual Studio.

## Updates and maintenance

The launcher checks GitHub Releases at startup and offers newer versions below the version number in the sidebar.
Updating preserves prepared discs, saves, tools and recorded code. If runtime patches change, **Install → Rebuild
the game** applies them and rebuilds the game.

Under **Install → More options**:

| Action | Purpose |
|---|---|
| Speed up visited areas | Compiles VU1/IOP code recorded during play (`build.cmd -Stages native`) |
| Quick rebuild | Syncs generated code/overrides and builds changed files (`build.cmd -Stages sync,build`) |
| Profile-guided optimization | Trains a separate clang build, then rebuilds using the measured profile (`build.cmd -Stages pgo`) |
| Runtime: Check / repair | Fetches the pinned runtime and applies the project's patches |

Logs are in `data/gow1/logs/`; the shared memory card is in `data/gow1/mc0/` on drives that support directory junctions
(such as NTFS). To customise the loading screen, place PNG, JPG or WebP images in `data/gow1/loading/`.

## Performance

The game is capped at 60 frames by design (its logic follows the PS2's 60 Hz VBlank). Measured and reported results on
several machines, with each code combination that was tried: [`docs/tested-hardware.md`](docs/tested-hardware.md).
The same settings may give different results on another machine — treat the table as a reference.

On the project's **Xeon E5-2666 v3 / 16 GB RAM / Radeon RX 580 2048SP** test PC, clang + PGO recorded **59.4 fps
average / 57.9 minimum** in scripted ship combat. The profile was trained on that scene; this does not establish a
locked 60 fps throughout the game. First-play preparation and compiling newly visited areas help reduce VU1 fallbacks.

Clang is the default compiler. `-Toolchain msvc` selects Visual Studio Build Tools; `data/toolchain.txt` remembers
the choice, and each compiler uses its own build folder. PGO is optional and currently requires clang.

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

## Roadmap

The [development roadmap dated 2026-10-27](https://github.com/Vnnc1/gow-native-pc/blob/claude/keen-dirac-42wd1y/docs/research/roadmap-2026-10-27.md)
on `claude/keen-dirac-42wd1y` sets these priorities, in order:

| Priority | Focus | Planned work |
|---|---|---|
| 1 | Build and recompilation quality | Better generated code, build caching, broader PGO training and correctness checks |
| 2 | Stable 60 fps | Reduce EE/VU1 overhead, streaming hitches and uneven frame times |
| 3 | Audio | Investigate PT-BR cutscene channel alignment and correct pitch drift |
| 4 | Mods and texture packs | ISO patches, file overrides, data cheats and texture replacement |
| 5 | Image quality | Internal rendering improvements, spatial upscaling, presentation and widescreen HUD fixes |
| 6 | God of War II foundation | Isolate game-specific code and prepare profiles, analysis and first-boot support |

That branch already contains VU1 JIT work, build/cache improvements and a saves tab. Those changes are **not yet
part of this `main` branch**. The table summarises planned work, not released features; temporal upscalers such as
DLSS remain research topics. Progress depends on correctness checks and measurements, with no release dates promised.

## God of War II

Planned: the architecture is per game (`games/<id>/`), but a GoW II port does not exist yet. What it needs:
[`games/gow2/README.md`](games/gow2/README.md).

## Repository layout

```
engine/     runtime.toml (which runtime to download) + numbered patches (origin and reason in each)
games/      per-game profiles: gow1 (playable), gow2 (planned)
launcher/   the Qt 6 launcher: installation + play
installer/  the release setup .exe (Win32, packs launcher + tools into one file; build.cmd -Stages installer)
tools/      disc/ (identify, extract, prepare), pipeline/ (build + updates), profile/ (sampling profiler)
docs/       architecture, tested hardware, translations, adding a game
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
