# Device-aware game prompts — 2026-11-09

Patch `zzz-310` implements device-aware **USA Flash button prompts**, including
compatible translated discs. It follows actual input and the launcher's existing
keyboard/mouse and controller mappings. Combat QTE acceptance and physical Sony
controller validation remain open; this is not a claim that every on-screen
PlayStation graphic has been replaced.

## Investigation and implementation

The pinned runtime's `CONTROLES.md` describes an implementation that was removed
by upstream commit `a25331d`. Its predecessor's `gow_iconos.cpp` supplies the
GPL-3.0 Flash recognizer reused here. These buttons are vector meshes, not ordinary
texture-pack entries. The USA shape draw entry is `0x149FA0`; named HUD symbols
include `XButtonGreek`, `CircleButtonGreek`, `SquareButtonGreek` and
`TriangleButtonGreek`. Color/background matching also recognizes unnamed menu
copies. Shoulder labels are recognized from their font glyphs.

The restored recognizer draws mapped symbols at the guest prompt's location.
The existing Cinzel font and OFL license remain in upstream `assets/fuentes`;
no third-party icon pack or new dependency is downloaded. Patch `zzz-310` initially
retained original guest drawing underneath. The follow-up `zzz-311` below removes
that duplicate artwork once replacements have rendered successfully.
Guest memory ranges, counts and string lengths are checked; batches are capped
at 128 icons. Complete batches, including empty ones, publish at the existing
guest flip hook. The old 8 ms/70 ms timing heuristics are removed. Movie discovery
is throttled and requested only for newly encountered shapes; a delayed discovery
request is retained. Mesh bounds are cleared on discovery to avoid reusing bounds
from an unloaded movie.

The window thread polls input and publishes the chosen slot atomically. Button
press edges and stick threshold/direction crossings select any of four pads.
Mapped keyboard/mouse press edges select keyboard/mouse; held buttons, small
stick drift and unfocused input do not steal selection. Before any input, the
first connected pad is the initial choice. Buttons, keyboard-stick injection and
the USA pad wrapper all use the same selection. Previously a connected pad could
exclude keyboard input regardless of what the player used last.

Labels reuse the production mapping parsers. Xbox face/shoulder labels and Sony
shapes follow the physical button assigned to each guest action. DualShock 4 uses
colored shapes and SHARE; DualSense uses neutral shapes and CREATE. Keyboard
labels follow the configured key; mouse bindings draw the selected mouse button,
with numbered labels for side buttons. Where an action has both keyboard and
mouse bindings, the last used kind is preferred. Unbound actions show `-`.
Spell/Rage aliases are resolved when the underlying guest action has no direct
binding. The always-active physical controller D-pad remains a valid fallback.

`GOW_ICONOS=0` remains a developer fallback. Normal launch needs no new setting.
`GOW_PROMPT_TEST_STYLE=1..4` only works together with `GOW_PAD_TEST=1`; it is for
rendering tests, not device detection. Scripted test packets now retain their
sticks instead of being overwritten by the configured keyboard after injection.

## Validation

Windows / Xeon / RX 580, LLVM MinGW 20261020, Release, current patch chain and a
private card/disc root. Visually tested runner SHA-256:
`82b370353e21ad8d051e1ad2f21678bb3d14c862ccdf9792dc40c40d5109e939`.
The final build also resolves controller Rage shortcut aliases, covered by the
final production tests: SHA-256
`565f0d7a299c266d8b4d48e73d13b043ff12b57a72866292e94befc45989ddfe`.

- `gow_control_prompts` passed through CTest. It compiles the production pad and
  extracted production label/recognition/frame-publication functions, testing
  default/custom maps, keyboard/mouse priority, four slots, focus, drift,
  disconnect, Xbox/DS4/DualSense labels, unbound bindings, spell/Rage aliases,
  four Greek face symbols, duplicate suppression, empty-frame clearing and the
  batch bound. It also runs all four existing QTE input regression modes.
- Release runner built successfully. The remaining `u8path` deprecation warnings
  originate in the existing save-backup header.
- The full-chain launcher environment contract passed (64 play-map keys,
  71 variables, 3 effect switches); patch apply/reverse checks passed in both
  the isolated full-chain runtime and the workspace runtime.
- Python pipeline tests: 17 passed. Linux pipeline tests: 7 run, one Windows-host
  skip. This does not validate Linux gameplay.
- Final host captures, not guest-only GS captures, showed Space on the title;
  a deliberately remapped confirmation button showed Y on Xbox, a green triangle
  on DS4 and a neutral triangle on DualSense. These styles were simulated.
- A private copy of the supplied first save loaded into gameplay. The pause
  information window displayed K in its instruction and continue prompts, with
  Ctrl/E on the tabs, matching the custom test map. The original card is not used
  as a writable test card.
- The final `final-moves` smoke reached the Moves screen: K/K for Icarus Ascension,
  G for the heavy-attack hold, the left mouse icon for Orion's Harpoon, and Ctrl
  for Hades Reverse. The collector reported completed/exit 0 and the source card
  SHA-256 stayed `4fe0d4a429b64cd5c0e0a12f6c89e5fd6faffc02f98c53570c4b3432e7341d10`.

Ignored evidence is under `data/control-icons`: `ctest-final.log`, `build-final3.log`,
`pipeline.log`, `linux-pipeline.log`, and the `host_shot.png`/collector reports in
`keyboard-title2`, `xbox-remapped`, `ps4-remapped`, `dualsense-remapped`,
`keyboard-pause2` and `final-moves`. The first pause attempt (`keyboard-pause`)
only reached difficulty selection: the helper had not copied the source card,
and custom keyboard injection could overwrite scripted navigation. It is not
counted as gameplay evidence.

Reproduce the data-free gate:

```powershell
python -I tools/test/control-prompts.py --runtime <runtime>/PS2Recomp/ps2xRuntime --compiler <clang++.exe> --raylib <raylib-source>/src --output <test-output>
```

`tools/test/control-prompts-smoke.py --help` documents the private-card visual
gate. For a first-slot save at the tested altar, use
`--script '5:start,12:abajo*0.15,18:x,24:x,30:x,g4:start' --shot 3000 --seconds 60 --remap --require-gameplay`.
`--style` forces only the scripted rendering family; physical-device detection
must be tested without that override.

## Duplicate button artwork follow-up (`zzz-311`)

The reported Q/R2 overlap was caused by the original Flash draw remaining under
the host overlay. The shared shape hook now suppresses recognized face symbols,
shoulder buttons, their label glyphs and learned backing plates. This applies to
all recognized buttons, independently of the selected device or remapping.
Unknown art, initial frames before host readiness, capacity overflow and direction
diagrams keep the original drawing. Learned plates reset with movie discovery.
The host publishes readiness only after every replacement in its batch has a
valid render target. An initial discovery frame may still contain original art.

The Release build and expanded production-hook regression suite passed. Tests
cover all four face buttons, L1/L2/R1/R2, original label glyphs, pause tabs,
unknown artwork, renderer-not-ready fallback, the 128-item bound, disabled mode
and preservation of direction diagrams even with a learned plate address.
Existing input/remapping tests and all four QTE input regression modes also pass.
Patch apply checks passed against the workspace and isolated full-chain runtime.

Final runner SHA-256:
`8275270e0bed900bc957dfedff7e449a2f58947d48f6495c0aa1f12933835d5a`.
The `visibility-moves` final-host capture shows remapped K/K, G, mouse and Ctrl
instructions plus Ctrl/E navigation without the original PS2 button drawings.
The final `visibility-xbox` capture shows the remapped Y confirmation by itself
on the title screen; the Xbox family was simulated, not physically detected.
The earlier `visibility-altar3` capture confirms Q alone at the altar (runner
`80a587c29568d1aa7b3741f73b68daf716d68ccc86658ce6a0b220917beea1b4`, before
removing investigation instrumentation and tightening batch readiness).
All three collectors completed with exit 0 and the source card hash stayed unchanged.
Ignored evidence: `data/world-prompts/{tests-final.log,build-final.log,
visibility-altar3,visibility-moves,visibility-xbox}`. Earlier `visibility-altar` and
`visibility-altar2` attempts produced no usable host image while minimized;
they are not visual acceptance evidence.

The world-circle investigation found the USA `goMiniGameCircle` name at
`0x2B6D48`, referenced by the show/hide routine at `0x1E0870`. That routine stores
the created child model at creature offset `0x1B8`; it is separate from the Flash
shape hook. Private-card ship and pre-Hydra routes did not reach its active QTE
path. Temporary tracing/RAM-dump instrumentation was removed from the final
runner and is not shipped. This finding does not establish a safe world-model
replacement or combat acceptance.

### Manual combat acceptance

The maintainer offered to test combat manually. Use a runner rebuilt with the
patches, without `GOW_PAD_TEST` or `GOW_PROMPT_TEST_STYLE`:

1. Reach a combat QTE and check each face/shoulder prompt for duplicate PS2 art.
2. Switch between keyboard/mouse and each available physical Xbox, DS4 and
   DualSense; verify that only actual input selects the displayed device.
3. Remap an action, restart as required by the launcher mapping, and check both
   its displayed symbol and the input that completes the QTE.
4. Check rotation/shake arrows, pause/tutorial instructions and return to combat
   for stale icons. Record the disc, enemy/location and a screenshot for failures.

The follow-up `zzz-312` implements the enemy-circle replacement; see its
[implementation, synthetic visual evidence and manual gates](world-control-prompts-2026-11-09.md).

## Remaining acceptance and scope

- A real combat QTE sequence has not been completed with this runner. Synthetic
  symbol/label checks are not end-to-end combat validation.
- The textured 3D circle above enemies (`goMiniGameCircle`) is outside Flash;
  `zzz-312` now replaces its render submissions with a projected host icon, with
  real combat acceptance and depth occlusion still open. Rotation/shake diagrams retain their original artwork to
  preserve the required direction; a generic LS/WASD label must not cover it.
- Controller identity comes from the host driver's reported name. A Sony device
  exposed by Steam Input/DS4Windows as an Xbox virtual pad appears as Xbox.
  USB/Bluetooth hot-switching on physical Xbox, DS4 and DualSense remains untested.
- Regional EU/Japan runners need separately validated hooks; do not apply USA
  addresses to them. No Linux/GPU-tier/performance improvement is claimed.
- This is a host overlay. It preserves prompt-local alpha/color transforms but
  does not reproduce later full-screen guest compositing passes. Background tab
  prompts can appear brighter than the dimmed guest image behind a modal.

Existing installations need a rebuilt runner (`fetch,sync,build` as appropriate
for their pipeline state). Changing the launcher alone cannot enable the hook.
Community requests #20/#29 should not be marked fully accepted from these tests.
