# Reproducible combat scenes on slow machines: test-only fixed step (`zzz-328`) — 2026-11-12

## Why the encounter anchor was not enough

The paused encounter-anchor draft (`render-delivery-2026-11-04/drafts/encounter-anchor-incomplete.patch`) resets the
frame origin when Kratos reaches a known position. The 2026-11-11 `ship_arrival_frames` pair on the i5-8265U shows the
origin was already aligned: frame 0 was identical in both runs (`1527.5, 35.3, 1886.1`), yet the trajectories drifted
by 5 units at frame 60, 14 at frame 120 and 88 at frame 240. The game's step function (`0x17D778`) turns the elapsed
fields (`0x29C670`) into each frame's delta (`0x29C64C`), so at ~20–26 guest FPS every frame simulates a different
amount of time and identical frame-indexed input produces different motion. The anchor fixes a different problem and
stays a draft.

## Change

`GOW_TEST_FIXED_STEP=1`, only together with `GOW_PAD_TEST=1` and the original 60 Hz rate, registers the existing
logic-rate step adapter and writes a 1/60 s delta (and the scaled delta with the game's own scale factors) for every
measured gameplay frame. Movies, the game's own fixed and one-shot steps, incomplete/resumed calls and the
experimental logic rate keep their path; the frame wait stays the original VBlank wait. The marker
`[gow-logic-config] ... fixed_step=N` is printed at start. On a slow machine the game then runs slower than real time:
the FPS measured is the throughput of an identical workload, never a player setting.

`gs-run-ab.py --fixed-step` sets it in both variants, rejects runs without the `fixed_step=1` marker and cannot be
combined with `--compare logic-rate`.

## Validation

- `tools/test/logic-rate.cpp.in` (in `verify`): 57 cases now, adding fixed step for six tick values, the six
  original-path exceptions and registration rules (needs `GOW_PAD_TEST=1`, ignored with `GOW_TEST_FIXED_STEP=0`
  and with `GOW_EXPERIMENTAL_LOGIC_FPS=120`).
- `fetch,sync,build,verify` passed (18/18 CTest groups); the PGO profile stayed applied (`code` fit, 2 of 380
  recompiled functions without data).
- Identical-binary repeat, i5-8265U / UHD 620, visible, audio, 1x, grouping on, `ship_frames` (combat frames
  240–840), `--fixed-step`, 2 pairs, runner `data/experiments/runners/fixedstep-zzz328/`:
  **4/4 runs valid; trajectory deviation 0.000 units at every sampled frame**. This scene was a rejected pilot.
  Guest FPS 34.7 / 32.5 / 33.6 / 34.6, p95 50.8–54.5 ms. The same binary therefore spreads about 6 % on this
  notebook: smaller differences need more pairs. Evidence: `data/experiments/fixedstep-repeat-20261112/`.

## Limits

Trajectory samples are every 60 frames; identity there is not a frame-by-frame or audio equivalence proof. Fixed-step
FPS is not real-time play speed. Other machines, other scenes and runs started from a card remain to be checked.
