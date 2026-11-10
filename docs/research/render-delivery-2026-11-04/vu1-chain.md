# Frame-aligned scenes and VU1 chaining (2026-11-04)

## Scope

Same i5-8265U / Intel UHD 620 notebook. Hidden, bounded tests use private blank
cards and copied executable/index/module inputs. Only known PAK inputs are linked.
No original card/save writes, power-plan changes or termination of other workloads.
Patches 66/67/68 stay disabled; 69 stays enabled in both compared binaries.

## Scene control (patch 70)

`f<N>` script/capture timestamps use the existing configured guest frame counter.
Their hold duration is measured in guest frames; wall-time and `g<seconds>` inputs
keep their previous behavior. Remaining menu confirms stop once a frame-relative
script reaches gameplay. A zero-length frame press injects no gameplay input.

The runner emits exact begin/end frame markers and observes consecutive guest
frames at pad reads. These intervals are **pad-observed frame intervals**, distinct
from the existing frame-function interval distributions and GPU/display latency.
The bounded observer reuses `FrameWindow`; the harness rejects skipped frames,
missing boundaries and windows longer than its 4096-sample capacity. Audio uses
monotonic requested/missing-device-frame snapshots at those boundaries. Callback
sampling can straddle a boundary by one device callback; it is not an audible-quality
assessment. No audio queue size, mixing rate or guest clock is changed.

The previous five-second windows can be absent in a short scene. They remain
reported separately; absence no longer masquerades as zero missing audio or a
complete frame distribution. Exact-window dropped-audio counts are unavailable
and reported as null; available five-second drop counters stay separately labeled.

The initial 240-840-frame combat pilot matched much of the path, but diverged near
the arrival jump and later enemy knockback. It was rejected. The selected control
is the rendered ship arrival, frames 0-360, before combat: an active engine scene,
not an FMV or inventory pause. The harness compares positions at the same 60-frame
milestones, within 25 game units, and requires the same frame keys, gameplay state
and allowed ship zones. This is a first-visit arrival benchmark, not a sustained
combat or whole-game performance claim.

## Candidate (patch 71)

Clang previously compiled the JIT's `chainFn` adapter with a call to the full
`VU1NativeAccess::chain` body. The candidate uses a separate adapter with a call-site inline hint, removing that
second call/stack frame per chained block. `GOW_VU1X_CHAIN_INLINE=1` opts in; the
default stays on the original adapter. The JIT selects the call target while
compiling each block, with no mode branch in the executed chain. It keeps
the exported AOT/DLL ABI, all register arithmetic, flags, lane checks, cycle budgets,
stop/depth checks and history accounting. No generator or JIT instruction semantics
change. The compiled adapter was inspected to confirm the body is inlined.

Reference and candidate receive the same patch-70 instrumentation. The final
comparison toggles the adapter in one binary. The initial experiment used separate
binaries; its numbers below are preserved separately. Runtime/executable
and corpus hashes are recorded, with alternating 0/1 then 1/0 order. The isolated
replay uses identical tasks and checks each backend against its captured baseline;
native and exact baselines are not assumed equal. Neither a replay speedup nor a
short arrival result alone justifies a universal 60-FPS or audio-quality claim.

The opt-in call-site hint follows the [Clang statement attribute documentation](https://clang.llvm.org/docs/AttributeReference.html#always-inline-force-inline).
The original chain implementation and exported entry point remain unchanged.

The first final-binary hybrid arrival was rejected: no JIT adapter marker appeared,
because this scene was covered by AOT blocks. This exposed an important scope limit:
patch 71 cannot accelerate an AOT-only scene. The final `vu1-inline` comparison
therefore explicitly forces JIT-only in **both** variants and verifies both the
registry-clear and adapter markers. These are JIT validation runs, not the shipped
hybrid configuration. The rejected attempt remains in `arrival-optin-ab`.

## Initial experiment (before making the candidate opt-in)

All three frame-aligned arrival pairs passed the state/zone/trajectory and save
checks. Each observed exactly 360 consecutive frames:

| Pair | Reference FPS | Candidate FPS | Reference p95 / p99 ms | Candidate p95 / p99 ms | Missing audio frames |
|---|---:|---:|---:|---:|---|
| 1 | 55.092 | 55.380 | 26.113 / 30.447 | 23.303 / 26.992 | 0 / 0 |
| 2 (reverse order) | 51.796 | 52.554 | 30.277 / 33.462 | 26.327 / 69.802 | 0 / 0 |
| 3 | 53.116 | 54.111 | 28.164 / 32.736 | 24.921 / 33.218 | 0 / 0 |

The p99 outlier in pair 2 blocks default promotion despite the improved FPS/p95.
On the identical local 32-task corpus, five pairs of 100 repetitions produced
median summed warm times of 482.6 us reference and 462.9 us candidate (-4.08%).
Four of five pairs favored the candidate. All task baselines and native-block
counts matched. This is isolated CPU execution cost, not a 4.08% gameplay FPS gain.

The short arrival has no missing audio in either mode. It cannot demonstrate
that previously reported long-combat audio failures are fixed. GPU engine load
was near saturation; short-run CPU samples can be unavailable and stay null.

## Final opt-in binary: isolated CPU result

Five alternating pairs on the same executable and identical 32-task corpus gave
median summed warm times **460.4 us off / 458.6 us on (-0.39%)**. Four pairs favored
the candidate, but the change is small relative to run variation (off 456.3-471.1 us;
on 451.8-465.9 us). The initial 4.08% reduction was not reproduced by this narrower,
optional implementation. No meaningful general speedup or utilization reduction
is established. All 32 records matched their native baselines with unchanged block
accounting in all ten runs; native/exact baseline differences remain explicit.

Evidence: `data/vu1-chain-followup/replay-optin-ab/summary.json`.
Runner SHA-256: `bbf74abfb8971e3b8d526a92fdedb5aeac4640b788a19601729734d7272bee7b`.
Replay SHA-256: `ed31593a79b93d9f130c73b3c46fb2ef04c35ebbfe880f3d6f64cce8f8fbfaad`.

`fetch,build,verify` passed: 13 CTest groups, pipeline/codegen/patch-stack checks,
production memory/audio tests, random VU1 backend equivalence and deterministic
self-loop budget/depth cases including the optional chain adapter, plus bounded
task capture/replay. Methodology tests cover frame boundaries, trajectory gates,
missing data, skipped frames and private-disc save exclusion. Disassembly confirms
that the reference adapter calls `chain` and the opt-in adapter contains its body.

## Final opt-in binary: frame-aligned JIT-only arrival

All six runs passed trajectory, state, zone, effective-mode, clean-exit and
unchanged-player-save checks. Each observed 360 consecutive guest frames. Fixed
1x internal resolution, 1280x720, audio on, hidden window; capture, intrusive timers
and compilation were excluded from these measurements. GPU busy samples use
Windows PDH and do not measure watts, temperature or GPU frame latency.

| Pair | Off FPS | On FPS | Off p95 / p99 ms | On p95 / p99 ms | Missing audio frames off / on |
|---|---:|---:|---:|---:|---:|
| 1 | 52.769 | 53.162 | 26.981 / 30.177 | 28.440 / 32.503 | 0 / 0 |
| 2 (reverse order) | 50.821 | 50.705 | 28.172 / 33.589 | 31.238 / 56.288 | 0 / 0 |
| 3 | 53.200 | 53.995 | 26.872 / 34.304 | 25.741 / 30.592 | 0 / 0 |

Mean per-run FPS: **52.263 off / 52.621 on (+0.68%)**. Median per-run p95 worsened
from **26.981 to 28.440 ms**. Median p99 was 33.589 / 32.503 ms, but the candidate's
second pair had a 56.288-ms p99 versus 33.589 ms reference. Thus the tail-latency
gate fails despite the small mean-FPS difference. Patch 71 stays **default off**.
The final implementation does not establish a useful player-facing improvement.

Mean GPU busiest-engine samples per run ranged 97.67-99.18% off and 92.51-98.54%
on; the short windows contain only a few samples. Total-system CPU means ranged
24.83-26.71% off and 23.52-29.34% on. Neither reduced GPU/CPU consumption nor power
savings is established. GPU pressure remains an independent investigation.

Missing audio frames were zero in both modes, so this scene cannot reproduce or
prove a fix for the reported sustained-combat audio problem. Exact dropped-audio
counts remain unavailable. Visible play, listening, long combat, other hardware
and stable 60 FPS remain open acceptance gates.

Evidence: `data/vu1-chain-followup/arrival-optin-jit-ab/summary.json`, per-session
logs, GPU samples and original-save inventories. The bounded helper stopped only
its own game processes. No test game was left running after the comparison.

Next work: isolate chain bookkeeping/block-timing costs on the identical corpus;
extend the frame-indexed fixture into combat without relaxing trajectory gates;
then correlate audio starvation with long frames and CPU/GPU/clock evidence.
Retain patches 66/67/68/71 as opt-in until those gates pass. The active changes
here improve reproducibility and diagnosis, not a validated stable-60-FPS tier.
