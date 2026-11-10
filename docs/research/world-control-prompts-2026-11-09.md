# Enemy world-space button replacement — 2026-11-09

Patch `zzz-312` replaces USA `goMiniGameCircle` render submissions with the same
device-aware, remapped Circle-action label used by Flash prompts. It applies to
the USA executable and compatible translations. Real combat QTE acceptance is
reserved for the maintainer's manual tests; no Hydra sequence was completed here.

## Evidence and implementation

The USA show/hide routine at `0x1E0870` creates the named model and stores it at
creature offset `0x1B8`. The model resource contains the exact lower-case name
`gominigamecircle` at resource offset `+12`. Its type-15 rendering child points
to the type-1 model through `+0x18`, and the model points to its resource through
`+0x1C`. Runtime snapshots of privately forced instances confirmed this layout.

The replacement does not intercept creation, destruction, health, input, sound
or the QTE state machine. It intercepts only the final rendering functions
`0x158020` and `0x158B40`, entered from the verified call sites in `0x157A60`
(return PCs `0x157EF0`, `0x157F0C`, `0x157FD0`). This preserves the preceding
animation, mesh selection and CPU visibility work. Other callers and resume PCs
delegate to the original function.

At those call sites, `a3` is the view-space matrix at caller SP+64; the
preceding matrix is the animated world transform. The hook verifies that stack
relationship, node/model types, exact resource name, bounded mesh counts and
memory ranges. It transforms the mesh bounding-sphere center and projects it
through the existing USA camera view-projection matrix (`*0x35FA98 + 0x40`).
Nonfinite values, behind-camera/offscreen positions and unsupported layouts
retain original rendering. The button's diameter follows the projected bound,
halved to exclude the original flares and limited to 24–96 guest-screen pixels.

The prompt uses the existing Circle-action mapping, last-input selection,
textures and complete-frame publication. World coordinates bypass the additional
Flash widescreen stretch. World and Flash entries are distinct during duplicate
suppression. The original mesh remains until host replacements are ready and
when the 128-entry batch is full. No guest RAM is modified by the replacement.

The active layout matters: Xbox Circle/Triangle actions are B/Y in the classic
layout and X/B in the built-in modern layout. Explicit launcher remappings take
precedence. The test suite checks both layouts plus custom maps and the Sony
families; device family alone does not determine an action's button.

## Validation

Windows / Xeon E5-2666 v3 / RX 580, LLVM MinGW 20261020, Release:

- Final runner built successfully, SHA-256
  `47a231bfdcc7d8ad046a4020f68abfddd8eba105ccda9b5735155742fe7a61b9`.
- CTest `gow_control_prompts` passed (14.12 s). It compiles production input,
  label, frame and render-hook code and runs the existing four QTE input modes.
  World-specific assertions cover identity, both submission paths, translation,
  projection, invalid pointers/counts/NaNs, negative depth, offscreen positions,
  caller/entry/stack gates, readiness, capacity, disabled mode and unchanged RAM.
  Complete/empty-frame tests include world prompts. This is already in `verify`.
- Patch application/reverse checks passed in both the workspace runtime and the
  isolated full-chain runtime; their final `gow_iconos.cpp` hashes match.
- `world-keyboard/host_shot.png` shows mapped K buttons replacing orange circles
  on the ship. This used a temporary, private test hook to force instances on
  Kratos and enemies; overlapping K labels belong to separate forced instances.
  It is a rendering probe, not a legitimate QTE completion. The visual runner was
  `75ef335b21fabce8893a6d73e4bf1a2e40a280ba8e0194c04cfea89fbad6ceb4`, before the
  additional SP gate and removal of the injection hook.
- That collector completed with exit 0. The source card remained
  `4fe0d4a429b64cd5c0e0a12f6c89e5fd6faffc02f98c53570c4b3432e7341d10`.
  The subsequent one-enemy Xbox visual trial was interrupted after computer-use
  reported the physical Escape key. It was closed normally (collector completed,
  exit 0, source card unchanged), but has no accepted host capture.
- All injection and RAM-dump instrumentation was removed from the final source
  and patch. The final runner was rebuilt and unit-tested after cleanup; a fresh
  interactive run of that exact binary was not performed after the interruption.

Ignored local evidence is under `data/world-prompts`: `circle-probe3..6`,
`world-keyboard`, `world-xbox`, `build-world-final.log`, `ctest-world-final.log`.
Earlier probe attempts are retained: forcing the indicator during initialization
hit an unavailable virtual method; the first update probe did not complete a
yielding guest call. Neither is a valid rendering check. The corrected temporary
probe completed the guest call before restoring its test context. No such guest
execution helper ships in `zzz-312`.

## Manual acceptance and limitations

Use a rebuilt runner with normal launcher settings, without scripted test flags.
Reach the actual enemy/Hydra indicator and complete the QTE. Check the world
indicator, tutorial symbol and each QTE face/shoulder symbol when switching
keyboard/mouse, Xbox, DS4 and DualSense and after remapping Circle/Triangle.
Check two nearby eligible enemies, death/despawn, camera changes, pause/resume,
the edges of the screen and enemies behind scenery. Direction diagrams remain
original so required rotation/shake directions are not lost.

At the zzz-312 baseline this is a flat host overlay, not a replacement textured 3D mesh. The projected
anchor follows the animated model, but the original spinning plate/flares are
removed. Host icons do not share the guest depth buffer or later full-screen
compositing passes; geometry occlusion and modal dimming are not guaranteed.
Physical-controller detection/hot-switching and real combat sequences remain
unvalidated. No regional EU/Japan, Linux, performance or other-hardware claim.

Existing installations need the rebuilt runtime; a launcher-only update is not
sufficient. The final local runner is `C:\gow-i30-build\ps2xRuntime\ps2EntryRunner.exe`;
the user's installed runner and preferences were not replaced.

## Xbox visual follow-up — zzz-313

Xbox face buttons now use dark, worn medal rims, deterministic stone grain and
colored A/B/X/Y lettering. QTE/world variants add a muted bronze inner ring;
shoulder buttons retain a rectangular silhouette without a second round plate.
All device artwork is baked to 48 pixels high with bilinear sampling to blend
with the game's UI. Allocation failure retains the existing higher-resolution
texture. No input mapping, last-device selection or launcher preference changes.

The world badge maximum diameter is now 64 guest pixels (minimum 24). Xbox world
badges project the four corners of the original animated model's XY plane and
show a readable face on either side of the turn. The pose comes from guest
transforms, not elapsed host time, so repeated paused samples stay identical.
Invalid projection retains original rendering. This is a projected host quad,
not a replacement guest 3D mesh: original flares are absent, and shared depth,
geometry occlusion and full-screen compositing remain limitations.

Validation on Windows / Xeon E5-2666 v3 / RX 580:

- Release runner rebuilt successfully; SHA-256 `90f22bfd532eaf2ce61fd8471481169b431c5934b5099de4c1756b0e05d7c252`.
- `gow_control_prompts` passed (16.67 s): existing default/classic/custom mappings,
  four QTE input modes and hook guards, plus front-facing corner order, narrowed
  rotated silhouette, perspective and stable repeated transform samples.
- `tools/test/control-prompts-render.py` compiles production artwork/projection
  functions against real raylib and the embedded font. The hidden OpenGL preview
  passed texture-size and nonblank-image assertions, then was visually inspected.
  A second execution also passed. It samples HUD/tutorial and QTE artwork plus
  world turns at 0/35/70/110/145/180 degrees. Its literal A/B/X/Y labels isolate
  artwork; mapping correctness comes from the production suite above.
- Initial preview attempts omitted a complete host drawing cycle and produced
  incomplete/blank captures. The fixture now warms up and completes that cycle
  before readback, with an explicit nonblank assertion. Those attempts are not
  accepted visual evidence.
- Patch application/reverse checks passed; workspace and isolated runtime source
  hashes match. Diagnostic strings retain their original UTF-8 encoding.

Local evidence: `data/world-prompts/build-style-final.log`,
`ctest-style-final.log`, `style-preview.log`, `style-preview-repeat.log`, and
`style-preview/xbox-style-sheet.png`. The preview is synthetic artwork on the GPU,
not an in-game combat capture. Real QTEs, actual model rotation during combat,
physical controller switching, pause/resume and occlusion remain manual gates.
The rebuilt runner is still the isolated path above; no installed runner or
player saves/preferences were replaced. No performance claim.
