# Keyboard rotation QTEs: continuous sweep along the guide (`zzz-329`) — 2026-11-13

## Report

[Issue 34](https://github.com/Vnnc1/gow-native-pc/issues/34): a player pressed the keys of a rotation QTE and the
game judged it wrong. The screenshot shows a counter-clockwise half-turn arrow with the `zzz-317` guide
`1 S > 2 D > 3 W`, which matches the arrow. The keys were right; the way they reach the game was not:

- Keyboard stick axes are digital (`eje()`: 0/128/255). Tapping S, then D, then W sends down, **centre**, right,
  **centre**, up. A thumb on a stick never passes through the centre while turning. The guide's numbers and `>`
  arrows invite exactly those separate taps.
- The Accessibility "Circle" gesture (`GOW_QTE_STICK=rotate`, patch 56) always turned clockwise from the right, so it
  went the wrong way for this counter-clockwise prompt.
- At 15-20 guest FPS (weak notebooks) the game samples the stick 15-20 times per second; quickly rolled keys can skip
  the diagonal between two cardinal directions.

The game's own rotation check was not reverse-engineered (the generated code carries no symbol names), so "a centred
stick breaks the turn" is the strong hypothesis that fits the report, not a traced fact.

## Change

`gowIconosFrame` already publishes the frame's automatic-button request; it now also publishes the frame's rotation
guide (keys in numbered order) under the same mutex and 250 ms staleness. `turnOf()` derives the screen direction from
the first two keys (up/right/down/left are clockwise order).

While a guide is fresh, the keyboard left stick goes through `gow_qte_prompt::KeyboardSweep`:

- the first pressed key places the stick at that direction at full deflection;
- each new key (or diagonal) becomes a target; the stick moves there at 900°/s (half turn 0.2 s, full turn 0.4 s)
  along the shorter way, and along the guide's way when the target is opposite (S then W turns through D for this
  arrow), so every game read sees an intermediate angle;
- releasing all keys keeps the stick out for 250 ms after the target is reached, so taps work; then it centres;
- outputs depend on time only, so the two pad readers of one frame agree; one mutex guards the state.

The held `qte_stick` gesture receives the guide's turn and first key as its start. Its defaults reproduce the previous
samples exactly. With the gesture set to "Circle", the guide also shows that key (its own label, keyboard or mouse)
under an open-circle mark, centred below the sequence.

Unchanged: input outside a recognized guide, gamepads (all four slots), the Alt evade stick, focus loss, scripted
`GOW_PAD_TEST=1` sessions, unknown/wiggle diagrams. `GOW_QTE_KEY_SWEEP=0` keeps raw digital keys. Nothing is pressed
on the player's behalf: with no key held, the sweep only finishes the turn the player started.

## Checks

- `qte_hold_test` (in verify): original gesture samples unchanged; guided counter-clockwise start and direction;
  `turnOf`; tapped S/D/W at 15/20/30/60 Hz never centre, pass the diagonal and make one 180° counter-clockwise turn;
  same-time reads agree; opposite key turns the guide's way; grace and release; no guide = raw keys; clockwise guide;
  turning against a guide reaches the shorter target. 70/70 cases.
- `qte_input_test` off/shake/rotate/smoke through the production `tobiichiSticksTeclado`: released guide key stays out,
  next key sweeps through the diagonal, no guide centres at once, held gesture starts at the guide's first key and turns
  counter-clockwise; scripted mode keeps raw keys. 20/20 cases per mode.
- `control-prompts` (production extraction, six modes): the frame publishes the guide in numbered order and clears it
  with the next frame; the hold-key label follows the binding. Visibility, world-prompt and QTE-symbol suites pass.
- Real `gow_iconos.cpp` and `ps2_pad.cpp` compile with the runtime's flags; the 143-patch chain applies; `fetch,verify`.

## Not validated

No game run: an actual rotation QTE (this ship scene, Cyclops/Minotaur finishers, full turns) with keyboard taps, held
rolls and the "Circle" key, at 60 FPS and on a slow notebook, remains the acceptance gate. If the game turns out to
require several turns or a faster turn, tune `kDegreesPerSecond`; do not add automatic turning without a key held.
