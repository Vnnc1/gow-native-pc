# PT-BR cutscene audio: reproduced channel-block misalignment

## Scope and result

The player confirmed that their two saves load normally; the title menu question was resolved without changing
the memory card. Investigation then focused on the sailor/arrow scene, `A01MP02`, in the PT-BR disc.
The player's `Documents/test2` card and last log were backed up before testing. All test runs use private card
copies. The original card SHA-256 is `0c79fd0e12b6235781f6084cf91f194bcb72c7190527f967944a1b4f79b90a62`.

**Reproduced:** PCM channel-block corruption is already present in the engine's pre-output mix on the translated
disc. In the corresponding original-disc run, the mix matches the source to normal fixed-point rounding accuracy.
This is a separate defect from patch 24's multi-voice integer overflow. No runtime correction is claimed here.

## Controlled evidence

- Same installed runner: `C:/gow-build-c634ceb1-clang/ps2xRuntime/ps2EntryRunner.exe`, same copied card, OpenGL,
  JIT enabled, muted but paced output (`GOW_AUDIO=0` plus `GOW_AUDIO_PCM`). Patch 24 is present in its sources.
- Original and translated `A01MP01` through `A01MP05` PSW files were extracted locally using each disc's own TOC
  offsets. Their video/PES packing differs; their reconstructed audio payloads are byte-identical. Both declare
  PCM16, 48 kHz, stereo, 512-byte channel blocks. Extracted source tracks have zero saturated int16 samples.
- `A01MP02` reconstructed audio payload SHA-256 starts with `6c1aed6063a0803b` in both discs. No game asset is checked in.
- Forcing A01MP02 from the title menu failed before playback (`missing-target`, source `0x161c68`, target zero).
  This diagnostic route is not valid evidence about its audio. The reproducible route is new game followed by
  `GOW_WARP=ATHN01D`; the level script loads `a01MP02`. The 180-second PT-BR run exits 0 without a forced stop or
  guest branch errors. The original-disc comparison uses the same route.

Source-relative second 4, after sample alignment:

| Measurement | PT-BR run | Original run |
|---|---:|---:|
| Gain fitted against original stereo source | 0.741515 | 0.999764 |
| Residual RMS after fitting gain (int16 units) | 2244.99 | 1.17 |
| Distinct-channel samples compared | 46822 | 46822 |
| Left output matches source left within 10 units | 30009 | 46822 |
| Left output matches source right within 10 units | 16813 | 0 |
| Saturated samples in that second | 0 | 0 |

The PT-BR left output changes source channel at source-sample phase 164 within each 256-sample period. For phases
164-255 the right output instead matches the left source **256 samples ahead**: all 17,204 tested samples in that
one-second window match within 10 units. This is the pattern of a misaligned serialized L/R block stream, not merely
excess gain. At 48 kHz the period is 187.5 Hz, consistent with a buzz. Later local alignment also jumps by 4,096
stereo frames (one 16 KB stream ring), so a single global lag is insufficient for judging the entire clip.

This identifies the defect at or before the SPU2 input mix. It does not yet identify the exact write that loses
alignment, prove that every original-disc session is immune, or establish that every other cutscene has this defect.
The stored raw mix makes a device/driver-only explanation insufficient for this reproduced case.

## Reproduction and analysis tools

`tools/test/movie-smoke.ps1` takes explicit Runner, Elf, Card and OutputDirectory paths. It creates a private card,
records pre-output `mixed.s16le` and post-output `output.s16le`, enables MPEG/output diagnostics and closes through
WM_CLOSE. Use `-Movies A01MP02 -Warp ATHN01D -Seconds 180`. It rejects guest branch errors and requires the requested
movie to reach picture 30; merely playing the intro is not a successful reproduction.

`tools/test/movie-audio-compare.py` requires numpy. It demultiplexes the source PSW's PCM packets, validates the
format, finds a sample lag within a supplied recording interval and reports per-second residuals and channel
matches. For these local runs use `--start 85 --end 135` (PT-BR) or `--start 80 --end 135` (USA). This is diagnostic,
not a universal pass/fail threshold: movies such as A01MP05 intentionally retain background music.

Local evidence: `data/gow1/logs/movie-sailor-warp-{ptbr,usa}/` (logs, raw/output PCM, analysis.json, summary.json).
Source extraction is under `data/gow1/logs/movie-source/`, also ignored by Git.

## Next correction: trace where alignment is lost

1. At the MPEG demux/callback boundary, record accepted/refused payload byte counts and a rolling hash. Compare the
   concatenation accepted into the EE ring with the extracted PCM; preserve first-packet header consumption and
   callback ownership when retrying. Inspect `MPEG.cpp` dispatchGuestStreamCallback/deliverPendingAudio.
2. At EE-to-IOP transfer, record source/destination positions and lengths, ring wraps and the first PCM byte offset
   modulo 1024. Inspect the game's `0x188688`/`0x1884B0`/`0x188610` transfer chain and LIBSD BlockTransStatus's
   reported position. Its current per-sample position and DMA granularity require validation, not a blind mask.
3. At SPU2 stream start/consumption, compare ring bytes with the accepted stream. Correct the first boundary that
   diverges; do not compensate by swapping channels, shifting every movie, lowering volume, or suppressing samples.
4. Validate both discs, first and subsequent cutscenes, natural play as well as warp, ring pressure/refused packets,
   and a deterministic distinct-channel fixture that crosses packet and ring boundaries. Require source-aligned
   residual near fixed-point rounding for A01MP02, with no new underruns or repeated rings.

The upstream `engine/runtime/docs/waffle/fmv.md` Open section independently describes an earlier intermittent
A01MP02 channel/interleave failure. The measurements above are new local evidence, not a claim that its suspected
refused-packet cause has been proven.
