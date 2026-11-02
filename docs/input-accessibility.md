# QTE input assistance

Launcher > Accessibility provides two independent, optional input assists. Changes
apply on the next game launch; both are disabled by default.

## Keyboard/mouse left-stick gestures

Select **Keyboard/mouse stick assistance** > **Left / right** for an alternating
horizontal gesture, or **Circle** for a full rotation. While the game requests
that gesture, hold **G**, then release it as soon as the prompt ends. Remap
**Hold for QTE stick gesture** in the keyboard/mouse bindings to another key or
mouse button if preferred. Existing saved keyboard layouts receive the new G
binding if G is free; otherwise assign a free key manually in Controls. The Controls page's binding editor marks conflicts with other actions.

The gesture replaces the left stick only while held. Releasing it restores
normal movement immediately. The right stick retains its usual mapping. Focus
loss stops the gesture. A connected gamepad in any of the four slots keeps its
ordinary sticks; this feature does not change controller input. Automated pad
smoke tests ignore the gesture setting.

This is manual assistance, not detection of grabs, petrification or other QTEs.
It can move Kratos if held during ordinary gameplay. Match the gesture to the
on-screen instruction; directional/partial-circle puzzles may still require
manual directions. Escape from each enemy grab and Medusa petrification still
requires in-game validation; synthetic input tests cannot establish success.

## Hold instead of repeated presses

Enable **Hold instead of mashing** and choose the face-button group. L1, L2, R1
and R2 have separate opt-in switches below it. They refer to the game's PS2
actions, so their keyboard/mouse and remapped controller equivalents also work.
Only a selected button that the player holds is repeated; this does not press
all selected buttons together. Short presses remain single presses.

Leave shoulder switches off unless a prompt needs repeated presses: repetition
can interrupt blocking, charging, opening a chest or another held interaction.
All repetition pauses while pressing multiple buttons (patch 58), including
face buttons, so R2 + Cross stays held even with the full face group enabled.
Shoulder repetition also pauses while moving either stick. Releasing the other action
restarts the repetition delay. The rate selector applies to all selected buttons.

## Keyboard combinations and crates

The default **Ctrl** binding is R2. **Ctrl + WASD** keeps R2 held and moves the
left stick; **Ctrl + Space** keeps R2 and Cross pressed together. **Alt + WASD**
is now the dedicated evade combination. Existing layouts that used the old
shared Ctrl default migrate the evade modifier to Alt; other custom evade
bindings remain unchanged. If Alt is already used, the migrated evade modifier
is left unassigned; choose a free key in Controls. Controls highlights conflicts.

Patch 57 gives gameplay buttons priority over a shared evade modifier, including
left/right Ctrl aliases. The input layer no longer drops the held button or
redirects movement into a roll. Synthetic tests verify these exact combinations;
completion of the opening ship's crate scene still needs a gameplay check.

## Texture packs and future modifications

Accessibility also contains **Texture packs and visual mods**, moved from
Graphics. Choose the existing PCSX2-format pack folder and enable its switch.
The same saved folder and enable flag are retained; moving the controls does
not install, modify, upload or redistribute any pack. This is a home for future
mod controls, not a claim that a general mod manager is implemented.

## Implementation and checks

Patch 56 extends `runtime/gow_qte_hold.h` with time-based left-stick gestures:
four left/right cycles per second or two circular rotations per second. The
configurable input action is `qte_stick` in `TOBIICHI_TECLAS`; `GOW_QTE_STICK` is
`shake` or `rotate`, with absent/unrecognized values disabled. `GOW_QTE_HOLD`
continues to carry the selected action names, including optional shoulders.

`tools/test/qte_hold_test.cpp` checks shoulder isolation and short presses,
gesture direction coverage at 30/60 Hz, identical repeated reads, release,
disabled behavior and restart phase. The `verify` stage includes this suite.
`tools/test/qte_input_test.cpp` exercises the production pad reader with a fake
host: keyboard and mouse gestures, all four controller slots, focus loss,
scripted-test exclusion and independent shoulder repetition. It is also in
`verify`. `python -I tools/test/qte-controls.py <Qt bin/qml.exe> <compiler bin>`
checks the actual Accessibility and Controls QML, saved choices, texture-pack
enablement and migration of older key maps.
