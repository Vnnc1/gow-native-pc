# 0.6.0 local test candidate — 2026-11-10

Target: `v0.6.0-rc.1`, explicitly authorized as a pre-release after the slot-3 correction and tests.
The stable v0.5.0 release and assets must remain unchanged; the pre-release must not become GitHub's latest stable release.
Base: fix-chore `f60a672`, plus the native-slot changes and release preparation in the working tree.
Fetched main `37290ba` is already an ancestor of this branch; there are no additional main commits to merge.

## Contents and installation

The [English](../../CHANGELOG.md) and [Portuguese](../../CHANGELOG.pt-BR.md) changelogs describe changes since v0.5.0.
Both launcher and Windows installer report 0.6.0. Windows setup carries the launcher, tools, runtime patches and
documentation; a matching game rebuild is required to use the new runtime features. No pre-trained PGO profile
matching this patch chain is included. User disc files, cards and private generated preview images are excluded.

Linux is an x86-64 host-library `.run` installer and archive, built on Ubuntu 26.04 WSL with Qt 6.10.2 and Clang 21.
It requires compatible Qt/QML libraries, installs into a new directory and refuses an existing destination.
This preserves an older installation but is not an in-place Linux update/migration mechanism. SteamOS/Deck and
Linux gameplay/audio performance require separate validation. See [Linux documentation](../linux.md).

## Validation record

- Native save integration: four loads, three transitions from gameplay, normal exit 0; source/private cards unchanged.
- Windows and native Linux save reader tests: 8 passed on each host. Native load wrapper contracts passed on both.
- Launcher QML slot/history refresh, regional routing, altar backups and production menu tests passed.
- Windows launcher built; isolated setup identity tests passed installation, Unicode relocation, update retention,
  foreign-build rejection and save/build preservation. LZMS payload verification matched every staged file.
- Linux native launcher and runtime library built. Initial runtime checks exposed unconditional Windows-only
  `intrin.h` includes in GS/VU1 counters; patch zzz-324 selects the compiler's x86 header without changing behavior.
- Linux: pipeline 17 tests, Linux pipeline 7, disc preparation 5 and collector 16 (2 Windows-only skips).
  Eight reader/asset tests also cover Japan RTC to UTC date conversion and invalid dates on both hosts.
  Real QML save/history refresh passed. A Qt 6.10 dialog implicit-height loop was removed with an explicit height.
- Linux installer passed member hashes, executable permissions, installation with spaces, existing-directory
  protection and damaged-payload rejection. This is installer/CPU-library validation, not Linux gameplay.
- Initial installed-build deployment preserved all 12 protected files and the complete launcher registry export.
  Manifest: `data/native-saves/deployed-final.json`. Test logs: `data/native-saves/` (private, not distributed).
- Slot-3 distorted CTRL was reproduced and fixed by zzz-325; see [cause, captures and tests](spartan-r2-prompt-2026-11-10.md).
  The final patched runtime library compiled on Windows and Linux; broader combat/controller acceptance remains open.

## Manual acceptance before a stable release

Test Windows setup on a fresh directory and as an update, including changing the build directory. Rebuild the game
when required, verify retained saves/settings, exercise four native slots, altar backup and history restore, menu
pause/persistence, control remaps and QTE assistance. Test the actual combat QTEs, Aphrodite dialogue and longer
play sessions; these are not established by unit tests. On Linux test dependency availability, launch, install,
input, audio and game compilation on the target machine. No universal 60 FPS or Steam Deck readiness claim.
