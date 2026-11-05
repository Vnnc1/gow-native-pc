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
