# GS per-batch prelude: what the 105 us of a batch are spent on (patch 72)

**Date**: 2026-11-05
**Machine**: Intel Core i3-4170 (2C/4T Haswell) + Intel HD Graphics 4400, 8 GB DDR3, Windows 10
**Disc**: Asia `SCAJ-97399` (`SLPM_670.10`), internal 0.5x, `PS2X_GS_WORKER=1`, VU1 x64 JIT, `GOW_VU1_FAST=1`
**Measurement**: `GOW_GS_COST=1` (patches 62/64), 5 s windows, 22–25 s runs, `data/_tmp/bench.sh <tag> 25`

## Conclusions first

1. The GS worker spends **~70–93 us per batch** and the renderer submits 12–18k batches per 5 s. That per-batch number,
   not the primitive count, is the wall: 12k batches × 90 us is 1.1 s of every 5 s.
2. Of that, the **prelude** (`BindFramebuffer` + `Viewport` + `Enable(SCISSOR_TEST)` + `Scissor` + `Disable(CULL_FACE)`)
   was 141–194 ms per 5 s — about 11 us per batch for five calls, i.e. ~2.3 us per driver call, thirteen times what a
   `glUniform*` costs here. Patch 72 issues each call only when its arguments change and removes two calls outright:
   **pre_fbo 141–194 → 47–94 ms per 5 s, one_ms/batch 83.5–92.8 → 69.4–71.8 us**.
3. `Disable(CULL_FACE)` was a pure no-op: nothing in `gs_hw_backend.cpp` ever calls `Enable(CULL_FACE)`.
4. The **texture cost is not where the comment in `textureFor()` said it was.** `[gs-hw] direct=0/0K idx=785/80384K`
   says this disc decodes **zero** direct-colour images and ~800 paletted ones per 5 s, 80 M texels. The whole
   `tex_resolve` (370–400 ms per 5 s) is `indexTextureFor()` → `GSMem::ReadIndexRun()`.

## Evidence

### Per-batch split (0.5x, opening level, `[gs-cost2]`)

| item | before patch 72 | after |
|---|---|---|
| `pre_fbo` (bind + viewport + scissor + enable + cull-face disable) | 141–194 ms / 5 s | 47–94 ms / 5 s |
| `pre_tgt` (target lookup, depth attach) | 68–71 | 62–68 |
| `tex_lookup` (find target/reinterpret source) | 401–403 | 392–429 |
| `tex_resolve` (decode + upload) | 377–392 | 372–402 |
| `tex_bind` (sampler + uniforms) | 57–60 | 53–65 |
| `draw` (`glDrawArrays`/`Elements`) | 212–225 | 198–223 |
| `one_ms` per batch | 83.5–92.8 us | 69.4–71.8 us |

The scene changes between runs (opening level, game-driven), so absolute `gs_ms` is not comparable across runs; the
per-batch figure and the `[gs-cost2]` split are.

### Where the texture time goes

`[gs-hw]` with the counters added by patch 72:

```
[gs-hw] ... texDecodes=785 texHits=5774 texReuse=785 ... direct=0/0K idx=785/80384K
```

- `direct=0` — `decodeDirect()` never runs on this disc: every textured draw uses a paletted format, so the
  `decodeDirect()` work (including the per-format TEXA row loops added in the same patch) is dormant here.
- `idx=785/80384K` — 785 index decodes of ~102 KB of texels each, 80 M texels per 5 s, which at the measured 370–400 ms
  per 5 s is **~4.5 ns per texel**: the per-pixel page-table walk of `readIndexRunT<P8>`.

## Falsified

**PSMT8 rows are not linear in memory — a run cannot be a `memcpy`.** The plan was to read up to 16 consecutive index
bytes per page-table lookup (P8 columns are 16×16). A checker (`GOW_GS_IDXCHECK=1`) compared the fast path against the
per-pixel one and reported, on the first decode:

```
[gs-idxcheck] bp=35a0 bw=2 at 1,0 run 16 ref=178 fast=36
[gs-idxcheck] bp=35a0 bw=2 at 2,0 run 16 ref=138 fast=67
```

The first two pixels of row 0 are 142 bytes apart. The fast path and the checker were removed; the patch does not touch
`ReadIndexRun`. Anyone revisiting this needs the real `columnTable` layout for P8 (`ps2_gs_memory.h`,
`ColumnExtent = {16,16}`), not the assumption that a column row is contiguous.

**Hoisting the page-table walk out of the texel loop buys nothing.** `PixelStorageTraits<P8>::Read` was replaced by a
version that takes `PageTableP8[bp & 31][y & 63]` once per run and computes the page base once per 128 texels, leaving
one `u16` table read and one byte load per texel. Verified identical by `GOW_GS_IDXCHECK` (0 mismatches), measured
**3.2 ns per texel against 3.1 ns** — the compiler already keeps the loop invariants out of the loop. Removed.

**Partial re-decode does not pay on this game.** The obvious fix for "re-decoding 100 % of an image for a small write"
is to re-decode only the written part. Measured first, with two counters added for exactly this (`[gs-hw] blk= box=`):

```
blk=41%/1202  box=91%     (one 5 s window)
blk=42%/1164  box=93%
```

`blk` is the share of the image's 256-byte blocks the upload actually rewrote; `box` is the rectangle covering those
blocks as a share of the image area. **42 % of the blocks, but 91–93 % of the area**: the game rewrites scattered
atlas entries (sprites, glyphs, UI pieces) across the whole image, so the rectangle that covers them is the image. A
partial `glTexSubImage2D` would decode almost as much and add a call per rectangle. Not implemented.

That leaves index decoding at ~370 ms per 5 s as a floor for this game, given that half of the invalidations are also
already filtered out as "bytes unchanged" by patch 61 (`texReuse` ≈ `texDecodes`).

Also confirmed (again): the 16×16/8×8 sub-block ordering means "the address of pixel x+1 equals address of x + bpp" is
false for every paletted format — this is the third time an assumption of that shape has cost a build here.


## What this patch does not fix

- `tex_resolve` is still 370–400 ms per 5 s. Note that `tex_lookup` in `[gs-cost2]` is not a second item: it is
  `tex_scan` (11–26 ms, the target lookup) plus `tex_resolve`, so the only remaining texture item is index decoding,
  and the measurements above say it is already at its floor for this disc.
- `draw` at ~200 ms per 5 s is 12–18k draw calls of ~180 primitives each; reducing it means fewer, larger batches, not
  cheaper calls.
- VU1 remains the frame-level wall (~2.3 s per 5 s); lowering GS cost moves the guest rate only as far as the
  VU→GIF→GS queue lets it (`[gs-pub]` wait time, patch 64).

## Rollback

- State calls: `GOW_GS_STATE_CACHE=0` restores the unconditional `Viewport`/`Scissor`/`Enable`/`Disable` calls. The two
  deleted calls (`Disable(CULL_FACE)`, the closing `Disable(SCISSOR_TEST)`) come back only by reverting the patch.
- Decode counters: always on, three `uint64_t` adds per decode (785 per 5 s).
- Patch file: `engine/patches/72-gs-batch-prelude.patch`; verified to apply cleanly to the pre-change tree and reproduce
  the working-tree file byte for byte.
