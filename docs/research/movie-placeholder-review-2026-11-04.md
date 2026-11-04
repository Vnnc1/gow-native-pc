# Movie placeholder report investigation (2026-11-04)

Investigated the maintainer-supplied report written by Claude against checkout `d28a63d` on `fix-chore`.
The attachment contains a proposed preparation diff and a subtitle feature description, but no
`59-movie-subtitles.patch`, subtitle file, binary-format specification or raw runtime logs.
Reported gameplay/FPS results below remain external claims, not local measurements.

## Confirmed preparation defect and correction

The local standalone PT-BR disc is code-compatible (`D95720D3`) and has no `PART2.PAK`.
All ten part-0 files named SEMO02, 03, 04, 05, 06, 07, 08, 09, 10 and 13 `.PSW` have size 114,692 and SHA-256
`97a80e440f6ca7d6253069629351d78984826ebb50d738832af7bc901640702a`, matching the report exactly.

`normalise()` first remaps missing part-1 entries to part-0 copies, but its subsequent movie check used the
original parsed tuple. Both placeholder recognition and replacement-size comparison could therefore inspect
the old payload. This is reproducible independently of the runtime or an audio device.

| Private-TOC experiment on the actual disc | Widescreen entries mapped | Remaining 114,692-byte entries |
| --- | ---: | ---: |
| Unmodified profile/preparation | 1 | 14 |
| Additional fingerprint only | 11 | 4 (SEMO05–08 part-1 duplicates) |
| Fingerprint plus current-entry lookup | 15 | 0 |

These counts refer to TOC entries, including duplicates, not fifteen distinct movies. The original TOC contains
713 entries moved because part 2 is absent. Source TOC SHA-256:
`75a1f0678d7638d054bbc803b613015cb0b2c59169e8ec804da1671c4b7421a1`.
The experiments use private TOCs and read-only access to linked PAK inputs; the installed TOC, ISO and saves were
not changed. Repeated normalization produces identical bytes and preserves `.orig`.

The fix adds the exact fingerprint to `games/gow1/game.toml` and rereads the current part/size/sector once in
`prepare.py`. Unlike the submitted diff, **all** size checks use the new tuple, including `size <= SECTOR`.
Three synthetic scenarios failed before the fix and pass afterward: a relocated known placeholder, an entry
formerly marked empty that now points at a valid movie, and a relocated entry whose current payload is empty.
Existing same-size nonmatching-payload, missing-replacement, IRX preservation and idempotence tests still pass.

No runtime patch or game recompile is needed to change these TOC mappings. Rerun disc preparation to update an
existing installation; the extraction cache can be reused and normalization starts from `.orig`. Adding this
profile entry changes the project's PGO identity under the existing manifest rules; no FPS comparison or reuse
of a stale release profile is certified here.

## Subtitle proposal: implementation unavailable

The quality problem is consistent with `merge_translation()`: the full edition preserves original movie bytes,
so subtitle text burned into a translation's re-encoded pictures disappears. `sceMpegGetPicture()` has decoded
RGBA frames and a frame counter before `writeDecodedFrameToGuest()`, making the proposed overlay point plausible.
That observation does not validate the missing implementation.

A review needs the actual patch and format specification; translated text is not required. Synthetic subtitle
fixtures can cover absent files, malformed/truncated files, bounded allocation, clipping and movie-state reset.
The first-256-KiB fingerprint needs identity checks across the intended PSS/PSW set: equal prefixes remain equal
regardless of hash algorithm. Frame-number timing needs whole-movie checks, transitions, skipping/replay, 4:3
and 16:9 playback, plus audible synchronization. A single sampled picture cannot establish whole-movie sync,
and linear scaling for SEMO13 is only suitable if the timing difference is actually uniform.

The report's 467 lines, correct sampled subtitles, 12 successful normal intros and lowest 58.8 FPS window were
not reproduced. Its i7-10700/RTX 3060 result cannot be transferred to the i5/UHD laptop. An added runtime patch
changes the PGO manifest identity; validation must use a matching profile or explicitly disable PGO rather than
treat the reused profile as release evidence. No subtitle code, translator text or assets were added.

## Diagnostic override: separate unresolved claim

The code confirms that `GOW_MOVIE_OVERRIDE` replaces movie-load arguments and calls the original loader;
`GOW_BONUS_MOVIE` can also request playback from the title menu. These diagnostic entry paths differ from
normal story progression. The report says the `0x27678` budget failure occurred once in six runs without the
subtitle patch, which suggests an existing diagnostic/runtime issue, but neither its cause nor that frequency
can be independently established from the pasted text.

Do not raise the guest-call budget or change scheduling without a reproducible trace. A follow-up needs exact
runner/patch/profile identity, complete environment/settings, raw logs and repeated normal-path versus override
runs. The current local runner predates the v0.5.0 sources, so running it would not reproduce the claimed release.
No in-game hang, end-to-end movie playback, listening test or runtime performance result is claimed in this review.

## Checks and evidence

- `python -I tools/disc/prepare_test.py`: 3 tests pass, including the 3 new regression subcases; those subcases
  failed on the original implementation.
- Actual-disc private-TOC experiment: exact ten fingerprints, 15 mapped entries, no remaining matching-size
  placeholders, preserved original TOC and idempotent rerun.
- `python -I tools/disc/import_test.py`: 8 passed, 6 real CHD round-trip cases skipped because `chdman` is unavailable.
- `python -I tools/test/disc-import-ui.py <qml.exe> <compiler-bin>`: actual QML import/retry/routing check passes
  offscreen; the platform plugin reports no OpenGL context, so this is not GPU rendering validation.
- `python -I tools/test/pipeline_tests.py`: 17 pass. `git diff --check`: clean.

Local evidence is under ignored `data/gow1/logs/movie-placeholders-{before,profile-only,after}.json` and
`movie-investigation-{import,pipeline,ui}-tests.log`. No game media or translated subtitle text is committed.
