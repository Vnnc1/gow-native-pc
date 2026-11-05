# Post-intro black-screen isolation

Follow-up to [the supplied Intel report](chin-delivery-followup-2026-11-04.md).
Requested 2026-11-04: test normal/skip-video startup and correct a demonstrated
cause while preserving working paths. This record distinguishes actual execution
from hypotheses; a missing reproduction is not a fixed defect.

## Identity and isolation

The registered Japanese runner `C:/gow-region-japan/ps2xRuntime/ps2EntryRunner.exe`
is absent. The prepared ELF and generated regional source snapshot remain under
`D:/gow-regions/japan/`. ELF SHA-256 is exactly the supplied report's
`e9018f431ad7046fbb73af802efb0e432ab9d0947720d959afc129fb97fa36e6`.
Build the preserved snapshot, without modifying its sources, into the new short
directory `C:/gow-black-jpn`. Do not register this as a released regional build
or change the normal launcher's build-root marker.

The local hardware is Xeon E5-2666 v3 / RX580 2048SP, not the reported i3-4170 /
HD 4400. The reported runner `fac532bd…a69f8` is unavailable. This new regional
baseline is not a byte-identical reproduction of that executable or the latest
USA branch. `MPEG.cpp` is nevertheless byte-identical across the preserved
regional snapshot, supplied delivery and current runtime (SHA-256
`ecf09bf1a4d1a354db78d5edc82a90005e750bfb0c7f636366c512274fc733b2`).
The GS backend differs across those three sources.

Build uses pinned llvm-mingw, Release -O3, portable x86-64-v2, no PGO or ThinLTO,
unity batch 16 and ten jobs. Dependencies are reused as source from the existing
separate build, with independent binary directories. No compiler runs during
gameplay tests. Private cards, captures and reports remain under ignored data.

`tools/test/regional-overlays.py` failed the existing source-baseline gate for
`src/gow_overrides.cpp` in both regions: the archived overlays no longer match
the current USA source. Do not bypass the gate or apply them to current sources.
This test uses the already-relocated historical snapshot instead. The failed
check is preserved in `data/experiments/black-intro/region-check.log`.

## Method

`session-game-smoke.py --normal-boot` tests ordinary startup. The new independent
`--skip-fmv` option changes only movie skipping, leaving fast boot disabled.
`--movie-diag` enables existing movie-state instrumentation. Reports now record
runner/ELF hashes and effective skipping, avoiding a comparison that accidentally
changes both startup and movie behavior. These are correctness tests, not FPS
benchmarks. Both variants use Japanese Circle menu confirmation, visible output,
audio, 1x scale, the same early-FINISH setting and a bounded duration.

No result or runtime correction is claimed by this method description. Completed
run evidence and any limitations are appended below.

## Executed normal-video test

Build completed successfully (558-step Ninja plan). Rebuilt runner SHA-256:
`86958a56d939b31d3fc184cdda268ff423a2ec74dc21df48d2b032c9da436764`.
The maintainer confirmed that they do not have the affected executable or another
reproduction available. Do not imply a binary-matched test against `fac532bd…`.

Normal-video test: `data/gow1/logs/session-game-20261104-214847`, 150 seconds,
visible 1280x720, 1x, host cap 120, audio and early FINISH enabled. Japanese
Circle inputs at 12/18/24/30/36 seconds, Start at 5 seconds, with the same later
gameplay inputs used for the skip control. Fast boot is disabled.

- `Semo01` loaded at elapsed 30.028 seconds. Movie-state counters continued
  advancing during playback. Nine complete windows at 47.364–87.371 seconds
  reported zero guest flips while host presentation remained about 120 Hz.
- Gameplay began at elapsed 89.934 seconds (79.53 on the pad-test clock).
  The capture at elapsed 90.432 seconds reports state=11, levelReady=1, movie=0;
  visual inspection shows Kratos, the ship and scenery. No persistent black
  screen reproduced on this machine/build.
- All 11 existing smoke gates passed, including 2000 VU1 parity checks, metrics,
  gameplay marker, exit zero and graceful stop. The audio gate checks metric
  presence, not uninterrupted audio: 19,406 missing audio frames were recorded
  in the startup window and 5,686 in the window spanning the movie/game transition;
  no dropped frames were reported. Do not describe this as flawless audio.

**New interpretation constraint:** a zero guest-frame probe during FMV can be
normal even when playback progresses and gameplay later starts successfully.
The supplied log's zero windows cannot independently distinguish this behavior
from its reported black screen. This strengthens the need for movie-state and
image evidence on the affected hardware; it does not dismiss the user's symptom.

Build/configure/source-identity logs: `data/experiments/black-intro/`.

## Skip-video test and shutdown failure

The matching 150-second skip control is
`data/gow1/logs/session-game-20261104-215129`. `Semo01` was skipped at elapsed
30.114 seconds, its start request at 41.998 seconds, and gameplay began at
42.097 seconds. The 90.498-second capture shows Kratos and several enemies in
combat, state=11, levelReady=1, movie=0. No post-intro black screen was reproduced.

This run is **not a fully passing smoke**: nine gates passed, but exit-zero and
graceful-stop failed. The collector requested stop at 150.174 seconds and killed
its own child at 155.202 seconds, then recorded exit 62097. Guest-frame and audio
activity continued after the stop request. This is a separate unresolved close/
presentation/shutdown issue in the historical regional build, not evidence of
the reported intro failure. Do not weaken the exit gate or silently extend the
collector deadline. Audio had 18,926 missing frames in its startup window and
zero drops. All 2000 VU1 comparisons passed.

A 100-second skip follow-up uses the same settings to check termination at an
earlier point; it must not erase the failed 150-second run or count as an FPS pair.

That follow-up (`session-game-20261104-215430`) completed: gameplay began at
elapsed 42.004 seconds; all 11 checks passed, stop was requested at 100.311 seconds
and exit zero recorded at 100.492 seconds. The first long-run shutdown failure
remains unresolved; one successful earlier close does not fix or disprove it.
Machine-readable results for all three sessions are in
`data/experiments/black-intro/results.json`.

## Decision and remaining limitation

No black-screen cause was reproduced or corrected. Do not ship a speculative
renderer, movie-clock, timeout or forced-skip change on this evidence. The only
tracked code change is the diagnostic smoke harness: independently controlled
FMV skipping, optional movie diagnostics, explicit host cap and binary identities.
Actual normal/skip executions validate these options; `git diff --check` passed.
The recorded regional source hashes are unchanged, no game process remains,
and the normal launcher still points to `C:/gow-q59`.

Further root-cause work requires the affected environment or equivalent evidence:
actual runner identity, movie progress and final state during the black screen,
and host/GS image distinction. Preserve the successful path and the independent
shutdown/audio failures. Neither RX580 success nor the initial-build comparison
establishes a fix for older notebooks.
