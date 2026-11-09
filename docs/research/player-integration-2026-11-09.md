# Player integration work — 2026-11-09

Maintainer-approved order on `fix-chore`:

1. Setup build-location choice for new installations and updates/location changes.
2. Automatic backup history after a confirmed altar save, listed by the launcher,
   with an in-game notification that the launcher backup was also saved.
3. Gameplay/QTE/tutorial prompts follow the last active device (Xbox, DualShock 4,
   DualSense, mapped keyboard/mouse), including remapped bindings.
4. Controls, graphics and audio in the in-game menu; cheats live only in their
   own in-game tab, with a master enable and individual selections.

## Build location

Implemented in `installer/setup.cpp`: a separate native, keyboard-focusable
build-folder selector, with English/Portuguese/Spanish text, and `/BUILDROOT=`
for unattended installs. Updates without a new choice retain the recorded root.
The diagnostic installer does not expose a compilation folder: its runner is
already packaged. The normal install persists UTF-8 `data/build-root.txt`
atomically. The existing launcher/pipeline compiler/configuration suffixes
(`-clang`, `-dev-clang`, etc.) remain unchanged and the UI explains them.

A changed build location requires rebuilding: CMake/Ninja caches contain absolute
paths and must not be copied as if relocatable. Setup marks `needs-rebuild` and
`pgo-stale`, preserves the previous build and all player data, and selects the
new location for the next build. It does not silently delete the old build or
move discs/cards. New locations must be short local absolute paths (40 characters
maximum), distinct from the installation tree and drive root. Existing recorded
long paths may be retained. Unrelated/nonempty and foreign-cache locations are
rejected before unpacking. Cache ownership compares the exact runtime CMake
source, not a prefix (which could match a different sibling checkout).

Pipeline collision fallback now stays beside the selected base instead of
switching back to `C:\gow-build`. Explicit roots are persisted; UTF-8 roots are
read correctly by Windows PowerShell 5.1. The fallback's own ownership is checked
before use. No configure/build ownership gate was removed.

### Validation

- Normal and isolated-test-identity Win32 installers built with pinned LLVM 20261020.
- `setup-build-location.py`: real packed synthetic installation, location change
  with Unicode, update retention, rebuild markers, rejection of foreign prefix
  caches/invalid paths, preservation of fake save/old-build content and owned-only
  purge passed.
  This uses `GOW_SETUP_TEST_IDENTITY=ON`, its own registration/shortcuts, and a
  verified new scratch root; it never installs over the user's game.
- `build-root-tests.ps1`: production selection block, custom-location collision,
  explicit persistence and UTF-8 reuse passed. The first harness attempted a
  PowerShell-only drive that .NET cannot resolve; it was corrected to use real
  filesystem paths. No claim of a physical cross-drive copy is made.
- Python pipeline suite: 17 passed. Linux pipeline suite: 7 tests, one skipped
  on Windows. PowerShell pipeline suite passed, including the new root checks.
- Final package stage rebuilt staging from current sources; packed normal payload
  verification passed: 1,718 files / 7 LZMS blocks / 102,612,926 bytes matched staging.
  The staged pipeline root selector also matched the working source byte-for-byte.
  Screenshot inspected at the desktop's DPI: both install and
  build paths, change controls and rebuild/preservation notice were visible.

Evidence: ignored `data/setup-build-location`. No installer was publicly released.
Packed artifact hashes and payload verification are recorded in `payload-verify.log`.
The extended purge test first exposed that the old uninstaller decoded the root
as ASCII and omitted `-clang` folders. The corrected UTF-8 reader and owned suffix
enumeration passed the rerun; unrelated and previous builds remained intact.
Moving a compiled cache without rebuilding is intentionally unsupported; old
build disk space remains until the player removes it after verifying the new build.

## Automatic altar backups

Implemented separately in patch `zzz-309`, with launcher history refresh and
localized automatic-source labels. The USA game uses EE libmc2 over DBCMAN,
not the generic MCSERV file-close path considered below. Its final successful
index write is the completion gate. See [implementation, tests and limitations](altar-save-backups-2026-11-09.md).

## Remaining work

Device-dependent USA Flash button prompts are implemented in `zzz-310`; see
[validation and remaining acceptance](control-prompts-2026-11-09.md). Physical
controller checks, combat QTE acceptance and non-Flash world prompts remain open.
Follow-up `zzz-311` removes the original PS2 button art behind recognized mapped
prompts; private-card altar and remapped Moves captures validate that correction.
The in-game settings/cheat changes remain an authorized next step.

Initial save-path investigation (superseded by the traced libmc2 path above): the interpreter persists and flushes individual
card ranges in `ps2xIOP/src/emulator/core/memory_card.cpp`; these writes are not a
completed game-save signal. `IopRpcBridge::handleRpc` executes the memory-card
server and copies its reply back to EE RAM. The EE RPC completion path is therefore
a candidate for observing successful write/close results, but a file close alone
still needs correlation with the game's multi-file save sequence. The existing
manual `snapshotCard` helper in `ps2_debug_panel.cpp` also needs its rename and
metadata-write errors checked before it can issue an automatic success notice.
The setup change alone did not ship a save hook; `zzz-309` implements it separately.
