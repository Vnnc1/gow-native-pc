# Movies flashing the last gameplay frame (`zzz-331`) — 2026-11-13

## Report

Manual test of the 0.6.1 setup (player install, PT-BR disc, RX 580, Xeon E5-2666 v3): the opening movie "flickers
between video and game", sometimes with black frames. Earlier sessions of the same player skipped movies, so the
problem was not visible there.

## Reproduction

The player's own runner and boot settings (`gow-native.boot`: 2x, AF16, texture pack, FXAA, fullscreen, window FPS
limit 0, detailed diagnostics), private card/saves copies, new game, opening movie A01MP02, 100-150 desktop captures
per burst (~25/s), luminance per capture:

| Variant | Old-frame captures |
| --- | --- |
| Player settings | 11/100 |
| `PS2X_GS_DIRECT_PRESENT=0` (RAM presentation) | 23/100 |
| Texture pack off | 20/100 |

The old frame is always the same dark gameplay picture. The host presentation counters show no blank or missing
acquisition, so the published GS frames themselves alternate.

## Cause

`GOW_GS_HW_DISPLOG`: during the movie only read circuit 2 is enabled and DISPFB alternates between fbp 104 (`0x1468`)
and fbp 208 (`0x14d0`); gameplay displays fbp 208 (`0x94d0`, CT24). `GOW_GS_HW_RTDUMPAT=32` with `RTDUMPFBP=104`
dumped one movie picture per frame into the 104 target (640x448 at 2x); the same instant with `RTDUMPFBP=208` dumped
nothing: the movie never draws the 208 target. Target 104 (fbw 10, 448 rows) covers the first block of fbp 208.
`Present` drew whatever target matched the displayed FBP, so every 208 flip showed the last gameplay frame (or
nothing, i.e. black, when no 208 target existed).

## Change

`displayTarget(fbp)`: when the displayed target was not drawn during the last 16 presents (~0.27 s) and another target
drawn in that window covers the displayed buffer's first block (excluding targets overwritten by depth), present that
target. A first draft used a one-present gap and also fired in gameplay at 45-50 FPS (gameplay draws an intermediate
pass into 104): rejected before release. `[gs-hw-display] N of the last 300 presents showed fbp=X for the stale
displayed fbp=Y` is printed per ~5 s window only when the rule applied.

## Validation

Runner built from fix-chore `ccc8b9b` + `zzz-331` with the shipped PGO profile, player settings minus detailed
diagnostics, 170 s (opening movie, then ship gameplay):

- Opening movie: 0 old-frame and 0 black captures in 150 (two remaining luminance jumps are cuts in the movie itself).
- `[gs-hw-display]`: 20-33 substitutions per 5 s window during the movie only; none in gameplay (75-165 s, 45-60 FPS).
- `fetch,verify` with the 144-patch chain: EXIT=0, 18/18 CTest groups, VU1 equivalence, launcher language and environment contracts.

Not validated: other movies (only A01MP02), NVIDIA/Intel GPUs, regional builds, the software renderer (unchanged).

## Related performance observation (same session)

Ship opening after the movie, player's runner (tune build with native VU1), same scene: detailed diagnostics on 42-46
guest FPS; off 51-53; also without continuous VU1 recording 51-52; at 1x without AF 51-54. The remaining limit is the
VU1 (CPU) in this heavy storm section on this machine, not the GPU. Players should keep "Performance diagnostics" off
except when producing a report.
