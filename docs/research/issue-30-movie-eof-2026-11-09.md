# Issue 30: Cliffs of Madness movie EOF

Investigation of [issue 30](https://github.com/Vnnc1/gow-native-pc/issues/30),
against `fix-chore` `086aa765a182e53d019d421f4f2f2fc6fd57aa4b`.
This is a correctness investigation, not a performance experiment.

## Report and reproduction

The reporter describes the lever lowering a block and rope, followed by a camera
pan to a doorway; the camera stops, then the fires stop. Disabling early GS FINISH
did not help. A comment reports FMV skipping as a workaround.
The attached session enters MPEG at approximately 123.35 seconds, then records
zero guest frame probes while the host continues presenting at 60 Hz. Those
counters alone cannot distinguish ordinary FMV playback from a stuck movie.

The inherited runtime documentation, `docs/waffle/fmv.md`, already records an
unresolved EOF stall in `P04MP05`. Local inspection confirms this movie contains
the suspended block/rope and the doorway with two fires described in the issue.
It is separate from the translated SEMO placeholder correction and the movie-tail
audio clock correction.

The prepared local PT-BR disc has a USA-compatible executable (CRC `97464644`)
and both PAK files. Its first `P04MP05.PSW` TOC entry is 23,871,492 bytes:
SHA-256 `9376ec124d708f1346eab4ea207c5c3a8ef03c77d60fee339aabd96fccd54af3`.
The sequence end is at byte 23,858,701, in the last full 16 KiB block; the four-byte
program end is at 23,871,488. FFprobe counts 741 pictures at 30000/1001 fps in this
payload. The historical document's 743-picture count is not used as a new oracle.

The existing installed runner reproduced the stall after its `frame=720` marker.
Reads reached `position=16c4000 -> 4`, then `position=16c4004 -> 0` with no menu
return. It still closed normally. The previous movie smoke script reported
success because it checked only that playback started; that is not completion.
This failed reproduction remains under `data/issue-triage/30-baseline-p04mp05`.

## Cause and targeted correction

The USA movie read callback at `0x188848` uses the stream structure at `0x2FDE10`.
Its state (`+0x28`) becomes 3 after the backing read reaches EOF. `+0x24` counts
queued blocks that still need to be delivered. After draining them, the callback
returns zero. The MPEG refill function at `0x18AC20` treats zero as temporarily
empty and retries in its blocking path; it sets the movie EOF flag only for a
negative callback result. This prevents the final buffered data from draining
through the normal movie completion path.

`zzz-305-movie-reader-eof.patch` wraps the USA read and movie-completion callbacks. At the reader entry,
for the two refill callers (`0x18AC70`, `0x18AD34`), a positive-size request with
state 3, zero queued blocks and no cancellation returns -1. Pending blocks,
temporary emptiness, cancellation, other callers, and checkpoint resumes delegate
unchanged to the original. The wrapper does not alter PAK/TOC data, inject an end
marker, skip a video, raise a guest budget, or change global IOP/decoder timing.
Registration is unconditional on the normal movie path; no player flag enables it.
Regional overlays are unchanged.

Returning -1 alone is insufficient: the guest sets `movie+0x154`, which makes
`0x189B00` report completion even with decoded pictures pending. The first
candidate returned to gameplay but only served pictures 0..739. Temporary
instrumentation at sequence end proved `served=739 queued=2`; one picture was
subsequently served and one discarded. That candidate was rejected.

The final completion wrapper delegates to the original except at its normal
entry with a non-null MPEG-format player, the read-EOF flag, drained stream EOF
and no cancellation. In that case it probes the existing synchronous
`sceMpegIsRefBuffEmpty` using a copied CPU context, and returns not-ended while
pictures remain. It preserves the guest registers, the original EOF flag and all
resume paths. Once the queue drains, the original completion/display-tail path
runs. There is no new decoder API or global codec behavior change.

## Validation

- All 118 baseline runtime patches applied in ordinal order to the pinned
  `471c83180a8df575cff4abd3fae6c043b5096925` runtime in `C:/gow-i30-src`.
  The current-chain baseline reproduced the EOF hang through normal new-game
  playback of `P04MP05` (`30-current-baseline-newgame`).
- The final patch passes forward and reverse application checks against that
  chain. Its exported source and compiled runner copy are identical apart from
  CRLF/LF. Release runner compilation passed in isolated `C:/gow-i30-build`.
- Production wrapper fixtures passed both against the isolated current runtime
  and the workspace runtime: existing one-field movie-tail clock/resume checks,
  1,152 reader combinations, and a three-picture drain followed by completion,
  plus cancellation, pending input, format, null-player and resume delegation.
  `movie-tail-tests.py` remains in the normal Windows `verify` stage.
- `tools/test/pipeline_tests.py`: 17 tests passed. `git diff --check` passed.
- Instrumented final candidate (`30-candidate2`): all 741 pictures served,
  `mpeg_pic_740.ppm` produced, gameplay began at 58.23 seconds and the 80-second
  capture showed the opening ship combat. Completion gate passed; exit 0,
  graceful close, no matched guest error. Temporary MPEG instrumentation was
  then restored byte-for-byte to the baseline and the runtime was rebuilt.
- Uninstrumented final runner (`30-final-p04mp05-retry`): last-picture and
  gameplay-completion gates passed, exit 0, graceful close, no matched guest
  error. The last picture's SHA-256 is identical to the instrumented run:
  `67095aaf79cea5aad32f74309a82f825d41e7a07c3fcf6f56807eaf105ea9586`.
  The final runner SHA-256 is
  `f8c986e90c7c26bcc2e10221c4c4d8d8d7f2bf59c4155489bc39e66a300f124a`.
- Uninstrumented `A01MP02` regression (`30-final-a01mp02`, 115 seconds):
  independently counted 998 pictures; the final picture (997) and gameplay
  completion gates passed. Gameplay began at 65.01 seconds; exit 0, graceful
  close, no matched guest error. This exercises a second movie's existing tail
  clock path with the same final executable.
- `tools/test/linux_pipeline_tests.py`: 7 tests ran, OK with 1 platform skip on
  Windows. PowerShell parser checks passed for the harness and verify module.
  These are pipeline unit checks, not a Linux runtime/gameplay build.
  The entire `verify` stage was not run; the affected runtime fixtures were.

The harness now supports `-NewGame` (replace the intro), `-RequireCompletion`
(return to gameplay/menu), `-ExpectedLastPicture` (require the decoded-frame
capture) and `-Visible` (visible window/audio enabled). Merely reaching frame 30
is insufficient for the completion gate. An early-EOF candidate that loses the
last picture fails the new picture gate even if it reaches gameplay.

Reproduction command, using a private card copy created by the harness:

```powershell
$env:GOW_PAD_TEST='1'
$env:TOBIICHI_VENTANA_FPS='60'
$env:PS2X_GS_HW_SCALE='2'
pwsh -NoProfile -File tools/test/movie-smoke.ps1 `
  -Runner data/issue-triage/30-final.exe -Elf <prepared-disc>/SCUS_973.99 `
  -Card <prepared-disc>/Mcd001.ps2 -Movies P04MP05 -Seconds 100 `
  -NewGame -RequireCompletion -ExpectedLastPicture 740 -Visible `
  -OutputDirectory <new-private-directory>
```

Rejected/non-comparable runs are retained: bonus-menu trials failed before
playback with target `0x161c68`; some scripted boots did not reach the scripted
pad/new-game route and instead entered the `Semo01` attract path with an
unhandled IOP `cdvdman:15` import. They are not successful EOF tests. The harness
reported those failures. No result from them is used to claim playback success.
The initial reader-only candidate is retained as negative evidence of tail loss.

## Isolation and limits

Hardware: Xeon E5-2666 v3, RX 580 2048SP, Windows. The current-chain build uses
pinned LLVM 20261020, Release, portable x86-64-v2, no PGO and no VU1 AOT capture
inputs. The USA EE generated sources are reused from the local compatible
installation; runtime and override copies are built in isolation. Source/runner
hashes and logs live in ignored `data/issue-triage/30-*`.

The available local card backups contain early-game saves, not a confirmed save
at this lever. Two backup cards are byte-identical. Source cards and the installed
runner/build selection remain untouched; movie tests use private card copies.
No full-campaign, regional, NVIDIA, audio-quality or performance acceptance is
implied by isolated movie playback. No game media, card or generated game code is
included in the patch or repository documentation. The installed `gow-test`
runner and its build were not replaced. Existing installations need a new runner
built with `fetch,sync,build`; fetching/building without syncing the owned
`gow_overrides.cpp` copy is insufficient.
