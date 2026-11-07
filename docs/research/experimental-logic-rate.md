# Experimental high logic rate

Date: 2026-11-05. Scope: the USA-code build and its data-only translations.

## Behavior

- `GOW_EXPERIMENTAL_LOGIC_FPS` unset, empty, `60` or invalid: original timestep
  and VBlank wait; invalid values are logged and fall back to 60.
- `120` or `240`: allow the measured game timestep to fall to 1/120 or 1/240 s,
  and replace only the ordinary frame-end wait with a scheduler delay. Late
  deadlines are rebased instead of running bursts of catch-up frames.
- Preserve the original game time-scale factors, upper delta clamp, fixed-step
  path, one-shot fixed step, 30 FPS mode, movies and non-frame wait callers.
- Keep VBlank and audio clocks unchanged. In the experimental mode, host image
  selection follows game flips instead of waiting for a new 60 Hz VBlank.
  This does not create interpolated frames or increase a monitor's refresh rate.
- No launcher setting, persistent boot profile or regional build is modified.
  Do not enable this for the Europe/Japan runtime overlays.

## Reproducing the comparison

From the repository root, after `build.cmd -Stages sync,build,verify`:

```powershell
.\data\_tools\python\python.exe -I tools/test/gs-run-ab.py `
  --runner C:\gow-build-clang\ps2xRuntime\ps2EntryRunner.exe `
  --compare logic-rate --logic-fps 120 --scene ship_guard `
  --pairs 2 --seconds 120 --warmup 60 `
  --output data/experimental-logic-rate/comparison-120
```

Use this copy's actual runner path if its build root differs. Output directories
must be new. The harness alternates 60/120 then 120/60, keeps the same host cap in
both variants, uses real-time input, enables audio and copies private disc/card
roots. It records binary/ELF hashes, effective options, guest FPS, windowed frame
tails, audio counters, simulation-time ratio and checks the original saves.
Scene-gate failures invalidate a performance comparison; retain their evidence.
Equal-frame-index scenes are rejected because they represent different amounts
of simulation time at different logic rates. Capture runs are separate functional
checks (`--capture`), not performance measurements. Use `--logic-fps 240` for the
second experimental rate.

## Validation boundaries

`logic-rate-tests.py` compiles the actual adapter against synthetic state and is
included in `verify`. It checks delta clamps/scales, original fallbacks, scheduling
and opt-in registration, plus presentation token selection. This does not prove
that the original game's actions remain equivalent at a higher rate.

`GOW_DELTA_DIAG=1` measures the sum of the game's timestep against wall time.
A ratio near one is necessary evidence for ordinary real-time speed, not proof
of QTE/combo windows, collision outcomes, scripts, animation events or audio sync.
Guest FPS, host loop frequency and unique images actually displayed are distinct.
No whole-game high-rate compatibility or 120 Hz display validation is claimed.

## Local results

Hardware: Intel Core i5-8265U, approximately 24 GiB RAM, Windows 11. OpenGL
selected **Intel UHD 620**, although a Radeon 520 is also installed. Both attached
displays report approximately 60 Hz. These are laptop results, not Xeon/RX 580
results. Windows were visible at 1280x720, internal scale 1x, VSync off, with audio
enabled and private blank cards. No claim about Linux or 120 Hz scanout is made.

`build.cmd -Stages sync,build,verify` passed: the new 41-case synthetic adapter
suite, 13 CTest groups, guest-call/codegen checks, VU1 backend/self-loop equivalence
and bounded task replay. The comparison-methodology tests and 17 Python pipeline
tests also passed. Patch 73 applies to the captured pre-change sources and
reproduces all four changed runtime files. These checks establish neither
whole-game equivalence nor a performance improvement.

The first attempted two-pair comparison stopped on its original-60 variant:
presentation reporting stopped, the session required forced termination, and
there were no complete post-warmup FPS windows. Its evidence is retained under
`data/experimental-logic-rate/comparison-120`; it is **not a valid benchmark**.
The cause of that presentation stall was not established.

A subsequent **single paired comparison** passed every existing session,
effective-setting, save-isolation and `ship_guard` scene-envelope gate. Both
variants used the new executable and host cap 120, ran 100 seconds and excluded
complete windows overlapping the first 45 seconds. Ten FPS/frame windows were
available in each variant:

| Mode | Guest FPS | Median window p95 | Game seconds / wall second | Audio missing / requested |
| --- | ---: | ---: | ---: | ---: |
| Original 60 | 21.06 | 63.32 ms | 0.980 | 5,125 / 2,400,000 |
| Experimental 120 | 15.60 | 115.20 ms | 0.853 | 15,523 / 2,400,000 |

The candidate was slower in this pair and had worse frame tails/audio counters.
One pair is insufficient for a general causal or statistical performance claim;
it provides no reason to promote the experiment. Passing the encounter envelope
does not mean enemy animation/state or every rendered frame was identical.
Evidence: `data/experimental-logic-rate/comparison-120-retry/summary.json`.

Separate diagnostic pilots then ran for 100 seconds each, excluding complete
windows overlapping the first 45 seconds. All three reached gameplay and exited
with code zero. The following are observations, **not an accepted paired result**:
the old-runner control included late arrival outside the scene envelope, and the
240 pilot used a different host cap.

| Diagnostic pilot | Host cap | Guest FPS | Game seconds / wall second | Audio missing / requested |
| --- | ---: | ---: | ---: | ---: |
| Pre-change runner, original 60 mode | 120 | 15.40 | 0.846 | 7,256 / 2,400,000 |
| New runner, experimental 120 | 120 | 13.17 | 0.748 | 18,281 / 2,400,000 |
| New runner, experimental 240 | 240 | 22.79 | 0.990 | 0 / 2,400,000 |

FPS is duration-weighted over ten complete five-second windows per pilot. Speed
uses separate complete approximately one-second delta windows. Audio uses
complete five-second callback windows; zero missing frames does not prove sync.
In the 240 pilot, one host window reported 196.32 Hz while guest FPS was 21.99:
the host count alone must not be advertised as high-FPS gameplay.

Pilot logs/settings/results are under `data/experimental-logic-rate/pilots`.
Original save inventories matched after every run. Experimental runner SHA-256:
`ef6953696e4b4b8c62887dd7f5a13e02a7adf6129259d0fcd33a07be3c7190ac`.
Pre-change runner SHA-256:
`24975b0ff28611cc49205b5ac0964c177b0b49eae975ca425d6a4b0c35851464`.

A separate 120-mode capture showed Kratos, enemies, ship, rain and HUD rendered
in the opening combat. The image was captured at 17:06:49 UTC, before the user
requested minimization. The test window was subsequently minimized; presentation
reporting stopped and the collector needed forced termination on shutdown
(exit 62097). Keep this session rejected as a graceful-exit check, and do not use
its FPS as a benchmark. Evidence: `data/experimental-logic-rate/captures/candidate120`.
No test processes remained running afterwards. Further unattended runs should
start hidden (`--hidden`) to avoid interrupting the user's desktop, and must be
identified as hidden-window results.

The laptop did not demonstrate sustained 60, 120 or 240 guest FPS in these pilots.
They do not exercise gameplay above 60 FPS, so action/QTE/combo timing, collisions,
animation events, movies and long-session audio sync remain unvalidated at high
rates. Movies were skipped in gameplay runs; their fallback was tested only with
synthetic state. Keep the experiment disabled by default.
