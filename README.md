<div align="center">

# God of War — Native PC

**English** · [Português (Brasil)](README.pt-BR.md)

A native PC port of *God of War* (PS2, NTSC-U `SCUS-97399`) built by statically recompiling MIPS R5900 code to C++,
with an installer launcher, one-click build, fan-translation support and a 60 fps target.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![version](https://img.shields.io/badge/version-0.5.0-crimson)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

**Linux / Steam Deck (experimental):** native launcher, build pipeline and Linux installer are available for testing.
See [installation and remaining validation](docs/linux.md). Steam Deck hardware and performance are not yet validated.

> [!IMPORTANT]
> This repository contains **no game files**. You need your own copy of God of War. The native runtime
> (**PS2Recomp**, as extended by Waffle565, KIexster and the Tobiichi port) is **required**; the launcher downloads it,
> it is not stored here. Full attribution: [`CREDITS.md`](CREDITS.md).

> [!WARNING]
> **The project is not finished yet.** The game is playable, but it is not 100%: a locked 60 fps is not reached in
> every scene, only the opening areas have been measured in depth, and some issues remain (see
> [Known limitations](#known-limitations)). It gets better with every release, and more will be added as the community
> needs it — texture packs, ISO patching and experimental Linux are now available; further work is in the [Roadmap](#roadmap).
> Bug reports with the launcher's session report help a lot: [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Contents

- [What is this?](#what-is-this)
- [What's new in 0.5.0](#whats-new-in-050)
- [What's new in 0.4.0](#whats-new-in-040)
- [What's new in 0.3.1](#whats-new-in-031)
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
- **Built for speed**: Windows builds can use a matching profile-guided optimisation (PGO) profile. The 0.5.0 package
  ships without a pre-trained profile; local training remains available. The first-play preparation records the
  game's VU1/IOP code in one run and builds it in as native code.
- **Configurable controls**: full keyboard/mouse bindings, classic or modern gamepad layouts and button-by-button mapping.
- **Accessibility**: the minigames that ask for repeated presses can be played by holding the button instead
  ("Hold instead of mashing" in the Accessibility tab), alongside stick gestures and texture packs.
- **In-game menu (F1)**: graphics settings changed live, cheats and memory-card copies.
- **Launcher in nine languages**: English, Portuguese, Spanish, Turkish, French, German, Italian, Russian and
  Simplified Chinese.

## What's new in 0.5.0

- **Experimental Linux:** native launcher, build pipeline and `.run` installer for testing on Linux PCs and
  Steam Deck. Built and smoke-tested in WSL; real Steam Deck performance and compatibility remain unvalidated.
- **ISO and CHD import:** verified CHD conversion to a local ISO cache before recompilation; original images stay intact.
- **Regional editions:** USA and the tested USA-compatible Asia disc; Japan and Europe have isolated Windows builds
  validated through opening gameplay. They require a matching registered build and are not automatically compiled
  by the USA pipeline. Demos are excluded. See [regional compatibility](docs/disc-import.md).
- **Accessibility page:** texture-pack selection and input assistance in one place. PCSX2-format PNG replacements
  can change the game's appearance; packs are not included. Quality and compatibility depend on the pack.
- **Keyboard/mouse improvements:** held Ctrl + Space and Ctrl + WASD chords are preserved; default evade is Alt + WASD.
  Optional stick gestures (default G) help with stick-based minigames. L1/L2/R1/R2 repetition is individually opt-in.
- **Movie audio:** fixed stale audio from one movie corrupting the next movie's PT-BR voices (patch 54).
  Earlier sound-effect fixes are retained; this is not a claim that every cutscene or transition is fixed.
- **Build time:** large native IOP modules compile in parallel parts (patch 55). On the recorded Xeon test, the longest
  unit fell from 126.5 s to 24.5 s; this is not the total installation time. Further reductions remain a goal toward 1.0.0.
- **Graphics:** existing internal scaling, sharpening, FXAA and external-tool borderless mode remain available.
  DLSS, including DLSS 5, is not integrated. See [upscaling](#upscaling-and-external-tools).

The target remains stable **60 guest FPS**, with continued work for slower computers. Recorded measurements do not
establish a locked 60 FPS across all mid-range PCs or the entire game. See [tested hardware](docs/tested-hardware.md)
and the full [0.5.0 changelog](CHANGELOG.md#v050--2026-11-02).

Setup and troubleshooting: [Accessibility, keyboard assistance and texture packs](docs/accessibility.md).

### Linux experimental download

From [Releases](https://github.com/Vnnc1/gow-native-pc/releases), download
`gow-native-pc-linux-x86_64-ubuntu26.04-experimental.run` and its `.sha256`, then run:

```sh
bash gow-native-pc-linux-x86_64-ubuntu26.04-experimental.run
bash "$HOME/.local/share/gow-native-pc-0.5.0/start-linux.sh"
```

Install the matching system dependencies first; this uses Ubuntu 26.04 libraries and is not a universal AppImage.
The installer refuses an existing destination to protect games and saves. Import your own compatible disc in the
launcher to compile the game. SteamOS and other distributions may require rebuilding the launcher from source;
see [Linux installation and limitations](docs/linux.md). The Windows steps below still use `gow-native-pc-setup.exe`.

## What's new in 0.4.0

> [!NOTE]
> **Coming from v0.3.1 or earlier? Run the 0.4.0 setup once over your installation.** Releases were renumbered on
> 2026-10-31 (v1.0.0, v2.0.0, v3.0.0 and v3.0.1 are now v0.1.0, v0.2.0, v0.3.0 and v0.3.1, same files), and a launcher
> from before the renumbering does not see 0.4.0 as an update. Your game build, discs and saves are kept; automatic
> updates work again from 0.4.0 on. Every release: [`CHANGELOG.md`](CHANGELOG.md).

- **PGO profile in the release**: the install uses the release's profile directly — no instrumented build and no
  training run — and CPUs with 4 threads or fewer, which skipped PGO before, now get it too.
- **Fast VU mode** (off by default; Launcher → Performance): VU1 code without the exact float clean-ups, like PCSX2's
  default settings. About 12% less VU1 work in a recorded combat replay (runtime patch 51). Most useful on slower
  CPUs, where VU1 is the limit.
- **Hold instead of mashing** (accessibility, Launcher → Controls), by
  [ThisIsAkill](https://github.com/ThisIsAkill) (PR #10, patch 53).
- **Launcher in French, German, Italian, Russian and Simplified Chinese**; the system's language is picked on first
  start.
- **Fixes**: sound effects going silent after about 35 s of combat (patch 48); a frozen pink screen when the GPU
  renderer cannot start now explains why (no OpenGL 4.3, generic driver, Remote Desktop; patch 52); an install script
  quarantined by an antivirus is reported as such instead of "Failed (code 1)"; installs in a folder with a space in
  its name no longer fail.

## What's new in 0.3.1

Measured on the test PC (Xeon E5-2666 v3 + RX 580, save route, full screen, alternating pairs); details in
[`docs/research/roteiro-60fps.pt-BR.md`](docs/research/roteiro-60fps.pt-BR.md):

- **Faster VU1 code**, same results bit for bit (runtime patch 43): average about 51 -> 57 FPS, heavy combat about
  51 -> 55 FPS.
- **Cheaper hand-off to the GS thread** (patch 44): about 150,000 fewer thread wake-ups per second, combat +3.5%.
- **VU1 decode on demand and one copy less per GIF packet** (patches 45-46, from the
  [gow-native-pc-optimization](https://github.com/huanghuangdaquan-beep/gow-native-pc-optimization) fork).
- **Install**: dependencies are downloaded once and shallow (the profile-guided step no longer re-downloads ~1 GB);
  CPUs with 4 threads or fewer skip the profile-guided pass and use one more compiler; CPUs without SSE4.2 are told
  before the install instead of after it.
- **Older GPUs**: GPUs whose drivers stop at OpenGL 4.3-4.5 (such as Intel HD 4000-4600) now get an OpenGL context
  for the GPU renderer instead of failing to start it (patch 47).
- **Updates**: the "rebuild" notice clears only after a rebuild with the new runtime, and the launcher recommends
  retraining the profile-guided optimisation after an update.

Earlier releases (0.3.0: Early FINISH, PGO in the install, the F1 menu, the VU1 JIT): [`CHANGELOG.md`](CHANGELOG.md).

## Required: the PS2Recomp runtime

Without the runtime nothing can be recompiled or run. It is **not part of this repository**: **Install and build**
in the launcher or the `fetch` stage of `build.cmd` clones it into `engine/runtime/` as pinned in
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, which bundles ran-j's PS2Recomp with Waffle565's and
KIexster's extensions) and applies [`engine/patches`](engine/patches) (01–58 in this release).

## Requirements

| | |
|---|---|
| OS | Windows 10/11 64-bit |
| CPU | x86-64 with SSE4.2 (x86-64-v2); AVX/AVX2 are used by the VU1 JIT when present. 4 cores or more recommended: 2-core/4-thread laptop CPUs run the game slowly (see [Performance](#performance)) |
| RAM | 8 GB (16 GB recommended while building) |
| GPU | OpenGL 4.3+ (4.3 needs `NV_texture_barrier` or `ARB_texture_barrier`, as Intel HD 4000-4600 drivers have), with the GPU maker's driver installed. The GPU renderer is the only renderer: without OpenGL 4.3 (or with Windows' generic display driver, or over Remote Desktop) the game window says so instead of showing the game |
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
   2. **Add ISO / CHD…** — select one or more compatible disc images; the launcher identifies the game and language;
   3. **Install and build** — downloads the runtime, prepares the disc and compiles the game. A matching shipped PGO
      profile is used when available; 0.5.0 does not include one. Leave **Prepare the first play (recommended)** enabled: a copy of the game plays itself for four
      minutes, **hidden and muted**, recording the VU1/IOP code it uses, and that code is compiled in.
3. Pick a **graphics profile** (Graphics page), check **Controls** if you play on the keyboard, then **PLAY**.

CHD import verifies and extracts the image into a local ISO cache. It needs additional disk space.
The supplied Asia image with the USA-identical executable was built and tested. The exact Japan and Europe
images now have isolated Windows builds tested through opening gameplay; registered builds are selectable in
the launcher. They cannot use USA recompilation/PGO. Demos are excluded; identity follows the executable, not its filename.
See [disc formats and regional compatibility](docs/disc-import.md).

Build time depends on the CPU, RAM, storage and downloads; the game's ~6,400 recompiled functions are compiled on your
PC. On the test PC (Xeon E5-2666 v3, 20 threads, 16 GB) the whole installation took **about 30 minutes** when it still
trained its own PGO profile (0.3.x). A matching shipped profile can avoid that training, but v0.5.0 ships without one.
On a 2-core/4-thread laptop CPU (i3-10110U) an install took **about 75 minutes**. These are historical references,
not deadlines. A game installed with an older version shows **"FPS optimisation recommended (PGO)"** on the Home page.

### From a terminal

Run these commands from the repository folder (PowerShell: prefix `build.cmd` with `.\`):

```bat
build.cmd -Discs "D:\God of War (USA).iso" -Stages tools,fetch,discs,configure,recomp,sync,tune
```

This is what the launcher does: tools, runtime, disc preparation, recompilation and the `tune` stage (recording run +
final build with the release's PGO profile; without a fitting profile it also trains one). Without first-play preparation, use the default `build.cmd -Discs "D:\God of War (USA).iso"`.
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

By default, the game keeps its original 60 Hz frame pacing. Every measurement, with the code
and settings used: [`docs/tested-hardware.md`](docs/tested-hardware.md). Results vary between machines — treat them as
a reference.

An opt-in **120/240 logic-rate experiment** is available for development tests, disabled by default.
The local laptop tests did not reach these gameplay rates; host presentation frequency is not guest FPS.
See [instructions, results and remaining validation](docs/research/experimental-logic-rate.md).

On the project's **Xeon E5-2666 v3 / 16 GB / Radeon RX 580 2048SP** test PC (full screen 1080p, internal resolution 2×,
PGO, Early FINISH), the opening ship averages **about 55 fps**, with heavy-combat windows around **50–53 fps**; a
30-minute session from a later save averaged 48 fps with stable memory. **A locked 60 fps is not reached yet**: the
remaining limit is the VU1 work on the CPU (about 19 ms per frame in the heaviest combat, 16.7 ms are needed). Lowering
the internal resolution helps only when the GPU is the limit.

On a **2-core/4-thread laptop CPU (Core i3-10110U, Intel UHD Graphics)** the image is correct but the game is slow:
menus at 40–48 fps and **about 20 fps in combat** on the ship (internal resolution 1×, no PGO, 0.4.0 test build). The
diagnostics report shows the VU1 thread busy over 90% of the time there, so the CPU is the limit, not the GPU. Fast VU
mode gave about 10% there; AVX2 builds (`-CpuTarget x86-64-v3`) were measured and do not speed up the VU1 code. Reports
from other machines are welcome: turn on **Audio and compilation diagnostics** first.

## Upscaling and external tools

- **Built in:** internal resolution (the game really draws 2×, 3×… more pixels), a sharp scaler (bicubic + adaptive
  sharpening), FXAA and anisotropic filtering — all in Launcher → Graphics, most also live in the F1 menu.
- **DLSS (including DLSS 5), FSR 2–3 and XeSS:** not integrated in this port. The existing borderless option
  enables external capture/scaling tools; it does not install DLSS or establish compatibility with a particular tool version.
- **External tools** such as Lossless Scaling (scaling / frame generation), ReShade (OpenGL) and OBS see the game in
  **borderless** mode (Launcher → Graphics → *Allow external tools*). They are not officially tested and may add latency;
  frame generation works best when the game already runs at a steady rate.

## Translations and languages

Compatibility is checked against the executable's **`.text` SHA-1** in [`games/gow1/game.toml`](games/gow1/game.toml).
Translations that preserve the original game code can be accepted even without a named edition entry; their language
is detected from menu text. Translations that modify code cannot use this pipeline. Different-code regions need
their own validated, registered build; see the regional compatibility table.

| ISOs selected | Result |
|---|---|
| USA original | English game |
| Compatible translation | Translated game with the movies present on that disc |
| USA original + compatible translation | Original movies, including widescreen, with translated text |

The launcher asks which language to use when multiple languages are available. See [`docs/translations.md`](docs/translations.md)
for compatibility and disc preparation details.

The launcher itself is in English, Portuguese, Spanish, Turkish, French, German, Italian, Russian and Simplified
Chinese (chosen on the Other page; the system's language on first start); the in-game F1 menu has English, Portuguese, Spanish and Turkish texts.

## Reporting problems

The launcher records a bounded report for each session. Use **Other → Mark a problem during play** when an issue
occurs, then **Other → Test and bug report** after closing the game to export the ZIP. Review and attach the ZIP to your bug report with the
area and reproduction steps. Nothing is uploaded automatically; game files and saves are excluded. Detailed
diagnostics are optional and can reduce FPS. See [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Known limitations

- A locked 60 fps is not reached in heavy combat yet (see [Performance](#performance)).
- Only the opening areas (the ship) have been measured in depth; later areas may behave differently.
- Short hitches with audio gaps can still occur at area transitions. The reproduced PT-BR movie channel-alignment
  defect is fixed by patch 54; other scenes still need testing. Missing or cropped video on a repacked disc may require
  the original disc; see [translations](docs/translations.md).
- Some replacement packs can show transparent enemies. The observed pack/runtime interaction remains unresolved;
  compare the same scene without replacements when reporting it.
- 2-core/4-thread laptop CPUs run the game at about 20 fps in combat (see [Performance](#performance)).
- If you see image glitches, turn off **Finish frames early** (and **Fast VU**, if you turned it on) in Launcher →
  Performance and report it.
- Linux is experimental; Steam Deck, regional Linux builds and broad GPU compatibility remain unvalidated.

## Roadmap

The full plan, with measurement gates for each item: [`docs/research/roadmap-2026-10-27.md`](docs/research/roadmap-2026-10-27.md).

| Priority | Focus | Status |
|---|---|---|
| 1 | Build and recompilation quality | Largely done in 0.3.0 (pinned toolchain, caching, verify, faster install with PGO); a sub-20-minute install is next |
| 2 | Stable 60 fps | Early FINISH and PGO done; next: static VU1 timing (the remaining ~14% in heavy combat), native VU1 ops still interpreted |
| 3 | Audio | PT-BR movie alignment fixed (patch 54); investigate remaining transitions and scenes |
| 4 | Mods and texture packs | PCSX2-format replacements and ISO xdelta patching implemented; improve compatibility and mod management |
| 5 | Linux port | Native pipeline and experimental installer implemented; validate real Steam Deck hardware and portable dependencies |
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
