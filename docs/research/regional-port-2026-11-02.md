# Regional port validation, 2026-11-02

Europe and Japan now have independently compiled Windows runners that reached
visible ship gameplay. This is initial-level validation, not whole-game support.
The production Asia/USA installation remains unchanged. The launcher now selects
these separately registered builds and recognizes matching ISOs as playable.
Fresh regional compilation is still a separate procedure.

## Exact identities and builds

| Region | ELF | CRC | .text SHA-1 | Frame probe |
| --- | --- | --- | --- | --- |
| Asia / USA | SCUS_973.99 | D6385328 | 8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00 | 0x1837B8 |
| Europe | SCES_531.33 | FB0E6D72 | 706831f2064ca73bf83d3cff4e02764fa26bfff1 | 0x1838A8 |
| Japan | SLPM_670.10 | CA052D22 | 8ed48ca88c73e7e340be3a8e7ff16b07825cb96c | 0x183BB8 |

The supplied Asia and USA complete ELFs are identical; the ISOs differ in layout.
Asia was prepared from its own disc. The regional identities above apply only to
these measured images, not alternate serials or demos.

Local runnable files:

- Europe: `C:/gow-region-europe/ps2xRuntime/ps2EntryRunner.exe`
- Japan: `C:/gow-region-japan/ps2xRuntime/ps2EntryRunner.exe`

Each has a `gow-native.boot` for direct launch with its own prepared disc under
`D:/gow-regions/<region>/disc`, card `D:/gow-regions/<region>/Mcd001.ps2`, and
save backups under `D:/gow-regions/<region>/saves`. No scripted input, fast-boot
or FMV skipping is enabled in these delivered boot profiles. Japan confirms
menus with Circle; Europe uses Cross. Keep these disc directories in place.

Builds use the pinned llvm-mingw, Release -O3, portable x86-64-v2 and the in-process
VU1 JIT. No USA PGO profile or USA recompiled code was reused. Runtime sources
are isolated under `D:/gow-regions/<region>/runtime`; the original production
runner, language manifest and build-root marker retain their recorded SHA-256.

## Fixes and address evidence

Initial automatic discovery decoded embedded data as instructions and returned
exit zero despite errors. The pipeline now rejects error-bearing compiler reports.
Bounded function maps contain 6410 Europe and 6416 Japan ranges. Shape matches,
neighbor anchors, paired data references and direct call targets supplied
relocation candidates; normalized shapes alone are not proof of equivalence.

Regional overrides use separate code/data mappings, not a single displacement.
Movie load entries were checked at Europe 0x1891F0 / Japan 0x189500, with movie
objects at 0x306E98 / 0x303898 and status fields at +0x80/+0x84. Frame probes are
listed above. SDK stubs were relocated for each generated executable.

The magenta Europe boot was caused by missing dispatch entries, first the
constructor at 0x29C7B8, later a code-constructed callback at 0x1D4EA8. Adding
data- and code-referenced entry hints fixed those failures without changing guest
instructions. Europe has 4093 hints; Japan has 4020. Generated headers must be
updated in both include and runner directories. Separately, disc normalization
created required IOP_MOD aliases; missing modules had caused silent HLE/stalling.

Source overlays and generation metadata are versioned under
`games/gow1/regions`; its README documents reproduction and baseline checks.
Generated game code, ELFs, screenshots and local compiler output remain ignored.

## Executed tests

Hardware: Windows, Xeon E5-2666 v3, RX 580 2048SP, 16 GiB RAM. All tests used
private test cards and the deployed independent session collector.

| Region | Mode | Duration | Log under data/gow1/logs | Checks |
| --- | --- | --- | --- | --- |
| Europe | fast boot | 100 s | session-game-20261102-162750 | 11/11 |
| Japan | fast boot, Circle menu input | 100 s | session-game-20261102-163236 | 11/11 |
| Europe | normal startup / FMVs enabled | 150 s | session-game-20261102-163440 | 11/11 |
| Japan | normal startup / FMVs enabled | 150 s | session-game-20261102-163753 | 11/11 |

Checks cover exit status, state=11/levelReady=1 gameplay, 2000 VU1 comparisons
with zero mismatches, guest-frame distribution, memory/audio/IOP/native/JIT
metrics, marker handling and graceful shutdown. GS captures confirmed the ship,
Kratos, enemies and HUD in both regions. Audio was enabled and its metrics were
present; this does not replace subjective listening across the game.

Re-run with `tools/test/session-game-smoke.py --visible --capture --normal-boot
--seconds 150 --runner <regional runner> --elf <prepared ELF> --frame-pc <table PC>`.
For Japan, pass `--pad-script` with the profile's 12/18/24/30/36-second `x`
menu presses replaced by `circulo`; retain later X presses for jumping.

Both delivered no-argument executables also passed a separate startup check:
their own boot profiles were read, the processes remained alive, and each closed
gracefully. Shortcuts are under `D:/gow-regions/God of War - <region>.lnk`.

Final regression: `build.cmd -Stages verify` completed with BUILD OK, including
10 CTest cases, guest-call parity, VU1 backend equivalence and isolated task
replay. A first attempt encountered a transient Windows access-denied error
renaming a temporary test directory; the unchanged rerun passed. Standalone
pipeline tests passed 17/17, Linux orchestration passed 6 with one POSIX-only
skip, and `regional-overlays.py` passed both regional subtests. These checks do
not broaden the regional gameplay coverage beyond the sessions above.

## Launcher integration and regression audit

The registered region selector now routes runner, ELF, frame probe and private
card/save paths together. The real ISOs were identified through the compiled
launcher backend: Europe/Japan returned `playable=true` with their regional
selection keys, while Asia retained the existing USA-compatible path. Foreign
discs never enter USA recompilation. The main rebuild button explicitly names
USA/Asia when regional builds are present; regional automatic AOT/PGO is disabled.

Regional play keeps JIT enabled but disables unused VU1 capture files. Recording
them would add disk work without a regional launcher AOT rebuild path. USA capture
and rendering settings are unchanged. Hashing installed binaries is cached by file
metadata and occurs during selection/startup, never on the game's frame loop.
The Saves list refreshes on region changes; missing regional builds do not silently
fall back to the USA card. Both runtime and launcher backups use the same private card.

Integrity audit (`data/region-validation/integrity-audit.json`):

- Original USA/Asia runner, language manifest and build-root hashes still match.
- 139 non-overlaid runtime source files per region match the original after newline
  normalization, including all 16 inspected GS/display/texture-store files.
- The complete TOC and 16 evenly spaced 1 MiB samples of each PAK match each
  source ISO for Asia, Europe and Japan; sizes also match. This is sampled PAK
  validation, not a complete media checksum or whole-game texture validation.

Additional visible, private-card gameplay tests:

| Region | Settings | Session under data/gow1/logs | Result |
| --- | --- | --- | --- |
| Asia / USA | 1x | session-game-20261102-165959 | 11/11, ship combat captured |
| Japan | 2x, FXAA, early FINISH | session-game-20261102-171037 | 11/11, ship combat captured |
| Europe | 2x, FXAA, early FINISH | session-game-20261102-171427 | 11/11, ship combat captured |

Each run lasted 100 seconds. The first Asia attempt (`165557`) stayed at the
menu; a repeat with longer scripted confirm holds reached gameplay. Its binary
hash was unchanged throughout. These are functional tests, not controlled A/B
performance measurements; some verification/build work overlapped the Asia repeat.
No new FPS regression conclusion is drawn from those runs. The regions still lack
USA's PGO training; equal performance across editions is not established.

Checks passed: 17 pipeline tests, 4 registration tests, the Qt regional registry
test, real Main.qml play/save routing, InstallPage import gating, language keys,
6 memory/QTE CTests, and disc import tests (8 passed, 6 optional real-CHD checks
skipped). Launcher build succeeded and was deployed. Screenshots confirmed all
three edition selectors in the compiled launcher. Desktop click automation failed
with `coordinate input geometry is unavailable`; the real QML handlers were
therefore exercised with mocked children, while games were tested separately.

## Remaining limits

- Full campaign, save-altar save/load, all European language choices and every
  keyboard/mouse QTE have not been validated in these regional builds.
- Optional host target-lock assistance is disabled because its camera heap
  allocation is unvalidated. Original game targeting remains available.
- Diagnostic GOW_WARP and enhanced host widescreen patches are not validated;
  do not enable them. The normal game's own display settings remain separate.
- These functional tests establish neither stable 60 FPS nor Linux/Steam Deck
  compatibility. Regional builds are selectable in the launcher, but rebuilding
  and updating them still requires the isolated procedure and re-registration.
