# Paused performance investigation — resume checkpoint

Date: 2026-11-04. Paused at the maintainer's explicit request so the notebook can
be used for other work. **Do not restart tests or builds automatically.** Resume
only when the maintainer asks. [Portuguese summary](retomada.pt-BR.md).

## Read this first

The requested objective remains: stable combat comparisons, lower actual VU1 cost,
better frame pacing and audio, on the i5-8265U / Intel UHD 620 notebook. Use ponytail
full mode and repository contracts. Do not infer notebook performance from the
Xeon/RX 580. There is still **no demonstrated stable 60 FPS or sustained-combat
audio fix**, and no measured power-consumption improvement.

Repository: `C:/Users/NOVETECH/Documents/gow/gow-native-pc`, branch `fix-chore`,
HEAD at pause `8cb44e2342885cafdd908cf75f84e8ffd016fbe7`. This is the actual current
checkout; do not assume the old conversation's Claude branch is checked out.
Read current status before editing; other work may have happened after this note.

The external runtime pin remains `471c83180a8df575cff4abd3fae6c043b5096925`.
The active ordinal patch chain is 01–58 and 66–71. Patches 66/67/68/71 are opt-in,
off by default. Patches 69/70 provide disabled-diagnostic cleanup and measurement
support. The normal runner remains:

`C:/gow-build-clang/ps2xRuntime/ps2EntryRunner.exe`

SHA-256: `bbf74abfb8971e3b8d526a92fdedb5aeac4640b788a19601729734d7272bee7b`.

No experimental scalar or encounter-anchor code was installed into that runner.
The three runtime source files changed during this investigation were restored
byte-for-byte from their pre-experiment copies. The rejected temporary scene was
removed from the live game profile. Drafts are preserved below, **outside
`engine/patches`**. Do not automatically apply them during fetch or packaging.

The verify build directory currently contains the experimental scalar runtime
library/replay executable. Its sources have been restored, so rebuild it before
using it as a reference. Prefer the immutable copied reference executable listed
below. No source commit, push, release or deployment was performed in this turn.

## Completed before this pause

- Patch 70: guest-frame input/capture times, frame-window markers, bounded
  pad-observed interval metrics, and exact-window requested/missing audio snapshots.
  The rendered arrival is repeatable; that does not establish repeatable combat.
- Patch 71: optional JIT chain adapter. Final same-binary isolated cost improved
  only 0.39%; JIT-only arrival averaged 52.263 / 52.621 FPS, but p95 worsened and
  p99 had an outlier. Keep it off. The ordinary hybrid arrival uses AOT and did
  not execute this adapter. See [full prior results](vu1-chain.md).
- The installed baseline previously passed Release build/full verify, including
  13 CTest groups, randomized VU1 equivalence and self-loop budget/depth exits.
  **That validation does not cover the new drafts.**

## Work performed in the interrupted follow-up

### 1. Combat pilot: rejected, with useful diagnostics

The `ship_combat_corner` pilot moved left/down at arrival-relative frames 600–780,
then held guard. Measurement was frames 1200–1800, with the existing 25-unit
trajectory tolerance, god mode and an active first encounter. Both runs used the
same reference binary, private blank cards, audio on, hidden windows and captures.

Both reached gameplay and exited gracefully; original save inventory checks
passed. The second run failed `same_scene`. Do not widen the tolerance or report
their FPS as a performance comparison. One run also had an intrusive 20-second
sampler attached, so these sessions were diagnostic, not benchmarks.

The captured image was inspected: Kratos and several attacking soldiers are
rendered on the ship, rather than an FMV, paused menu or empty arena. Player
positions still drifted. At frame 1500, the first run was near
`1435.3,40.5,1906.8`; later in the second run the player remained near
`1506.6,51.6,1979.6`. Full frame-indexed traces, rather than these differently
timed examples, drive the rejection.

The existing gameplay-start marker fires at state 11 during the arrival animation.
Thus equal frame numbers need not identify equal encounter progress. A candidate
next anchor is the observed landing/encounter position near `1530.2,49.8,1973.7`,
after at least 300 arrival frames, with a narrow initial position tolerance.
**This is a hypothesis; anchoring alone may not remove enemy/physics drift.**
Do not change simulation delta, RNG, enemy behavior or audio clocks merely to
force a benchmark to pass.

Evidence under `data/vu1-combat-followup/`:

- `corner-pilot/summary.json`, per-run `settings.json`, `session/runtime.log`,
  captures and `saves-before.json`;
- `corner-pilot.log` preserves the failed gate;
- `corner.png` is a local inspection image, not a distributable asset;
- [rejected profile](drafts/rejected-corner-fixture.toml) preserves exact inputs.

### 2. VU1 sampling: chain remains a target

`corner-sampler.txt` sampled only the owned test PID. `chain-samples.json` resolves
instruction addresses using `runner-symbols.txt` and `chain-disassembly.txt` from
the exact reference executable. The VU1 worker had 6562.500 ms CPU time over
19903.739 ms observed time: about **32.97% of one logical core**. Wall instruction
samples included **29.14% in `chain`** and **2.69% in `blockTiming`**.

These are not self-time percentages and cannot be added to CPU utilization.
The run was intrusive and not a same-scene comparison with earlier sampling.
Hot locations include history stores, successor-slot checks, lane-mask updates
and flag-tail setup. This supports investigating chain bookkeeping instead of
assuming another JIT call-site inline hint will solve the bottleneck.

### 3. Scalar scheduling outline: promising CPU experiment, not accepted

Draft: [vu1-scalar-outline.patch](drafts/vu1-scalar-outline.patch).

Only `PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_native.inl` changes. The common
`finishBlockTiming` history update stays inline; scalar scheduling loops move to
an out-of-line helper using the existing `VU1N_NOINLINE` macro. It preserves calls
to `scalarStart`, their ordering, issue cycles, latencies and the existing scalar
pipeline discriminator. The intent is to keep the scalar loop's register/stack
requirements out of every chain call. No arithmetic, clock or generator changes.

The helper uses inferred template types to avoid adding a declaration involving
private runtime types to the widely included native header. Review this choice
before promotion; it is a local extraction, not a general framework.

Built `gow_vu1_tasks` and `gow_vu1_x64_fuzz_test` successfully. The latter was
**built, not executed** in this follow-up. Five alternating replay pairs, each
with 32 identical captured tasks and 100 repetitions per record, gave:

| Pair | Reference sum of warm medians (us) | Candidate (us) |
|---|---:|---:|
| 1 | 561.8 | 514.7 |
| 2, reverse order | 600.6 | 507.8 |
| 3 | 587.4 | 517.5 |
| 4, reverse order | 535.5 | 494.2 |
| 5 | 532.6 | 502.2 |

Median run sums: **561.8 -> 507.8 us (-9.61%)**, all five pairs favorable.
All records matched their native captured baseline and block accounting across
all ten runs. This is isolated **JIT replay CPU cost**, not 9.61% more gameplay FPS.
The test executable does not establish the game's shipped AOT workload. The cost
level differs from earlier sessions; compare only within these pairs. A second
independent repetition, broader equivalence and gameplay validation remain open.

Local evidence: `scalar-build.log`, `scalar-replay-ab/summary.json` and per-run logs.

| Input | SHA-256 |
|---|---|
| `replay-reference.exe` | `ed31593a79b93d9f130c73b3c46fb2ef04c35ebbfe880f3d6f64cce8f8fbfaad` |
| `replay-scalar.exe` | `1553d9c9755584dd25f80c636fa9089b29b892df3c20684691106e89e6b7497a` |
| Corpus | `70432627a7c5a3417b5b57008cc4a36f27476044e54c9177296a9d58a46ad94b` |

The corpus is `data/scene-bottleneck/task-capture/01-countdown-0/tasks.bin`.
It contains game-derived data: keep it local/ignored, never package or upload it.
Immutable executable copies and source snapshots remain in
`data/vu1-combat-followup/`; do not overwrite these evidence files on resume.

### 4. Encounter-anchor draft: incomplete and untested

Draft: [encounter-anchor-incomplete.patch](drafts/encounter-anchor-incomplete.patch).
This was started just before the maintainer requested a pause. It was **not built
or tested**, is not in the ordinal chain and is not active in the runtime sources.

It proposes `GOW_TEST_FRAME_ANCHOR=x,y,z,tolerance,minimumArrivalFrame`, only inside
`GOW_PAD_TEST`. It observes the existing position vector at `0x2C7790`, state 11,
pending=0 and movie=0. On the first match, it resets only the test frame origin;
wall/`g<seconds>` times and actual guest state stay unchanged. Before matching,
frame-relative inputs/captures and frame windows wait. Remaining absolute menu
confirms must still stop at the original gameplay marker. Pre-anchor trace frames
use an out-of-range sentinel so they cannot masquerade as anchored frame zero.

Missing work before it can be tested:

1. Review/harden parsing, invalid input diagnostics and finite/bounded values.
2. Add profile fields and harness environment wiring; none exists yet.
3. Require exactly one effective anchor marker, correct position/minimum frame,
   and the same frame/state/zone/trajectory gates. Timeout must fail, never silently
   fall back to the old origin or accept menu/intro footage.
4. Add isolated anchor/parser/clock tests and methodology tests for missing,
   duplicate, invalid and premature markers, including pre-anchor trace exclusion.
5. Build reference instrumentation first and validate identical-binary combat
   repeats. Inspect captures separately from timed sessions. Only then compare
   an optimization with identical instrumentation in both variants.

## Open bugs, uncertainties and tasks for other AIs

| Priority / work item | Evidence or symptom | Required outcome |
|---|---|---|
| P0 — combat fixture drift | Both old guard and new corner pilots fail trajectory gates; arrival origin includes the intro | Complete/review the anchor, then three matched reference pairs with active enemies and unchanged gates. If it fails, log the cause and reject the timing. |
| P1 — real VU1 chain cost | Repeated samples concentrate on bookkeeping; scalar-outline replay is promising | Review exact scalar semantics, repeat isolated replay, run random/DLL/JIT/self-loop tests and full verify, then matched hybrid gameplay including p95/p99/audio. |
| P1 — sustained audio starvation | Earlier long sessions had missing/dropped frames; short arrival has zero missing in both modes | Reproduce on accepted combat fixture; correlate sound production, device drain, IOP drift and long frames. No blanket buffer increase or guest-clock change as a substitute for a cause. |
| P1 — prolonged slowdown | Some earlier runs slowed with GPU load falling, not rising | Measure clocks/thermals and competing system load without changing the user's power plan or terminating other workloads. Separate CPU, GPU, driver waits and power limits. |
| P2 — GPU saturation | UHD 620 can remain near 99% in short scenes | Accepted same-scene resolution sweep; distinguish busy percentage from GPU frame latency/watts. Do not trade FPS for lower utilization and call it an optimization. |
| P2 — incomplete telemetry | Exact dropped-audio counter is unavailable; pad intervals are not presentation latency | Add bounded counters only where needed, preserve null/unavailable values and collector privacy. Do not relabel pad metrics as GPU latency. |
| P2 — experimental renderer regressions | 66/67/68/71 did not pass all performance/tail gates | Keep opt-in. Validate separately and on AMD/NVIDIA before public defaults. |

These are research/acceptance tasks, not all proven engine defects. In particular,
GPU busy=99% by itself is not a bug, and improved isolated CPU time is not gameplay
acceptance. An AI reviewing one item should return its diff, exact reproduction,
checks performed, raw metric definitions and remaining limitations. Do not ask it
to merge several unmeasured optimizations or remove reference paths.

Independent reviews can cover anchor correctness, scalar semantics and audio
tracing. **Do not run concurrent build/pipeline writers or performance sessions in
this checkout.** Integration and machine measurements must be serialized.

## Safe resume sequence

1. Confirm the maintainer has requested resumption. Read `AGENTS.md`, this note,
   current `git status`, runtime pin/patch list and the runner hash. Preserve any
   newer user edits; never reset the entire runtime to discard one draft.
2. Recheck installed/default settings and original save inventories. All game
   sessions must continue using `gs-run-ab.py` private disc/card roots; never pass
   the player's card to a diagnostic runner.
3. Complete the anchor draft and its tests, or reject it with evidence. Establish
   combat repeatability before an FPS comparison; keep the existing arrival
   fixture as a separate regression check.
4. Review scalar-outline independently, apply it only to the intended runtime
   baseline and rerun isolated replay/equivalence. Reserve a new ordinal patch
   number only once scope and validation are clear; 72/73 were not assigned.
5. If the runtime change is retained, export it as an ordinary patch and run
   `build.cmd -Stages fetch,sync,build,verify`. Keep immutable reference/candidate
   runners with matching test instrumentation. Exclude compilation, sampler and
   capture from the paired FPS sessions.
6. Require three alternating matched gameplay pairs and no regression in p95/p99,
   missing/dropped audio or correctness. Follow with visible play/listening and
   independent GPU tiers before any support claim or default promotion.
7. Update this checkpoint, the roadmap and tested-hardware notes with actual
   results. Preserve rejected attempts rather than replacing them with favorable
   subsets. No universal 60-FPS or "1000%" claims.

Example isolated replay command after explicit resumption, using a **new** output
directory and the saved executables (no game launch or card access):

```powershell
python -I tools/test/vu1-task-ab.py --reference data/vu1-combat-followup/replay-reference.exe --candidate data/vu1-combat-followup/replay-scalar.exe --corpus data/scene-bottleneck/task-capture/01-countdown-0/tasks.bin --output data/vu1-combat-followup/scalar-replay-repeat
```

At pause there were no remaining test runner, sampler or task-replay processes.
The original save checks passed in both new game sessions. No background build or
automatic continuation is scheduled by this checkpoint.

Checkpoint checks: both saved drafts pass `git apply --check` against the restored
runtime sources (without applying them); all three restored files match their
pre-experiment copies byte-for-byte; the installed runner hash is unchanged;
the temporary profile has no remaining content diff; `git diff --check` passes.
These are preservation/applicability checks, not compilation or semantic validation
of the incomplete anchor draft.
