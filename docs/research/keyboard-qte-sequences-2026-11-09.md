# Keyboard QTE sequences and opt-in automatic buttons

## Behavior

Patch `zzz-317` replaces the undifferentiated movement-key cross beneath the six
recognized rotation diagrams with a numbered left-to-right sequence. Labels use
the production `li_arriba/li_der/li_abajo/li_izq` mappings and last-active-device
selection. Full turns show five positions, closing the circle; half turns show
three. The original animated arrow remains visible. Gamepad artwork is unchanged.

The launcher adds **Accessibility > Automatic QTE buttons**, default off and
requiring restart. `GOW_QTE_AUTO=1` generates a 60 ms press / 60 ms release for
one uniquely recognized Greek face-button or R2 prompt. It responds to a new
button immediately and repeats while that prompt remains. It operates on guest
button bits, so remapped keyboard/controller bindings do not change the action.
World enemy indicators, ordinary tutorial/menu buttons, unknown art, conflicting
button batches and stick movements are not automated. It does not initiate a
finisher. The UI states these limits; this is not an all-QTE completion cheat.

## Recognition and safety

Inspection of an existing private guest-memory capture confirmed that opposite
rotations share their leaf meshes. Selecting the first matching symbol name would
silently confuse directions. The scanner now retains named sprite descriptors.
A bounded lookup follows the USA Flash instance ancestry, only at leaf return PC
`0x1478A0`, with the saved caller `0x1474F0`, verified sprite vtable `0x2BF4C0`,
movie ownership and valid memory ranges. It reads the existing guest stack rather
than keeping a host call stack across generated-function yields/resumes. At most
16 ancestors are examined. Ambiguous/invalid identities retain original drawing.

The six named exports were found in the local captured HUD. The half-arrow mesh
runs local +X -> +Y -> -X; full arrows use one winding and its mirrored transform.
The guide uses the final drawing matrix, not the CW/CCW text alone: the asset
matrices contain reflections and rotations. This also preserves direction when
the artwork is transformed. Nonfinite/degenerate matrices produce no sequence.
A complete guide must fit the existing 128-icon batch, and composite leaves share
one guide. Unknown wiggle diagrams retain their original animation; this change
does not claim a directional sequence for those assets.

Automatic presses only consume exact named Greek button identities, never color
alone or the world-circle hook. Complete guest-frame publication includes empty
batches. Missing publication expires after 250 ms; focus loss, disabled mode and
multiple requested buttons preserve manual input. Existing F1 menu input blocking
still applies. Scripted `GOW_PAD_TEST=1` sessions disable automation. The shared
snapshot and assist state are protected by one short mutex; no guest state is
modified to skip a QTE. Saves and settings migrations are not involved.

The setting is connected through QML persistence/reset/play map, the runtime
reader, both collector allowlists and mod environment validation. All nine UI
languages include the new option and its scope.

## Checks

- Production input/prompt suite: default/classic/custom mappings and automatic
  mode; all four existing QTE input modes; visibility/capacity; world projection.
- Sequence fixtures cover all six sprite transforms, remapped movement labels,
  mirrored direction, full/half length, invalid matrices, unknown identity and
  complete-batch publication. Automatic-input tests cover press/release timing,
  requested-button changes, repeated reads, stale/empty/conflicting requests,
  focus loss, disabled mode and the production pad backend.
- Production scanner/ancestry tests cover caller, stack, vtable, ownership,
  bounds and parent cycles. An optional ignored local memory capture confirms
  discovery of all six named sprites; no game-derived fixture is committed.
- Real QML Controls/Accessibility binding test passes, including persistence of
  the new toggle in both directions. Launcher environment and language checks pass.
- Hidden GPU artwork preview rendered and inspected, including all six ordered
  guides using the production texture and marker code. This is not a combat test.
- Release launcher/helper build passes. The first build lacked Qt tool DLLs on
  PATH; supplying the existing compiler/Qt paths fixed it. The first collector
  test invocation from the build folder also lacked DLLs; all 15 tests pass
  against the deployed helper, including the new environment-report check.

Evidence remains under ignored `data/qte-sequence-auto/`. Real combat QTE timing,
all other gestures, physical controllers and regional runners still require
manual acceptance. No FPS claim is made from these checks.


## Deployment

Normal fetch/configure/sync/build succeeded against the owned installed runtime.
Launcher inspection selected the existing PT-BR edition and updated runner.
A 65-second private-card load smoke passed with normal exit 0. The ship-altar
capture was generated for visual inspection; this does not exercise combat QTEs.
All 11 protected files, save-history inventory, launcher registry settings and
existing boot profile remained byte-identical. Automatic QTE remains off by default.
Backup: `C:\Users\dzvini\Documents\gow-test-backup-qte-20261109-231658`.

- Runner SHA-256: `1061499fd7db3cc7eb9a3f15a0a7aad709ec856ec727303179cebda8a338a6a4`.
- Launcher SHA-256: `793d19384dc5d6251c8746a6e31f2b3407a78d23ba4b5fd5effa8c2857123a3e`.
- Collector SHA-256: `8a90884f0dcac8fc3b8304d186ba9ec9d7d7c9c8850e0445204da7f3284ae942`.

Preservation results: `data/qte-sequence-auto/deployment/validated.json`.
