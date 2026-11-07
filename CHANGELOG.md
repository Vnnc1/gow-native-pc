# Changelog

**English** · [Português (Brasil)](CHANGELOG.pt-BR.md)

What changed from one release to the next. Release notes on GitHub are the same text with download and install
instructions; runtime patches are listed one by one in [`engine/README.md`](engine/README.md).

## Versioning

Versions are `0.MINOR.PATCH` ([Semantic Versioning](https://semver.org/) for a project that is not finished yet):

- **MINOR** (0.**4**.0) goes up for a release with new features or performance work. It may ask you to rebuild the game.
- **PATCH** (0.3.**1**) goes up for a release with bug fixes only.
- **1.0.0** is reserved for the complete port: the whole game playable at a locked 60 fps, with no known blocking bugs.

The tag of a release is `v` + its version, and the launcher inside it reports the same version: the launcher's
update check compares the two.

**Renumbering (2026-10-31).** The first releases were tagged v1.0.0, v2.0.0, v3.0.0 and v3.0.1 while their titles
said v0.0.x. They are now v0.1.0, v0.2.0, v0.3.0 and v0.3.1, with the same files and contents. A launcher from those
releases (it reports 1.0.0 to 3.0.1) does not see 0.x releases as newer: **install v0.4.0 once from its setup over the
existing installation**; automatic updates work again from there on. Your game build, discs and saves are kept.

## [Unreleased]

- **PR 26 integrated onto fix-chore.** The contributor's renderer work is in: one persistent vertex ring, primitive
  runs, texture-reuse by content hash, one depth buffer per ZBP, cached GL prelude, warm CLUT shader, frame-pacing
  percentiles and spike attribution. Also in: internal resolution below 1x (0.25-4) for integrated GPUs, effect
  switches (shadows, additive effects, texture filtering), a Mods tab with VFS overrides and declarative data
  patches, and a software rasterizer fallback for GPUs without OpenGL 4.3. Every fix-chore fix and test is kept.
- Fixed while integrating: single primitives were dropped by the threaded queue when grouping was off. The
  vertex ring now uses per-segment fences instead of a full GPU wait on every wrap. `glBufferStorage` is used
  below OpenGL 4.4 only when the driver lists it. The installer manifest is back (no elevation prompt), and so is
  the `.gitattributes` rule that keeps runtime patches applying on Windows clones.
- Performance on weaker PCs is not yet measured on this branch: see `docs/research/pr26-integration.md`.

## [v0.5.0] — 2026-11-02

### Added
- **Experimental Linux distribution:** native launcher and diagnostic helper, Linux build pipeline, verified source/binary
  archive and self-extracting `.run` installer. Intended for testing on Linux devices and Steam Deck; compiled and
  smoke-tested in Ubuntu 26.04 WSL. Uses host libraries; SteamOS, real Deck hardware and performance are not validated.
- **CHD import for recompilation:** supported CHDv5 images are verified and converted to a cached ISO, then pass the
  same executable compatibility checks as ISO imports. Extra disk space is required; source images remain read-only.
- **Regions:** USA and the tested USA-identical Asia disc; isolated Japan `SLPM_670.10` and Europe `SCES_531.33`
  Windows builds validated through opening ship gameplay. The launcher selects matching registered builds and keeps
  their saves separate. A fresh installation does not automatically compile foreign-code discs with the USA pipeline.
  Other serials and whole-campaign compatibility remain unvalidated; demos are excluded.
- **Accessibility page:** texture packs and input assistance now have a dedicated page. Existing PCSX2-format PNG
  replacements can customize the visuals; no packs are distributed with the project.
- **Keyboard stick assistance:** optional held shake/rotate binding (G by default), with release/focus-loss handling
  and no changes to connected gamepads. Shoulder-button repetition (L1/L2/R1/R2) is individually opt-in.
- **ISO mods:** verified xdelta/VCDIFF application to a separate output image, preserving the source disc.

### Fixed
- **Cutscene audio:** stale packets from a previous movie no longer corrupt the next movie's channel alignment and
  PT-BR voices (patch 54). The measured PT-BR scene now matches its source audio within rounding error; USA remains
  unchanged. Earlier disappearing-sound-effect fixes are retained. This does not certify every movie or transition.
- **Held keyboard chords:** Ctrl + Space and Ctrl + WASD retain their gameplay buttons; default evade moves to Alt +
  WASD. QTE repetition pauses during chords to avoid interrupting held actions (patches 57–58).
- **Linux startup:** prepared discs include lowercase IOP-module aliases for case-sensitive paths. The diagnostic
  helper now records Linux process CPU/RSS, with platform-correct crash tests.

### Build and performance
- Native IOP modules compile in parallel parts (patch 55). On the recorded Xeon/Clang build, the longest unit fell
  from **126.5 s to 24.5 s**; this is not the complete installation time or a cross-machine benchmark.
- Further compilation-time reductions and better performance on slower PCs remain goals toward v1.0.0, without a
  promised date or duration. Existing VU1/PGO improvements remain; recorded results do not establish locked 60 FPS
  on every mid-range computer or across the full game. See [hardware evidence](docs/tested-hardware.md).
- The v0.5.0 Windows package ships **without a pre-trained PGO profile**; local training remains available.

### Graphics and remaining limits
- Existing internal scaling, sharp filtering, FXAA, anisotropic filtering and borderless external-tool mode remain
  available. **DLSS, including DLSS 5, is not integrated**; external scaling/frame generation is not native DLSS support.
- Transparent enemies were reproduced with a replacement pack; pack data versus renderer handling has not been
  isolated. No blanket alpha correction is included.
- Linux tests reached initial gameplay with software rendering in WSL. Steam Input, suspend/resume, hardware GPU
  performance and Japan/Europe Linux builds still need validation. See [Linux instructions](docs/linux.md) and
  [disc compatibility](docs/disc-import.md).

## [v0.4.0] — 2026-10-31

Changes since v0.3.1 on the development branch.

### Added
- **Fast VU mode** (off by default; Launcher → Performance): VU1 code without the exact float clean-ups, like PCSX2's
  default settings. About 12% less VU1 work in combat; rare small differences from the exact mode (patch 51).
- **Hold instead of mashing** (accessibility, off by default; Launcher → Controls): in the minigames that ask for
  repeated presses, holding the button presses it for you; a short press stays a single press. By
  [ThisIsAkill](https://github.com/ThisIsAkill) (PR #10, patch 53).
- **Launcher in French, German, Italian, Russian and Simplified Chinese**, besides English, Portuguese, Spanish and
  Turkish; the system's language is picked on first start. The in-game F1 menu stays in English for these.
- Releases can ship a profile-guided optimisation (PGO) profile trained on exactly their runtime and patch set.
- `tools/pipeline/patches.ps1`: the runtime patch stack as git commits, to move it to a newer runtime commit.

### Performance
- The VU1 interpreter's debug and recording paths no longer reserve large stack frames on every VU1 program (patch 50).

### Fixed
- **Frozen pink screen when the GPU renderer cannot start** (no OpenGL 4.3: an old GPU, the Microsoft Basic Display
  Adapter, Remote Desktop; or a driver that rejects the shaders): the window now says why and what to do (patch 52).
- **"The term ...\build.ps1 is not recognized" during install**: an antivirus had removed the pipeline script while it
  started. The launcher now says that a file was removed and how to restore it, instead of "Failed (code 1)".
- **Sound effects going silent in long fights**: released voices now fade to zero and free their slot; before, the
  effects voices filled up after about 35 s of combat and hits went silent until an area change (patch 48).
- **Install failed in a folder whose name has a space** (for example `E:\God of War`): the path of the PGO profile was
  cut at the first space and every compile failed ("sccache: Failed to open file for hashing").
- Running the setup over an earlier version now asks for a game rebuild when the runtime patches changed, as launcher
  updates already did.

## [v0.3.1] — 2026-10-31

Formerly v3.0.1. 7 commits since v0.3.0.

### Performance
Measured on the test PC (Xeon E5-2666 v3 + RX 580, full screen, save route, alternating pairs).
- Leaner generated VU1 code, bit-identical results: average about 51 → **57 fps**, heavy combat about 51 → **55 fps**
  (patch 43).
- Lock-free hand-off to the GS stage thread: about 150,000 fewer thread wake-ups per second, combat +3.5% (patch 44).
- VU1 decode on demand and one copy less per GIF packet, from the
  [gow-native-pc-optimization](https://github.com/huanghuangdaquan-beep/gow-native-pc-optimization) fork (patches 45–46).

### Added
- The installer checks for SSE4.2 and tells unsupported CPUs before installing.
- CPUs with 4 threads or fewer install without the profile-guided pass (it can be run later) and with one more
  compiler in parallel.

### Fixed
- GPUs whose drivers stop at OpenGL 4.3–4.5 (Intel HD 4000–4600 and others) use the GPU renderer instead of the much
  slower software one (patch 47).
- Dependencies are downloaded once and without history: the profile-guided step no longer downloads ~1 GB again.
- The "rebuild" notice clears only after a rebuild with the new runtime; after an update the launcher recommends
  training the profile again.

## [v0.3.0] — 2026-10-31

Formerly v3.0.0. 28 commits since v0.2.0.

### Performance
Measured on the test PC (full screen 1080p, 2× internal resolution).
- Heaviest ship combat about 40 → **50–53 fps**; ship average about 55 fps.
- **Early FINISH**: the game prepares the next frame while the VU1 draws the current one, about +20% in heavy combat.
- **Profile-guided optimisation is part of the install** (stage `tune`): about +5% average, +13% in combat.
- **VU1 x86-64 JIT**: areas without recorded VU1 code are compiled while playing (patches 18, 27).
- Leaner JAL/JALR calls and memory fast paths (patches 28–35).

### Added
- In-game **F1 menu**: live Graphics tab, Cheats tab (F2), Save tab; runtime debugger moved to Ctrl+F1.
- Launcher: graphics profiles (Performance / Balanced / Quality), borderless fullscreen, an "Upscaling and tools"
  section, Saves page, PGO status, session reports for bug reports.
- First-play preparation + PGO in about 24 minutes instead of about 63; `build.cmd -Stages verify` regression tests.

### Fixed
- Memory/DMA correctness, SPU2 audio mix overflow, standalone game launch, widescreen movie placeholders.
- FXAA no longer turns off the sharp scaler; settings that did nothing were removed.

## [v0.2.0] — 2026-10-25

Formerly v2.0.0 (its launcher reports 2.1.0). 15 commits since v0.1.0.

### Added
- **clang (llvm-mingw) is the compiler**: the game builds in about 15 minutes instead of 45–60 with MSVC; Visual
  Studio, Git and Python are no longer needed.
- **Install in three steps**: portable tools → ISO → install. New loading screen with one progress bar and time left.
- Controller remapping button by button (patch 14), 32:9 aspect ratio.
- **Launcher updates from GitHub Releases.**
- Optional profile-guided optimisation (Install → More options).

### Performance
- Scripted ship combat: minimum 51.4 → 54.6 fps, average 56.5 → 58.4 fps (clang + PGO).
- VU1 without needless float clean-ups and with chained blocks (patches 10, 13); sound mixed in batches; the IOP heap
  reuses freed memory (patch 11).

### Fixed
- Builds from USB / exFAT drives; the Python check; the launcher reads the game path again after a build.

## [v0.1.0] — 2026-10-25

Formerly v1.0.0. 12 commits: the first release.

### Added
- Build pipeline with per-game profiles, one-file setup (no administrator rights) with uninstaller, launcher.
- Fan translations accepted by language, with a language choice when several ISOs are added.
- Anisotropic filtering option.

### Performance
- Scripted ship combat with the default settings: average about 48 → 58 fps (every VU1 block as native code, cheap VU1
  recording, faster sound mixing, "register locals" code generation, patches 08–09).

### Fixed
- Image fixes at higher internal resolutions from the God of War II native port; MOVZ/MOVN translation; runtime memory
  out of the game's heap; FMV audio streams; faster memory card saves; runtime patches keep their line endings.

[v0.5.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.5.0
[v0.4.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.4.0
[v0.3.1]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.3.1
[v0.3.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.3.0
[v0.2.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.2.0
[v0.1.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.1.0
