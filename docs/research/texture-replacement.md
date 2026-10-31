# Texture dump and replacement (planned runtime patch) — design

Status: **design only, nothing implemented**. This replaces the outline in
[roadmap-2026-10-27.md §4.4](roadmap-2026-10-27.md) and
[audio-standalone-mods-2026-10-26.md, "Texture packs"](audio-standalone-mods-2026-10-26.md). Both put the hook in
`gs_texture_store.cpp`, but this game's textures do not go through it on their way to the GPU (see §2). The roadmap's
patch numbers 42-43 are taken now; the patch gets the next free number when it is written.

Goal: let players replace God of War's textures with higher-resolution or edited images, the way PCSX2 texture packs
work. The patch must change nothing at all while it is off.

## 1. How PCSX2 does it

1. **Dump.** When the GS samples a texture for the first time, PCSX2 hashes its *contents*: the texels in GS memory,
   plus the palette (CLUT) for an indexed texture. It writes one PNG per hash. An address alone cannot identify a
   texture, because the game keeps reusing the same VRAM for different textures.
2. **Edit.** A modder edits or upscales the PNGs (by hand, or with ESRGAN-style AI upscaling) at any multiple of the
   original size. The files keep their names and go into a replacements folder.
3. **Replace.** For each texture it has not seen yet, PCSX2 computes the same hash. If a file with that name exists, it
   uploads that image instead of the decoded one. Replacements load asynchronously, so the original shows for a frame
   or two instead of stalling.

PCSX2's hashes depend on its own texture cache. Do not assume that existing PCSX2 packs work with this renderer under
the same names (§8).

## 2. Where textures reach the GPU in this runtime

All paths are relative to `engine/runtime/PS2Recomp/ps2xRuntime/src/lib/gs/`.

| Path | What it does | Role for this patch |
|---|---|---|
| `gpu/gs_hw_backend.cpp` `textureFor` (≈ line 899) | Direct-colour textures (CT32/CT24/CT16). Address-based cache key (tbp0, tbw, psm, TW/TH, TEXA, plus CLUT hash/CSM/CSA for indexed). On a miss: `decodeDirect` → RGBA8 → `glTexImage2D` | **Main hook**: hash, dump, replace |
| `gpu/gs_hw_backend.cpp` `indexTextureFor` (≈ line 1008) | Indexed textures (T8/T4/T8H/T4HL/T4HH). Uploads an R8 index texture; the shader does the palette lookup and the bilinear/anisotropic filtering itself (`indexedTexel`) | Most of the game's textures. Need their own path (§4.4) |
| `gpu/gs_hw_backend.cpp` `invalidateBlocks` | Invalidates cached textures whose block range [blockLo, blockHi) an upload overlaps | Replacement entries follow the same invalidation |
| `gpu/gs_texture_store.cpp` | Holds the uploaded bytes in GS memory layout and loads the CLUT (`LoadClut`, `ClutHash`). `DecodeTextureRgba` is only the fallback for formats with no direct layout ("none seen in this game") | Hashes come from here (CLUT words), not the hook |
| Render targets (`RenderTarget`, `findReinterpretSource`, `uReinterp`, `uZTex`) | Textures the game drew itself: framebuffer effects, reflections, bloom, depth haze | **Never replaced** |

Debug dumps that already exist: `GOW_GS_HW_TEXDUMP=<n>` writes `gs_hw_tex_NN_tbp<addr>_psm<p>_<w>x<h>.ppm` (named
by address, so the names change from session to session) and `GOW_GS_HW_PALDUMP=<tbp>` writes index textures. These
can be reused for testing, but they are not the dump format this patch defines.

Shader facts that matter (the fragment shader in `gs_hw_backend.cpp`, roughly lines 236-345):

- Coordinates stay in PS2 texel units: `uv = STQ/Q * uTexDim`, clamped to `vUVClamp` (the texel range a sprite samples).
- The direct-colour point and linear paths already handle a texture that is larger on the host than its PS2 size,
  with `k = textureSize(uTex) / uTexSize`. That is how scaled render targets are read. A replacement that is 4× in
  each axis has the same layout as a target drawn at scale 4: PS2 texel j covers host texels 4j..4j+3. **Expected
  result:** set `uTexSize`/`uTexDim` to the original TW×TH and the existing scaled path samples the replacement
  correctly. Confirm the 0.5 − 0.5/k shift on the linear path (made for render targets) for uploaded images, or
  bypass it with a `uReplaced` flag.
- Anisotropic filtering (`GOW_ANISO`, `uAniso`) currently runs only when k = 1. Replacements need either
  hardware mipmaps with `GL_TEXTURE_MAX_ANISOTROPY` or the manual taps extended to k > 1.

## 3. Identity (the hash)

A replacement must map to the same texture across sessions, game versions (US, PT-BR and other editions that share
the art) and runs on different machines.

```
texture_id = XXH3_64(
    version byte,                 // bump when the definition changes; old packs stop matching instead of mismatching
    psm, TW, TH,                  // format and size from TEX0 (not tbp0 or tbw: those are addresses and layout)
    texel words of the TW×TH area, read in linear order (unswizzled) from GS memory,
    for indexed: the CLUT entries this texture can reach (16 for T4, 256 for T8) after CSA/CSM/CPSM, plus TEXA when
                 CT24/CT16 alpha expansion applies
)
file name: <texture_id as 16 hex digits>.png    (optionally "-<psm name>" for readability)
```

- Hash the **unswizzled texels**, not the raw blocks. The same image uploaded at another tbw gives the same id.
- For indexed textures, hash **indices and palette separately**: `id = hash(indices) ⊕ hash(palette)`, and also
  record `hash(indices)` alone. A pack can then replace "this image with any palette" (`<idx>-any.png`) or one palette
  only (`<idx>-<pal>.png`). God of War animates palettes (flashes, colour pulses), and a pack would otherwise need one
  file per frame of the animation.
- Hashing runs only on a cache miss (`stats.texDecodes`), not on every draw. Measure it: it must stay well under the
  decode it sits next to.
- Depends on correct CLUT decoding. Check the colour-tint issue
  ([handoff-2026-10-25-performance-phases.md §5](handoff-2026-10-25-performance-phases.md),
  [roadmap §2.6](roadmap-2026-10-27.md)) first. While it is open, dumped hashes of indexed textures may be
  wrong and the ids would have to change later.

## 4. Behaviour

### 4.1 Settings

| Variable | Default | Effect |
|---|---|---|
| `GOW_TEX_DUMP=1` | off | Write each new texture id once to `data/<id>/textures/dump/` |
| `GOW_TEX_DUMP_MIN=<px>` | 16 | Skip textures smaller than this in both axes (gradients, 1-pixel fills) |
| `GOW_TEX_REPLACE=1` | off | Use `data/<id>/textures/replace/` |
| `GOW_TEX_REPLACE_DIR=<dir>` | — | Another pack folder (testing several packs) |
| `GOW_TEX_DIAG=1` | off | `[gow-tex]` log: ids hashed, dumped, replaced, load time, VRAM used |

Launcher / F1 menu: "Texture pack" (on/off) on the Graphics tab, through `runtime/gow_ajustes_vivo.h` like the other
live settings (patch 39). Dump stays a developer switch (environment variable or debugger), not a player option.

### 4.2 Dump

- On a miss in `textureFor` / `indexTextureFor`, compute the id. If it is new this session and has no file yet,
  queue `(id, RGBA8 pixels, w, h)` to a writer thread. A bounded queue drops the oldest entry and counts it, so the GS
  worker never waits on the disk.
- Write PNGs with alpha. Convert the GS's 0-128 alpha range to 0-255 on dump and back on load. Document this for pack
  authors: an alpha of 255 in a PNG means GS 128 (opaque).
- Indexed textures are dumped as RGBA through the current palette, so the PNG looks like what the player sees. The
  file name carries both hashes (§3).
- `raylib` (already linked: `gow_integracion.cpp` includes it) has `ExportImage` / `LoadImage` (stb_image) for PNG.
  No new dependency is needed for phase 1.

### 4.3 Replace

- At start: list the pack folder into a map `id → path` (names only, no decoding). No disk reads in the frame loop
  after that.
- On a miss whose id is in the map: upload the original as usual and ask a loader thread to decode the file. When
  it is ready, the GS thread (it owns the GL context) uploads it with mipmaps (`glGenerateMipmap`) and linear
  filtering, then marks the cache entry `replaced`. Later draws bind it, with `uTexSize` left at the PS2 size (§2).
- Accepted sizes: whole multiples of TW×TH, at most 8× and 4096 px per axis. Anything else is logged and ignored
  (the original stays).
- `.dds` with BC7 is a later step. It saves VRAM and load time for big packs, but PNG alone is enough to start.
- VRAM budget: LRU over replaced textures, with a configurable limit (default 1 GiB). An evicted replacement falls
  back to the original until it is loaded again.
- Invalidation: a replaced entry is dropped by `invalidateBlocks` exactly like an original. The next miss recomputes
  the id, so a texture the game overwrites with new contents loses its replacement correctly.

### 4.4 Indexed textures

When a replacement exists for an indexed texture, that draw goes through the direct-colour RGBA path
(`uIndexed = 0`) with the replacement bound. Without one, the R8 index path is unchanged. Wrap/clamp (`uWrap`,
REGION_CLAMP) still works in PS2 texel units, so the larger image wraps and clamps at the same texture edges.

### 4.5 Never replaced

- Render targets and reinterpretations (`uReinterp`), depth reads (`uZTex`), shuffles (`tryShuffle`).
- Textures shorter than `GOW_TEX_DUMP_MIN`, unless a pack lists them explicitly (a later manifest).
- FMV frames: the video decoder uploads new frames each time, so their hashes never repeat.

## 5. Things that will go wrong

| Risk | Mitigation |
|---|---|
| Text/HUD built from many small pieces of one atlas | Hash the TW×TH that TEX0 declares, not the drawn sub-rectangle. Same atlas = same id |
| Same image at several TEXA settings | TEXA is part of the id only for CT24/CT16 (§3) |
| Palette animation makes many ids | `<idx>-any.png` (§3) |
| Hash cost in scenes that stream textures | Measure with `GOW_TEX_DIAG`. Hash in the same pass as `decodeDirect` |
| First use shows the original (pop-in) | Optional preload of the whole pack into RAM at start (`GOW_TEX_PRELOAD=1`) |
| Bigger textures change the GPU load | Measure FPS on the reference route with and without a pack (RX 580; an Intel HD class GPU, see patch 47) |
| A pack hides a decoding bug | Dumps are taken with the pack off |

## 6. Tests

- **Unit (no game data)**, in `verify`: a synthetic GS memory image with a CT32 and a T8 texture uploaded at two
  different tbw/tbp values. Same id for both. Changing one texel or one palette entry changes the id. The `-any`
  rule matches across palettes.
- **Off = unchanged**: with both switches off, a fixed-input run (`GOW_PAD_TEST` script, `GOW_HOST_SHOT`) gives the
  same images byte for byte as before the patch.
- **Real game, by hand**: dump the first area, replace three textures (one CT32, one T8 with an animated palette, one
  HUD piece) with obviously marked images, and check they appear, wrap, clamp and keep their alpha. Then do the
  same in a translated edition.
- Record the hash cost, load time and VRAM numbers in this document when it is implemented.

## 7. Legal and distribution

Dumped textures are copyrighted game data. They follow the rule for everything game-derived: they live only under
`data/`, never go into the repository, never go into the release package, and are never attached to an issue. The
project ships the mechanism and the documentation (the folder layout, the id rule, the alpha convention). Packs are
made and distributed by their authors, outside this project.

## 8. Later

- A pack manifest (`pack.toml`: name, version, game edition ids, per-texture options such as "keep point
  sampling").
- PCSX2 pack import: map PCSX2's names to these ids by dumping the same scenes in both. Only worth it if packs for
  this game exist.
- BC7 `.dds`, and a `tools/` script that converts a PNG pack and generates its mipmaps.
- Other quality options that do not need packs: internal resolution (already there, `uPxScale`), anisotropic
  filtering for indexed textures at k > 1, mipmaps for uploaded textures.
