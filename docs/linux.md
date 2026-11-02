# Native Linux and Steam Deck (experimental)

The Linux entry point is `bash build.sh`. It builds native ELF executables with
Clang and system Qt, separate from Windows build folders and PGO profiles.
This is a development port, **not a validated Linux release or a Steam Deck
performance claim**. No Linux binary or visible gameplay was verified on the
Windows machine where this integration was authored.

## Build from source

Use a writable checkout on an x86-64 Linux filesystem. Python 3.12+, Clang,
CMake 3.21+, Ninja, Git, pkg-config, Qt 6.5+ (Core, Gui, Qml, Quick,
QuickControls2 and QML development tools), SDL2 development files, OpenGL and
the X11 development libraries required by raylib/GLFW are needed. Keep a working
X11/XWayland session for this initial runtime path. Do not disable SteamOS's
read-only system partition to install a compiler; use a separate development
machine or development container.

On Ubuntu 24.04, install the non-Qt dependencies below, then install the Qt 6.8.3
Linux desktop SDK with the Qt installer and export `CMAKE_PREFIX_PATH` to its
`gcc_64` directory. Ubuntu 24.04's system Qt is too old for this launcher.
The CI uses the same Qt version.

```sh
sudo apt-get install git python3 clang cmake ninja-build pkg-config \
  libsdl2-dev \
  libgl1-mesa-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev \
  libxi-dev libasound2-dev
export CMAKE_PREFIX_PATH="$HOME/Qt/6.8.3/gcc_64"
bash build.sh --stages tools,launcher
bash build.sh --discs "/path/to/your/game.iso"
./data/build-linux/launcher/gow-launcher
```

The launcher finds the checkout above its build directory. Its Install tab uses
the same Linux pipeline and writes the selected game build directory to
`data/build-root-linux.txt`. Keep the checkout and prepared discs in place;
copying only the launcher binary is not a portable distribution. Linux paths
are case-sensitive. Prepare discs on Linux instead of reusing Windows absolute
paths from `languages.json`.

`--jobs N` overrides the automatic CPU/RAM bound. Low-memory machines may need
`--jobs 1`; monitor disk and memory during generation and linking. A first build
downloads the pinned runtime and its CMake dependencies. The checkout lock
prevents concurrent pipeline writers. Cancel signals only that pipeline's
private process group. Do not build the same checkout simultaneously through
Windows and a network/WSL mount: cross-OS filesystem locking is not supported.

Supported stages: `tools,fetch,discs,vu1disc,configure,recomp,sync,build,native,
launcher,runtime-check,xdelta`. `tools` checks system programs; it does not
download Windows toolchains or install packages. `runtime-check` builds the
runtime library without an ISO. `native` rebuilds captured VU1 code. The existing
System V x64 JIT remains available while playing. Linux does not yet implement
the Windows automated recording/IOP training, PGO, release packaging, or binary
updater. First-play training and PGO controls are hidden on Linux; these stages
are rejected rather than silently treated as completed.

## Graphics, controls and Steam Deck

The runtime retains its existing OpenGL/GLFW Linux rendering path, portable
x86-64-v2 baseline, audio backend and System V JIT. This integration does not
replace the renderer with Vulkan. Driver-dependent rendering and shared-context
behavior still need validation on Mesa AMD/Intel and NVIDIA.

SDL2 handles launcher controller detection, button capture and reconnects on
Linux, preserving the game's raylib button codes. Gameplay input still uses the
runtime's raylib backend. Steam Input can present a gamepad; select a gamepad
layout and map an extra button to F1 for the in-game menu. The launcher is still
primarily a mouse/touch UI: full gamepad-only navigation is not implemented.

On a Steam Deck with a compatible development build and dependencies, add
`data/build-linux/launcher/gow-launcher` as a non-Steam game and set its working
directory to the checkout. Use the native Linux executable, then test in both
Desktop and Gaming Mode. A build from another distribution is not automatically
ABI-compatible with SteamOS. A distributable package needs a selected
[Steam Linux Runtime](https://partner.steamgames.com/doc/store/application/platforms/linux)
baseline and dependency packaging; that work remains outstanding.

## Acceptance before publishing

Run `python3 -I tools/test/pipeline_tests.py` and
`python3 -I tools/test/linux_pipeline_tests.py`. The Linux CI workflow additionally
compiles the launcher and runtime library without a disc; this alone does not
validate the generated game or GPU output.

On each actual target, complete installation from a legally obtained compatible
disc, launch visible gameplay with sound, verify movies, HUD and textures, test
Steam Input/reconnects, F1, saves/restore, diagnostics export, cancellation, and
suspend/resume. Measure guest-frame pacing and first-visit stalls at the profile's
frame PC with `GOW_PERF_DIAG=frames`; do not compare presentation Hz to guest FPS.
Record OS, GPU/driver, settings and results in `docs/tested-hardware.md`. Steam Deck
LCD/OLED, desktop AMD/Intel and NVIDIA are separate unvalidated targets until
those checks pass. No 60 FPS claim follows from a successful compilation.
