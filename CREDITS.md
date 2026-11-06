# Credits

This project assembles, adapts and documents work published by other people. It is a derivative work and is
distributed under the **GNU General Public License v3.0** (see `LICENSE`), like every project it builds on. Their
copyright notices stay in their files; changes made here are described in `engine/patches/*.patch` (one header per
patch) and in the history of this repository.

| Project | Authors | What this project uses | License |
|---|---|---|---|
| [PS2Recomp](https://github.com/ran-j/PS2Recomp) | ran-j and contributors | The MIPS R5900 → C++ static recompiler (ps2xRecomp) and the native PS2 runtime (ps2xRuntime, ps2xIOP): the foundation everything runs on | GPL-3.0 |
| [God-Of-War-Native-Port](https://github.com/Waffle565/God-Of-War-Native-Port) | Waffle565 | The God of War native port on PS2Recomp: native GS renderer, VU1 and IOP compiled ahead of time, sound, pad, memory card, the game's overrides; `tools/disc/iso_extract.py`; the CPU speed-ups backported in `engine/patches/04-cpu-backports-from-waffle.patch` | GPL-3.0 |
| [god-of-war-recomp](https://github.com/KIexster/god-of-war-recomp) | KIexster | The patch stack that first reached God of War (USA) gameplay, its recompiler configuration and function map, and the VU1 capture fix in `engine/patches/02-vu1-capture-with-native.patch` | see its repository |
| [Tobiichi-Port](https://github.com/YYOzcan/Tobiichi-Port) | YYOzcan | The runtime this project downloads (`engine/runtime.toml`: it bundles the three above) and the **launcher** in `launcher/` (Tobiichi Launcher: Qt 6 interface, settings, controls, cheats, widescreen, image filters) | GPL-3.0 |
| [GoW2-nativo-PS2](https://github.com/cxldsakeb/GoW2-nativo-PS2) | cxldsakeb, DaniSBR1, Alejrr2 | Runtime fixes from their fork [DaniSBR1/PS2Recomp](https://github.com/DaniSBR1/PS2Recomp) (branch `godofwar2`) in `engine/patches/05` (GS upscaling fixes, anisotropic filtering, guest pools, DMA, MPEG audio, memory card, IOP imports) and the MOVZ/MOVN fix redone in `06` | GPL-3.0 |
| [gow-native-pc-optimization](https://github.com/huanghuangdaquan-beep/gow-native-pc-optimization) | huanghuangdaquan-beep | A fork of this project: its VU1 lazy pair decode and GIF zero-copy patches, rebased as `engine/patches/45` and `46` | GPL-3.0 |
| [Qt](https://www.qt.io/) | The Qt Company | The launcher's toolkit (dynamically linked) | LGPL-3.0 |

## Added in this project

- Game profiles (`games/<id>/game.toml`) and a pipeline driven by them (`tools/pipeline/build.ps1`, `profile.py`).
- Disc identification and preparation (`tools/disc/identify.py`, `prepare.py`, `discfs.py`): one ISO or several, fan
  translations recognised and run on their own or on top of the original disc, one memory card for all languages.
- The launcher's Install tab and installer backend (`launcher/qml/InstallPage.qml`, `launcher/src/installer_backend.*`),
  the language question, continuous VU1 optimisation while playing, Brazilian Portuguese interface texts.
- Runtime patches 01 (LTCG option) and 03 (Windows fullscreen crash), the selection of the Waffle speed-ups in 04, the
  selection of the God of War II fixes in 05, and 07 (VU1 block heads recorded while playing, batched sound mixing,
  Release with debug information); the sampling profiler in `tools/profile/`.
- Documentation for users (`README.md`, `docs/tested-hardware.md`) and for AI maintainers (`AGENTS.md`, `docs/`).

## Game

God of War is a trademark of Sony Interactive Entertainment. No game files (disc images, executables, data, the C++
generated from them, recorded microcode) are part of this repository; users need their own copy.
