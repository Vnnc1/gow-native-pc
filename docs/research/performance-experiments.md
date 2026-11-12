# Performance experiment ledger: read before retesting

Last consolidated: 2026-11-03. Scope: VU1, JIT/AOT, GS, synchronization and related
build/PGO performance work recorded in this repository. Search terms in Portuguese:
**testes já realizados, piora, regressão, empate, sem ganho, inconclusivo, melhora parcial**.

This is the decision index for future maintainers and AI agents, not a new benchmark.
Read the linked evidence before proposing an experiment already listed here.
Detailed reports remain authoritative for settings, binaries, checks and limitations.
No entry establishes universal 60 FPS or validates the notebook's 28-minute scene.

## How to use and maintain this ledger

1. Search the hypothesis, function, flag and patch number here and in the sources below.
2. Reuse recorded results. Do not repeat an identical rejected/neutral experiment just
   because a new agent or chat starts. Missing ignored artifacts do not erase the report;
   mark raw evidence unavailable rather than inventing its contents.
3. A retest needs a material reason: different implementation, changed bottleneck/runtime,
   compiler/PGO, representative scene, previously untested hardware, or a concrete flaw
   in the previous method. Record the existing ID and that reason **before** running it.
   A changed binary hash alone is not an explanation of why the hypothesis should improve.
4. For incomplete gains, test the missing acceptance criterion rather than repeating the
   already-passed synthetic/functional check. Routine regression checks remain required;
   this rule avoids duplicate performance research, not correctness validation.
5. Append evidence; do not overwrite a negative result with a later favorable sample.
   Update this index and `docs/tested-hardware.md` when the decision changes.

Status meanings: **rejected** = not retained; **neutral** = no demonstrated useful gain;
**inconclusive/invalid** = no reliable performance decision from that comparison;
**partial gain** = a measured benefit with explicitly missing validation;
**deferred** = analysis/proposal, not a completed candidate A/B test.
Correctness, isolated execution time, guest FPS and presentation rate are separate claims.

## Evidence map and shared measurement limits

- **H**: [tested hardware](../tested-hardware.md), dated sections named in the entries.
- **S**: [VU1/synchronization follow-up, 2026-11-03](vu1-sync-2026-11-03.md).
- **R**: [60 FPS research roadmap, 2026-10-31](roteiro-60fps.pt-BR.md), especially phases 1–2.
- **V**: [review, 2026-10-30](revisao-2026-10-30.pt-BR.md), sections 6–10.
- **N**: [next steps, 2026-11-01](proximos-passos-2026-11-01.pt-BR.md), section B.

Unless explicitly stated otherwise, local measurements below use the Xeon E5-2666 v3
and RX 580 2048SP on Windows. The 2026-11-03 S comparisons each used three alternating
pairs of visible 100-second runs, 1x, audio enabled, precise VU, early GS FINISH,
complete measurement windows after 40 seconds, private cards, and no simultaneous
compilation/profiling. Baseline includes patch 60. Their numbers are **baseline → candidate**.
Other historical experiments have different settings: consult H/R/V, never compare
absolute FPS across entries. Real-time scripted inputs do not guarantee scene alignment.
Pinned replay controls scheduling; it does not emulate a slower computer.

## Regressions and rejected candidates

| ID / date | Hypothesis and search keys | Result, validation and decision | Evidence / missing scope |
| --- | --- | --- | --- |
| SYNC-01 / 2026-10-30 | Batch producer GS-stage pushes, 64 KiB, XGKICK | 57.1 → 53.8 mean FPS, slower in 3/3 full-screen pairs; reverted. Keep per-packet submission. | H “Early FINISH”; V §8.3. Distinct from consumer reclamation SYNC-04. |
| SYNC-02 / 2026-11-03 | `GOW_GS_STAGE_SPIN_US=0`, immediate sleep instead of 50 us | 58.154 → 56.839 FPS (-2.26%); three pairs, two worse; pacing worse and no demonstrated process-CPU saving. Keep 50 us. Detailed wait metrics collected separately. | H “GS queue instrumentation”; `data/experiments/queue59/`. Weak-CPU/power benefit unvalidated. |
| SYNC-03 / 2026-11-03 | `gs_stage.cpp`, `alignas(64)` head/tail separation | 59.4245 → 59.5143 (+0.15%); one pair worse, no consistent pacing benefit. Inconclusive; rejected and source restored. All six functional run checks passed. | S; `data/experiments/sync61/ab-valid/summary.json`. Earlier `ab` helper-launch failure is invalid evidence. |
| SYNC-04 / 2026-11-03 | Publish consumed `tail` every 4 KiB / batch end | 59.3409 → 57.7046 FPS (-2.76%), lost 3/3 pairs; minimum windows 54.06 → 43.6. DMA/ring/wakeup tests passed, but candidate rejected and restored. | S; `data/experiments/sync62/`. This batches reclamation, not submission. |
| VU-01 / 2026-10-31 | `chain`, `preserve_none` calling convention | Isolated transition experiment slower: +7% cost without PGO, +11% with PGO. Rejected; not an FPS gain. | R, patch-49 investigation. |
| VU-02 / 2026-11-03 | Remove `[[likely]]` from `chain` self-loop branch | Initial unpinned apparent gain failed confirmation: lost 4/5 alternating pinned replay pairs after warm-up. Native-baseline task parity passed; reverted before a game build. | H “Rejected VU1 branch-hint experiment”; `data/experiments/vu60/`. No gameplay FPS comparison. |
| VU-03 / 2026-11-03 | Compact `NativeState::Hist`, separate `histTails` | Five pinned JIT replay pairs improved 2091.36 → 2083.58 us (-0.37%), but gameplay tied: 59.4121 → 59.4173 FPS. Full verify and 128 tasks across five backends passed. Rejected; both source files restored. | S; `data/experiments/vu61/`. Native/exact corpus baselines differ; no new exact-equivalence claim. |
| GS-01 / 2026-11-03 | Reuse `tryShuffle` scratch vectors | Synthetic geometry -23.15% elapsed time and zero warm allocations, same digest; initial game variant 59.008 → 58.413 FPS. Visible smoke/parity passed but no FPS benefit. Rejected. | H “Rejected shuffle scratch experiment”; `data/experiments/gs60/`. See GS-02 for second layout. |
| GS-02 / 2026-11-03 | Append shuffle scratch fields after hot members | Second `fps-layout` series incomplete: fourth run lacked complete `gow-perf` windows and required forced termination while `gow-frame` continued. Cause unknown. No valid gain; not shipped. | Same H section; `data/experiments/gs60/fps-layout/`. Do not use incomplete averages or claim the synthetic win as gameplay speedup. |
| GS-03 / 2026-11-03 | Texture byte budget only, initial member layout | 59.145 → 58.596 FPS (-0.93%); rejected variant. This is not the retained patch-60 implementation with storage reuse and preserved hot-member offsets. | H “Default GS texture storage update”; `data/experiments/gs61/ab/`. |
| GS-04 / historical 2026-10-25 record | Waffle batching commits `00bda7f`, `09ea6cb`, `91ac954`, `c558c21` | RX580 game ~62 FPS but window 0.2–2 Hz, GPU queue saturation / SwapBuffers blocking. Excluded from patch 04. Do not reintroduce as an untested batching win. | H historical performance table; [handoff §8](handoff-2026-10-25-performance-phases.md). Not a reproduction of the new RX5500 XT report. |
| BUILD-01 / 2026-10-30 | Train PGO with `-O1` to shorten installation | Training compiled 2.2x faster, but final game 49.7 → 45.0 FPS, worse 3/3 pairs. Rejected; keep training at `-O3`. | H “Build time and the tune stage”; V §9.3. |
| CPU-01 / 2026-10-30 | PGO `x86-64-v3` instead of portable v2 | 52.91 → 52.11 mean FPS in three pairs, no gain; portable kept. | H “PGO, CPU target and patch 38”. Not the same test as VU-only AVX2. |

## Neutral experiments and failed apparent gains

| ID / date | Hypothesis | Result and decision | Evidence |
| --- | --- | --- | --- |
| VU-04 / 2026-10-31 | Move rare `blockTiming` / `scalarStart` paths out of `chain` | Neutral isolated transition result; rejected. | R, patch-49 investigation. |
| VU-05 / 2026-10-31 | Broader self-loop fast path, covering 89% of self-loops | 146.1 vs 146.2 ms, neutral; zero differences in alternating replay study. Rejected. | R, patch-49 investigation (4000 executions, eight alternating rounds). |
| VU-06 / 2026-10-31 | Inline common `chain` path at block exits | 156.3 vs 156.3 ms with PGO; 178.4 vs 178.5 without. Zero differences, no speedup; rejected. | R, same study. Do not relabel this as an untested easy win. |
| VU-07 / 2026-10-30–31 | AVX2 only in generated VU1 code | Reported 0% gain, discarded. Older summary does not supply a new paired FPS table. | V §10.1; R. Preserve this evidence limitation. |
| VU-08 / 2026-11-07 | Patch 76 `GOW_VU1_CHAIN_WARM` (successor-slot prefetch, default on), i3-10110U | VU1 ms per heavy frame 35.48→32.41, 34.03 vs 36.49, 32.64→33.24 (0→1); pairs disagree. Neutral; default kept. | [i3-10110U report](i3-10110u-2026-11-07.md). Throttling machine; within-pair only. |
| GS-10 / 2026-11-07 | zzz-302 wrap-blend grouping with padded bounding boxes only | Grouped nothing on the route: every batch was 4 triangles (two quads) whose halves always "touch" (`draws == tris`). Superseded by zzz-304's exact test (GAIN-12). | Same report, session 01. |
| SYNC-05 / historical barrier tests | Large-VIF1 drain-before-submit barrier, `GOW_VU1_EARLY_FINISH` | Three pairs on patches 01–37: 43.04 FPS on / 43.11 off, inconclusive. Later patch-38 pairs neutral; an earlier non-alternating baseline falsely suggested a gain. Remains opt-in. | H “PGO, CPU target and patch 38” and preceding barrier comparison. Not patch 40's early GS FINISH. |
| BUILD-02 / 2026-10-30 | Retrain PGO specifically with early FINISH | New 51.9 vs old 52.2 FPS, three pairs; neutral. | H “Build time and the tune stage”; V §9.1. Does not mean PGO itself is ineffective. |
| UI-01 / 2026-10-30 | Patch 39 menu/scaler/FXAA comparison | Two alternating pairs varied in opposite directions; no measurable FPS change. Functional menu/window captures passed. | H “PGO, CPU target and patch 38”; V §7. Not evidence for a performance optimization. |

## Retained or promising gains with incomplete acceptance

These are **not** instructions to revert existing patches. Do not promote their
limited evidence to whole-game correctness, stable 60 FPS, or notebook support.

| ID | Change and observed benefit | What remains unconfirmed / appropriate next validation | Evidence |
| --- | --- | --- | --- |
| GAIN-01 | Patch 60: 128 MiB decoded-texture budget plus same-shape `TexSubImage2D` reuse; 58.940 → 59.514 FPS (+0.97%), won 3/3 pairs. Retained by default. | No consistent process-memory reduction; observed game set ~7.2 MiB never exercised eviction. Synthetic pressure and RX580 CT32/T8/T4 pixel tests passed. Notebook near-6-GiB spikes, 28-minute scene and NVIDIA unvalidated. Do not attribute the entire gain solely to reuse. | H “Default GS texture storage update”; `data/experiments/gs61/{ab-reuse,result.json}`. |
| GAIN-02 | Patch 51, optional `GOW_VU1_FAST`: replay 150.0 → 132.3 ms (-11.8%), six alternating rounds; single-run scene FPS observations improved. | 23/4000 cases differ from exact mode. Limited captures show no visible difference, not whole-game correctness. No controlled scene FPS acceptance or default enablement justified; remains experimental/off by default. | R phase 2. |
| GAIN-03 | Patch 43 exact VU code simplification: reported VU -8.6%, FPS +11%, combat +8%. Retained. | Historical local route; not stable 60, full-campaign or weak-hardware acceptance. | R phase 1; V §10.2. |
| GAIN-04 | Patch 44 SPSC ring: combat 52.8 → 54.7 FPS (+3.5%), won 4/4 pairs on top of patch 43. Retained. Earlier baseline had tied. | Benefit depends on the preceding bottleneck; other CPU/core tiers not established. | R phase 1. |
| GAIN-05 | Patch 45 lazy VU decode: fork reports 39–112 us → ~1 us per code change on i3-4170. Already applied. | Local 45/46 comparisons were noisy (47–56 FPS in the same variant while PC in use). Do not claim local or notebook FPS gain from the fork's metric. | R phase 1. |
| GAIN-06 | Patch 46 PATH3 copy removal/pool return. Already applied. | One copy removed, but separate local FPS gain not established in the noisy 45/46 runs. | R phase 1. |
| GAIN-07 | Patch 50 recording/debug stack extraction: sampled `___chkstk_ms` 2.3% → 0%, replay zero differences, verify passed. Retained. | Controlled gameplay FPS gain still missing in the cited record. | R phase 1. |
| GAIN-08 | Patch 40 early GS FINISH: ship mean 54.63 → 57.80 FPS (+5.8%), combat 43.45 → 52.22; retained. | Save-route measurements vary (one of three pairs reversed); visual checks cover limited ship scenes. Not stable 60 or whole-campaign validation. | H “Early FINISH”; V §8.2. |
| GAIN-09 | Portable PGO: 52.51 → 54.96 FPS (+4.7%), combat dips +13.4%, three pairs. Retained. | Build/profile and route-specific; no transfer of percentages between PCs. New runtime/codegen needs matching profile identity. | H “PGO, CPU target and patch 38”. |
| GAIN-11 | PR 26 renderer stack (59 vertex ring, 61 shuffle/texture reuse, 66+74 primitive runs, 69 depth per ZBP, 72 prelude cache, 94 warm shaders), on by default since the [PR 26 integration](pr26-integration.md); contributor measurements are i3-4170/HD 4400 component costs (e.g. frontend submit 366-427 -> 86-118 ns/vertex, pre_fbo 141-194 -> 47-94 ms per 5 s). | No frame-pacing or FPS acceptance on fix-chore hardware. The integration fixed default-path defects first (zzz-300: dropped compact primitives, run-tail over-read, per-wrap GPU drain). Next: notebook `gs-run-ab.py --compare pr26`, then `grouping` (p95/p99 gate, see AGENTS.md), then single switches. | [pr26-integration.md](pr26-integration.md) |
| GAIN-12 | zzz-302 + zzz-304: wrapping-blend (COLCLAMP=0 shader blend) triangles with disjoint pixel coverage share one feedback draw; exact (GL shared-edge rule, separating line with 1/16 px margin). i3-10110U: draws and barriers per batch 4/3 → 2/1. | No FPS change on a CPU-bound (VU1-saturated) machine; GPU-bound hardware (weak GPU, strong CPU) unmeasured. Pixel equality relies on GL rasterization rules, not a captured-frame comparison. `GOW_GS_WRAP_GROUP=0` is the reference. | [i3-10110U report](i3-10110u-2026-11-07.md) |
| GAIN-11 / GAIN-02 notebook follow-up (2026-11-07) | i3-10110U: `--compare pr26` off 41.68/35.97/43.21 vs on 38.77/40.02/28.08 FPS, scenes diverged; `GOW_VU1_FAST` at most ~6 % VU1 cost per heavy frame (one pair throttled). | Neither establishes a gain on this machine; no default change. v0.5.0 vs fix-chore: heavy section ~10-15 % slower on fix-chore, p95 worse 3/3, cause not isolated (next: `vu1-task-ab.py` on both runtimes). | Same report. |
| GAIN-10 | OpenGL 4.3 context, patch 47: RX580 artificially limited to 4.3 kept hardware rendering with unchanged FPS. | Compatibility check, not a measured speedup on Intel HD 4400; physical target GPU test remains missing. | R phase 1. |

## Analysis and proposals that are not completed optimization tests

| ID | Existing finding | Do not confuse it with |
| --- | --- | --- |
| OPEN-01 | Disabling timing bookkeeping experimentally suggested only ~5–5.5% VU ceiling; static timing implementation deferred (R; V §10.1). | A completed, correct static-timing candidate with measured FPS gain. |
| OPEN-02 | Cheaper exact `madd` overflow handling: no cheaper exact alternative found in the recorded investigation (R). | Evidence that every future mathematically equivalent implementation has been tested. |
| OPEN-03 | Native OPMULA/OPMSUB/EFU and `(pc, hash)` slot cache discussed with small estimated ceilings (V §8.3). | Implemented and validated optimizations. |
| OPEN-04 | ThinLTO gameplay gain, fast-mode PGO training, idle timing in fast mode, parallel VU1 tasks and superblocks remain proposals in R/N. | Validated wins or already rejected implementations. Require a concrete new hypothesis; do not repeat the chain variants above under a new name. |
| OPEN-05 | Notebook reports showed complete native coverage for recorded blocks and long waits/memory spikes. | Proof that more JIT/AOT coverage fixes those stalls, or that waits are pure VU/GPU compute time. See H and the diagnostic reports; root cause and updated-kit result remain open. |

**GPU-03 — rejected for adoption**: [Official FSR 1 experiment](fsr1-experiment-2026-11-03.md).
Actual EASU/RCAS FP32 implemented in the isolated build; real-GPU orientation,
visible gameplay and full verify passed. Nine valid RX580 runs: current 2x
59.65 FPS, current 1x 59.39, FSR 1x 59.34. Scaler GPU cost ~0.107 -> ~0.243 ms;
no reliable FPS/pacing or quality advantage. Source/build restored, prototype
archived privately. One invalid no-FSR control stall and stale exit-metadata
recovery remain documented. Weak GPUs and Hydra attack unvalidated; retest needs
a changed GPU-bound workload/hardware or implementation, not another identical
opening-route comparison. The existing legacy `filtro=fsr` remains bicubic.

## Required record for a new experiment or retest

**GPU-02**: [LK report and presentation contention](shared-present-input-2026-11-03.md).
Retained patch 61 fixes a deterministic CPU-lock stall; six RX580 runs averaged
59.05 -> 59.40 FPS, 2/3 pairs positive (not a reliable FPS gain);
distinct from queue batching. RX7600 log identifies late guest FPS dips but contains
neither GPU utilization nor input latency. Candidate validation/retention is recorded
in that report; do not treat the synthetic stall reduction as a gameplay FPS claim.

Active source investigation **GPU-01**: [RX 5500 XT saturation / Hydra report](gpu-saturation-2026-11-03.md).
Launcher 0.5.0, default settings, VSync off, above/below deck; no target-GPU reproduction
or fix yet. Records per-triangle blend fallback, real-draw counter gaps, presentation
and bounded-queue behavior, and missing measurements. The new hardware/workload is
the reason to investigate; it does not reopen rejected queue experiments without evidence.

Record: ID/date; hypothesis and affected symbols/flags; previous ID and retest
reason; source/patch and runner hashes; hardware/driver/compiler/PGO; scene/card
and fixed settings; warm-up, duration, pair order and valid-run criteria; correctness
checks; guest FPS and pacing separately from replay/timing; failed or interrupted
runs; artifact paths; retain/revert decision; missing hardware/scenes and acceptance
criteria. Keep game-derived captures/cards under ignored `data/`, never in Git or
diagnostic packages. If raw artifacts are unavailable, say so explicitly.

## GS-05 / GS-06 — merged patch 66/67 RX580 retest (2026-11-04)

Planned at the maintainer request. Prior patch-66 laptop comparison improved mean
FPS but failed frame-tail/audio gates; patch 67 also failed default promotion.
See [patch 66](render-delivery-2026-11-04/integration.md) and
[patch 67](render-delivery-2026-11-04/followup.md). New material scope: physical
RX580 2048SP / driver 31.0.21924.61 rather than Intel UHD 620, combined with
patch 60 texture-budget/storage reuse and patch 61 nonblocking shared presentation.
Use a separate portable Release build and same-binary switches, private cards,
visible 1x/1280x720/audio, no simultaneous build/profiling. Start with the bounded
360-frame arrival trajectory gate (not sustained combat), three alternating pairs
for grouping, alpha alone and alpha with grouping. Record rejected runs and
visual smoke separately. Defaults remain off pending consistent pacing/audio and
visual evidence; no performance result exists at this planning point.
Artifacts: `data/experiments/patch66-67-merged/`.

Completed results: [RX580 report](patch66-67-rx580-2026-11-04.md). The bounded
arrival comparisons are mostly at the 60-FPS cap; no default promotion. The long
resource attempt failed scene alignment and the alpha resource series failed
exit metadata validation. Preserve both as invalid/incomplete evidence.

Resource follow-up requested during this retest: FPS cap alone is not an
efficiency gate. Collect separate 100-second guarded-ship sessions (40-second
warmup), Windows PDH GPU engine busy time and process CPU time, with identical
settings and scene-position gates. Compare grouping and alpha independently;
normalize CPU work by guest frames where valid. These are utilization/time
metrics, not watts. Timing/capture sessions must remain separate from FPS evidence.
Prior notebook resource observations are in the patch-67 follow-up and
scene-bottlenecks reports; changing to RX580 and the merged texture/presentation
paths supplies the material retest reason. Failed scene gates remain invalid
comparisons; do not loosen them to manufacture a saving.

## GS-07 / GS-08 / GS-09 — renderer efficiency candidates (2026-11-04)

Implemented isolated candidates for sampler-state caching (patch 72), a specialized
shader with full-program fallback (73), and conservative vertex-alpha intervals
(74). Patch 75 exposes test-only path coverage. These are new implementations,
not re-runs of the rejected FSR or stage-spin experiments. Reference switches
preserve the old paths. The alpha extension intentionally excludes texture-alpha
dependent draws; it does not claim full texture/CLUT range analysis.

Evaluate CPU time per guest frame and GPU engine busy time as well as FPS; capped
FPS is not an efficiency verdict. Synthetic interval/state tests and differential
real-GL pixels precede default promotion. Reference and candidate use one binary,
private cards, matching frame trajectories and separate diagnostic samples.
Initial solid-color pixels passed but were insufficient to validate filtering;
the stronger nonuniform texture fixture supersedes that limited coverage.
Detailed results, negative evidence and retained/default decisions are recorded
in [the implementation report](patch66-67-rx580-2026-11-04.md).

## GPU-04 — supplied i3-4170 / HD 4400 report (2026-11-04)

[Delivery/log follow-up](chin-delivery-followup-2026-11-04.md): all 72 recorded
source-patch hashes match the supplied delivery. Source snapshot does not prove
runner provenance. Guest probe matches Japan; 25 later windows show zero guest
flips while the host presents at 60.59–119.18 Hz. No controlled 60-FPS gameplay
or GPU-saturation evidence. Original delivery ring ownership and vertex-tail
defects reuse the prior correctness review; the current renderer excludes that
ring and already fixes the tail. Disappearing bodies remain unlocalized.
Deferred investigations: incident-correlated progress/render checks, host cap
60/120 resource/latency comparison, and missing acceptance criteria of the
notebook scalar-outline replay result. No runtime/default changes or new
performance benchmark in this review.

Clarification: the reported vanilla-launcher failure is black screen after the
intro, distinct from the issue screenshot's missing bodies. Prioritize bounded
movie-to-game transition diagnostics; no confirmed hardware incompatibility or
ring-corruption attribution for this session.

Authorized follow-up: reconstruct the available isolated Japanese source snapshot
in `C:/gow-black-jpn` because the registered executable no longer exists. Its
prepared ELF exactly matches the supplied session hash. Run visible, audio-enabled
normal boot with/without only FMV skipping, using private cards and movie-state
diagnostics. This is a new correctness workload (post-intro black screen), not
a repeat of the capped performance experiments. The local RX580 and rebuilt
regional baseline cannot substitute for the missing reported runner/Intel GPU.

Executed evidence: [post-intro isolation](black-intro-tests-2026-11-04.md).
The reconstructed Japanese runner reaches visible gameplay with normal and
skipped `Semo01` on RX580. Normal-video smoke passes 11 gates and demonstrates
zero guest-probe windows during progressing FMV; this is not alone a hang signal.
The 150-second skip run reaches combat but fails graceful shutdown (collector
forced termination), so it is not a passing full smoke. Preserve this failure.
No post-intro root cause or hardware compatibility fix established; no runtime
or default changed. The affected runner is unavailable per maintainer reply.

## AUDIT-01 — source, build and audio correctness (2026-11-05)

[System audit](system-audit-2026-11-05.md): patches 76/77 fix shader lifecycle/link
failure handling and stale fractional audio phase after reset. Launcher reset,
PGO eligibility/provenance and persisted FFmpeg configuration were corrected.
Full fetch/verify passed, including 18 CTest groups and VU1 equivalence. Release
game and launcher built; old/new real-GL fixtures match in seven 384-frame variants.
No experimental renderer default was promoted and no FPS gain is claimed.

The 150-second normal-boot, 2x/FXAA/early-FINISH/audio smoke passed 11 functional
gates and inspected menu/ship captures. It still recorded missing audio frames:
7085 in the startup window ending 7.702 s and 1646 in the transition window ending
87.702 s. Capture occurred at 83.610 s; correlation does not establish cause.
Repeat the same functional route without captures to test that specific diagnostic
cost. This is not a clean performance benchmark or an acceptance of audio quality.
The new runner has no matched PGO; never compare it as a performance A/B against
the preserved PGO executable. Detailed evidence and follow-up results stay in
the linked audit and ignored `data/experiments/audit-20261105/`.

Follow-up completed: the no-capture route also passed all functional gates but
recorded 6605 startup and 1036 transition missing audio frames. Captures are not
the sole cause. A later gameplay window was 57.18 guest Hz / p99 35.263 ms; no
stable-60 or audio-quality acceptance. Preserve both runs without attributing the
variation to any patch. The active PGO runner remains selected after testing.

## AUDIO-01 — local FMV-to-game undersupply investigation (2026-11-05)

Continuation of AUDIT-01, authorized by the maintainer. New measurement: patch 78
adds opt-in bounded output events (reset generation, producer publication count/
age, callback deficit/gap and mutex/drain duration). No buffer size or playback
rate change. The previous five-second audio windows could not distinguish these
mechanisms; the new event timestamps are the reason for repeating this route.
Use the same isolated unprofiled runner settings, private card, normal boot,
2x/FXAA/early FINISH and audio, without captures or simultaneous compilation.
This is diagnostic work, not an FPS benchmark. Preserve overflow/failed-exit cases.
Evidence: `data/experiments/audio-transition-20261105/` and
[complete results](audio-transition-2026-11-05.md). The first destructor-only trace
failed completeness because normal exit uses `_Exit`; preserved, not accepted.
Explicit shutdown flush then passed all 12 smoke gates in a 120-second visible run.
The complete trace recorded 6605 startup and 1340 transition missing stereo frames.
Transition deficits had no reset, acquisition <=1 us and producer age <=95 us:
publication continued but supplied only 320 frames across the observed 30.132 ms
endpoint interval. Upstream cause remains open; no audio-policy or FPS gain claim.

Producer-attribution follow-up: the new measurement adds publication reasons and
the last publication's IOP grant/clock snapshot to the existing bounded trace.
This addresses the missing distinction between one-frame flush causes and
insufficient granted emulated time; it justifies another identical route under
AUDIO-01. Keep any native-sampler run separate from the unsampled trace run.
Reference patch-78 executable is preserved in
`data/experiments/audio-producer-20261105/reference-78.exe`; results follow below.

Patch 79's unsampled run passed all 12 gates and localized all 395 newly published
frames over a 39.419 ms deficit interval to stream-position polling. Granted IOP
time advanced only 8.230 ms. Source inspection found the final display-drain loop
never reaches the existing movie service's host-deadline catch-up. Patch 80 extends
that existing mechanism only to the proven USA entry/caller pair, with the same
one-field cap and no mixer change. Full verify and the new production-wrapper
fixture passed. Matched unsampled transition comparisons use the preserved
patch-79 runner and patch-80 candidate, both without PGO; do not use the separate
sampler run as a performance reference. Evidence: `data/experiments/audio-tail-20261105/`.

Result: after correcting an omitted override synchronization, two patch-80
120-second visible runs passed 12/12 gates and recorded zero post-startup deficits.
The two preceding patch-79 references recorded 1570 and 1497 transition missing
stereo frames. Same settings, no profiler/captures/concurrent builds, no matched PGO.
This supports the targeted local transition fix, not a gameplay-FPS improvement.
Startup undersupply remains (7437/7085 missing frames in the candidate runs).
The initial intended candidate was still patch 79 by hash and is explicitly
preserved as an integration failure. Full data, hashes and ordering are in the
linked AUDIO-01 report; other movies/hardware remain open acceptance gates.

## BUILD-MEM-01 / 2026-11-09 — VU1 generator retained images

New correctness/memory investigation motivated by community issue 6's
`std::bad_alloc` in `ps2x_vu1_generator`, not a retest of an earlier FPS candidate.
Patch `zzz-306` keeps raw captures and decodes one image per existing pass rather
than retaining every decoded image. On 1000 zeroed images, Windows peak working
set fell from 158097408 to 26755072 bytes; both executions succeeded. All 13 output
files remained byte-identical for that workload and for eight real captures.
Malformed-size inputs now fail before an unbounded read. Accepted for output
parity and lower retained memory; reporter crash closure remains pending without
their captures. Extra decoding work is not a claimed build-time speedup; unique
emitted code can still consume substantial memory. No gameplay/FPS claim.
See [triage and reproducible checks](community-issues-2026-11-09.md).

## GPU-05 / 2026-11-09 — issue 31 shared acquisition diagnosis

New report: GTX 1060 3 GB rain/combat stutter, including 2x with AF disabled.
Unlike GPU-01's utilization-only report, the attachment includes guest intervals,
runner identity and a player marker. It still has no fresh-shared-frame metric.
The current change measures host acquisitions/reuse with bounded counters and no
new GPU calls under existing performance diagnostics. Local RX 580 controls at
2x/AF off, 2x/AF16 and 3x/AF off exercise those measurements under different load;
they do not retest GPU-03's rejected FSR implementation or establish NVIDIA gains.
No renderer optimization is promoted without a separate reproduction and parity
check. One control stopped host reporting and required forced termination; the
controls do not establish a matched gameplay workload or a performance gain.
Decision: retain diagnostic coverage only; issue 31 remains unresolved. See
[evidence and limitations](issue-31-stutter-2026-11-09.md).

Follow-up on the invalid 2x/AF-off control: an unchanged visible 180-second rerun
exited normally. Deliberate minimization reproduced stopped host reports plus
forced termination. A thread snapshot identified raylib's minimized-window
`glfwWaitEvents` loop, which does not surface close requests until restoration.
Patch `zzz-308` keeps host polling active using `FLAG_WINDOW_ALWAYS_RUN`.
This is lifecycle correctness, not a new FPS experiment or proof of the original
control's unrecorded window state. Background rendering remains active; no power
or GPU performance improvement is claimed. See the investigation's follow-up.

## PERF-06 / 2026-11-09 — current native-build release readiness

New request: investigate stable 60 FPS before a public test release. First inspect
existing player sessions (latest runner through zzz-314), then GAIN-11's missing
local frame-aligned renderer comparison. Unlike GPU-05's unaligned JIT-only /
interpreter-IOP controls, this uses the actual installed AOT/native-IOP Release
runner, exact VU, no PGO, private blank cards and `ship_arrival_frames` (0..360).
The materially different execution tier and mandatory trajectory gate address
those earlier controls' limitations. This is a short arrival acceptance probe,
not a reproduction of rain/combat or notebook acceptance. Use two alternating
PR26 off/on pairs, visible 1280x720, 1x, FXAA off, AF off, audio enabled, frames-only
metrics and optional PDH GPU counters; no captures/profiler/concurrent builds.
Keep all failed gates and do not change defaults from an invalid comparison.
Evidence: `data/experiments/release-readiness-20261109/`; results will be appended.

Result: four visible, frame-aligned arrival runs passed all ten functional gates.
Off/on/on/off: 59.909 / 59.996 / 59.996 / 59.996 guest Hz; p99 18.446 / 17.815 /
17.819 / 18.028 ms, no missing audio in the measured 360-frame intervals.
This capped six-second workload establishes no useful speedup. p95 did not
improve in both pairs; no default change. Startup audio counters, two-sample GPU
estimates and varying background CPU activity remain limitations. Current player
reports have lower-rate windows with large scoped VU time, which includes waits;
no confirmed pure-CPU cause, stable-combat-60 or notebook acceptance. Added explicit
installed ELF/collector CLI paths to the harness; regression suite passed.
See [full method, numbers and priorities](release-performance-2026-11-09.md).

## VU-09 / 2026-11-09 — distinguish VU wall time from thread CPU

Follow-up to PERF-06's high scoped VU time. New measurement: the existing Windows
sampler gains a counter-only mode with no thread suspension, symbols or timer
resolution change. Read actual CPU time separately from scoped wall time and
bounded queue waits on the installed native build. A separate intrusive sample
may locate executed addresses; it is not an FPS run. Use a private copy of the
player card, scripted load, bounded local task recording and preserve hashes.
This addresses a missing attribution criterion, not a retest of VU-01..08's
rejected chain/branch/layout candidates. No runtime optimization is accepted
without parity and a matched heavy-workload comparison. Evidence will remain in
`data/experiments/vu1-waits-20261109/`.

VU-09 result: private-card Athn01D altar load reproduced high VU cost. Windows
thread CPU counters without suspension measured 99.75% of one core with detailed
probes and 98.09% with basic metrics only. The latter's separate instruction
sample attributed approximately 33.8% of wall samples to chain; this is not CPU
self time. GS-stage producer capacity waits after capture were only 1.956 ms over
36.318 s. This local workload is predominantly execution, not blocked waiting.
Basic-metric windows averaged 59.403 guest Hz, median window p99 21.866 ms;
detailed probe windows 50.423 / 34.367 ms. These are different instrumentation
conditions, not a candidate FPS A/B or stable-60 acceptance.

Found and retained zzz-315: the enabled task recorder entered its large temporary
interpreter frame even for delayed/strided/completed captures. Move selection
checks outside that frame while retaining the mutex and all gates. Three pinned
synthetic pairs (one million calls, limit three) reduced median elapsed time
0.730440 -> 0.648603 s (11.20%), with identical digests and corpus hashes. The
recording-disabled path is unchanged: no ordinary-play FPS gain claimed. All 32
real tasks passed JIT/exact replay against their respective baselines; native/
exact baselines still differ. Initial identical-binary build controls were rejected
before timing and retained. No launcher runner/save/configuration was replaced.
See [full VU-09 report](vu1-waits-2026-11-09.md) for method, tests and limitations.

## VU-10 / 2026-11-09 — chain diagnostic-path specialization

New hypothesis after VU-09's heavy Athn01D capture: compile the no-diagnostics
chain path separately so its per-block body has no cost/opcode/self-counter
instrumentation checks. One entry selection retains the existing detailed path.
This is not VU-04's timing/scalar outlining, VU-06's block-edge inlining or
OPEN-01's removal of emulated timing: all cycle/flag/lane/history/stop behavior
stays intact. Start with the identical 32-task corpus, alternating pinned replay
and baseline-specific digest checks. Only a passing replay candidate proceeds to
isolated normal-build gameplay with private cards. No installed runner/settings
or user saves are replaced. Evidence: `data/experiments/vu1-chain-20261109/`.

VU-10 result: retained as zzz-316, default on for ordinary gameplay. Five pinned
32-task replay pairs reduced median sum of warm execution times 599.6 -> 553.7 us
(7.66%), all pairs favorable, unchanged signatures/digests. This is total isolated
native task time, not a 7.66% FPS claim or removal of emulated cycle bookkeeping.
Three alternating private-card Athn01D pairs (1800 aligned frames, 2x/AF16/FXAA,
normal AOT/native IOP, no detailed timing/recording/profiler) passed all 11 gates.
Candidate p95/p99 improved in all pairs. Median run FPS 59.766 -> 59.966, p95
17.973 -> 17.785 ms, p99 19.490 -> 18.537 ms. Preserve the third reference outlier
(58.599 Hz / p99 26.051 ms); no controlled background-load or universal-speed claim.
Zero missing audio in all measured intervals; startup deficits remain outside them.
Five-seed generated/JIT/SSE/special-value and self-loop budget/depth equivalence,
32-task replay in five modes, diagnostic-path fixtures and harness/profile tests
passed. Final rebuilt core equals the measured object except its COFF timestamp.
The installed runner/settings/source card were not replaced. Other hardware,
sustained combat and full-campaign acceptance remain open. [Full report](vu1-chain-2026-11-09.md).

## GPU-06 / 2026-11-11 — GS worker frames in flight (`zzz-326`)

New hypothesis for issue 31 (still reproducing on v0.6.0-rc.1): the GS worker context never swaps,
so no driver pre-render limit applies. Only the 4×8 MiB vertex ring, waiting on a fence three segments old,
bounded its lead (about 12–24 frames). A GPU-bound scene then alternates running ahead with whole-segment
ring stalls. That fits the counter showing 45–60 FPS during visible stutter, and the 5–6 s of smoothness
after a menu pause drains the queue. Not a retest: GS-04 and SYNC-01..04 changed batching and spin strategy,
GPU-02/05 host acquisition; none bounded queue depth. Candidate: fence per presented frame, wait on the
oldest while more than 2 are pending, 50 ms bound, no `glFinish`. `GOW_GS_FRAME_LATENCY=0` is the reference.
Validation so far: fake-fence unit test, syntax compile, full chain apply. **No game, GPU or FPS run.**
Do not claim a #31 fix or an FPS change until gates 1–3 in
[the report](frame-latency-2026-11-11.md) pass: GTX 1060 3 GB scene, a CPU-bound notebook and the RX 580 arrival probe.

GPU-06 Windows follow-up (2026-11-11, i5-8265U / UHD 620 / driver 27.20.100.9664, AC):
`fetch,sync,build,verify` with the 140-patch chain passed on Windows/llvm-mingw (18/18 CTest groups
including `gow_frame_latency`, VU1 equivalence, task replay, mod consumers). Runner
`e909b29f5a8b68e9f20a426eee13fadfa65f9601e5482503cfd8488b5b7cef14`. `gs-run-ab.py --compare frame-latency`
(new mode: variant 0 = `GOW_GS_FRAME_LATENCY=0`, 1 = shipped 2; checks `[gs-latency-config]`) ran visible
`ship_guard`, 1x/1280x720, audio, private blank cards, 120 s / 60 s warmup. **FPS comparison invalid**:
three batches aborted on `same_scene` after 5, 1 and 2 runs; guest FPS ranged 13.7–26.5 in both variants
with mean system CPU 16–70% from concurrent desktop work (VS Code, Chrome, Explorer), and the sampled
processor performance fell from ~207% idle to ~130–160% while playing (shared CPU/iGPU power limit).
Mechanism evidence that is valid: with `GOW_GS_HW_STATS=1` the reference had `ringStalls` 0–2 per session,
and the candidate waited at most once per 5 s window (≤1.8 ms total), with no timeouts. So on this
power-limited notebook zzz-326 is near-free and the ring-wrap stall it targets barely occurs; this neither
confirms nor refutes the GTX 1060 issue-31 hypothesis. Evidence: `data/experiments/frame-latency-20261111{,-b,-c}/`.
Gate 2 (no CPU-bound regression) still needs an idle-machine repeat; gates 1 and 3 untouched.

GS-05 (patch 66 grouping) gate retry (2026-11-11, same notebook/runner): `--compare grouping`, same settings.
**Invalid**: aborted on `same_scene` after 3 runs, system CPU 69–100% (concurrent `zig`/`node`/Chrome),
guest FPS 7–13. No default change; the i5-8265U gate in AGENTS.md remains open and needs an idle machine.
Evidence: `data/experiments/grouping-20261111/`. Per maintainer guidance, a notebook result alone
does not set defaults for other tiers.

Idle-machine repeat (2026-11-11, same notebook/runner, system CPU 17–33%, no concurrent build). New
`gs-run-ab.py --keep-going` keeps runs that fail validation as invalid evidence and averages only complete
pairs whose two runs passed every check (same validity rules; `same_scene` now compares against accepted
runs only). Visible `ship_guard`, 1x/1280x720, audio, private blank cards, 120 s / 60 s warmup, 4 pairs each.
`ship_arrival_frames` was not usable here: at ~26 FPS the frame-indexed trajectory diverged by 88 units at
frame 240 (delta-time physics), so frame-aligned scenes need faster hardware.

- GPU-06 `--compare frame-latency`: 3 valid pairs (one reference run failed `same_scene`). Mean guest FPS
  19.82 → 20.67; median-window p95 per pair 67.8/76.2/64.5 → 65.6/64.5/65.6 ms; intervals >100 ms 14 → 0;
  zero missing audio. Candidate waited 2–8 times per session (38–249 ms total), never timed out; reference
  ringStalls 0–4. **Neutral to slightly favorable; gate 2 (no notebook regression) passed.** Gates 1 (GTX 1060)
  and 3 (RX 580) remain open. Evidence: `data/experiments/frame-latency-keepgoing-20261111/`.
- GS-05 `--compare grouping`: 2 valid pairs (two candidate runs failed `same_scene`, both faster: 22.4 and
  25.7 FPS, excluded). Mean guest FPS 18.62 → 21.65; p95 74.5/68.7 → 63.6/65.7 ms, p99 81.3/72.0 → 68.7/70.6 ms;
  intervals >100 ms 14 → 0; missing audio 1751 → 0 (one reference run). Every valid off run was slower than
  every on run. **The notebook gate passed: grouping stays default on.** Local i5-8265U/UHD 620 evidence only.
  Evidence: `data/experiments/grouping-keepgoing-20261111/`.

GAIN-09 retest (2026-11-11, i5-8265U / UHD 620): first profile trained on the current 140-patch chain
(`-Stages pgo,pgo-check`, 243,003 profiled functions, exact fit). The final build reported
`profile coverage: 1 of 6 profiled functions in 1 recompiled objects changed` (`vu1_generado/programa0.cpp`
differs between the instrumented and the final build): under the former `-Werror=profile-instr-out-of-date`
that object would have failed the build; with the tolerant fit it built and pgo-check passed.
Runners: no PGO `e909b29f…cef14`, PGO `7ee02a2a…afcd` (copies in `data/experiments/runners/`).
`--compare vu1 --reference-runner` (both variants grouping **off**, not the shipped default), visible
`ship_guard`, 4 pairs, `--keep-going`: **inconclusive**, only 1 valid pair (no PGO 19.16 vs PGO 15.78 FPS,
the PGO run under 44% system CPU from concurrent node/headless Chrome/VS Code). Five runs failed `same_scene`:
knockback moved Kratos up to ~230 units into a lighter area (20–29 FPS), so roughly half of ship_guard runs
on this notebook are not comparable. No PGO speed claim from this machine; repeat on an idle machine with
`--grouping 1`. Evidence: `data/experiments/pgo-20261111/`.

MEAS-01 / 2026-11-12 — reproducible combat measurement (`zzz-328`). Not a speed change: a test-only fixed 1/60 s
step so frame-indexed scenes replay the same simulation on slow machines. Identical-binary `ship_frames` with
`--fixed-step` on the i5-8265U: 4/4 runs valid, trajectory deviation 0.000, guest FPS 32.5–34.7 (same binary,
~6 % spread). Use it for future A/Bs on this notebook; its FPS is identical-workload throughput, not real-time play.
Evidence: `data/experiments/fixedstep-repeat-20261112/`, [report](fixed-step-2026-11-12.md).
