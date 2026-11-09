# Updating the player test installation â€” 2026-11-09

Target: `C:/Users/dzvini/Documents/gow-test`; owned Release build:
`C:/gow-build-clang`. The normal launcher inspection resolves the existing
Portuguese translation and that runner. No cache ownership checks were bypassed.
The source is the current `fix-chore` working tree, including uncommitted
`zzz-312`/`zzz-313` and their tests. This is a local test deployment, not a release.

## Preservation and scope

Backup: `C:/Users/dzvini/Documents/gow-test-backup-20261109-162041`.
It contains the former launcher deployment, runner, overwritten source files,
all saved-card history and the current card, plus an export of launcher registry
settings. Discs and player preferences are retained in their existing locations.
443 source/package files were refreshed, and the launcher/collector were rebuilt
and deployed with Qt dependencies. The game uses the regular
`fetch,configure,recomp,sync,build` pipeline against the target installation.
The old runtime was only through patch 58; the full current chain ends at 313.
The old PGO profile is preserved but rejected by the current identity check;
this functional test build is Release without stale PGO data.

## Integration defect found

A clean indexed application of the chain failed at `zzz-310`: two existing
Spanish comment context lines in `gow_integracion.cpp` had mojibake. Restoring
those two context lines to upstream UTF-8 makes the patch apply without changing
its executable behavior. The corrected chain through 313 applied to the actual
installation. Do not infer clean-chain reproducibility from a manually prepared
scratch runtime alone.

## Checks

- Deployed collector: 14 tests passed.
- Pipeline: 17 tests passed.
- Target runtime: altar-backup, movie EOF/tail and control-prompt production
  suites passed, including mappings, QTE input modes and world projection.
- Target launcher environment contract passed. An initial invocation against the
  unrelated development runtime failed its reader checks; it does not describe
  the target full-chain runtime. Both logs are retained.
- Launcher `--inspect-installation` returned the existing PT-BR edition and
  `C:/gow-build-clang/ps2xRuntime/ps2EntryRunner.exe`.
- Launcher build passed. CTest in that launcher build defines no tests; it is
  not counted as a passing test suite.
- Seven protected save/history files and the launcher registry export remained
  byte-identical after deployment and read-only inspection.

Build completion, runner identity and private-card smoke results are recorded
below after validation. Real combat QTE acceptance remains with the maintainer.
Local logs and preservation manifest: `data/deployment-fix-chore/`.

## Completed deployment

The full target pipeline completed successfully. The runner's CMake source root
is the installed runtime; Release flags use x86-64-v2, without stale PGO.
The owned runner copy of `gow_overrides.cpp` is byte-identical to the profile's
runtime source after sync.

Final binary SHA-256 values:

- `C:/gow-build-clang/ps2xRuntime/ps2EntryRunner.exe`: `c78eebddefa9ab45486f685e8ecbd47db6c3af6d8718bf9e5b496044239cfc41`.
- `C:\Users\dzvini\Documents\gow-test\launcher\bin\gow-launcher.exe`: `953cd958bad725ea70b9a0b52875063484c45f64da21a87b761ce0004960a5ca`.
- `C:\Users\dzvini\Documents\gow-test\launcher\bin\gow-session.exe`: `6cba14495c4946b804ccecc1e786de5dbc5fbc39e4adb1ad4b782a16fa63647c`.

The 30-second private-card smoke passed: a host capture shows the Portuguese
title menu and the new textured Xbox A prompt. The collector reached `completed`
with exit code 0. This is startup/render/shutdown evidence, not gameplay, combat
QTE or physical-controller validation. No FPS claim is derived from this run.
All seven protected save/history files and the registry settings export were
still byte-identical after the test. Final manifest: `validated.json`; capture:
`game-smoke/host_shot.png` under the local evidence directory above.

The existing launcher shortcut can be used for manual combat testing. No game
process is left running. Setup/uninstall executables were not replaced in place;
this update targets the installed source, launcher/helper and owned game build.
