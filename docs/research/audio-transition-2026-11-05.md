# Audio transition follow-up — 2026-11-05

Continuation of [AUDIT-01](system-audit-2026-11-05.md), ledger AUDIO-01.
Local target: Xeon E5-2666 v3 / RX 580 2048SP, driver 31.0.21924.61.
This is correctness/diagnostic work, not a performance benchmark or weak-PC claim.

## Measurement change

Patch 78 adds `GOW_AUDIO_TRACE=1`: a fixed 512-event buffer per sound engine,
allocated only when requested. It records reset generation, producer publication
count/age, requested/produced frames and callback acquisition/drain timing. No
new file writes or allocations occur in the callback. Normal buffering and
resampling policy remain unchanged. See [field semantics](../reporting-bugs.md).

The smoke test accepts `--audio-trace` and requires matching begin/end markers,
complete event counts and no overflow. Use event-relative `t_us`, not the collector
timestamp of the final dump. Acquisition duration includes scheduling; a long
value alone does not prove mutex contention.

## First integration failure: preserved

The initial implementation dumped from `SoundEngine` destruction. Although the
runtime destructor stops audio before destroying the IOP, normal `main` calls
`std::_Exit(0)` after `runtime.run()` and bypasses that destructor. Thus unit tests
and full verify passed, but the 150-second real-game test correctly failed its
new trace-completeness gate: begin marker present, no event/end dump.

Evidence: `data/experiments/audio-transition-20261105/trace-smoke.log` and
`data/gow1/logs/session-game-20261105-183138`. The other 11 functional gates passed;
the transition audio counter again recorded missing frames (1289). This run cannot
localize the missing audio because the event trace is absent. Initial runner
SHA-256: `a4c4189a3ceca867e0797ec11bd863f8335f640acfbc97370bb446203c29da7a`.
The follow-up explicitly flushes diagnostics after stopping audio on the opt-in
path, preserving the normal fast-exit policy.

## Complete trace result

The corrected 120-second visible normal-boot run passed all 12 gates, including
trace completeness: 42 events, zero overflow, six resets, 126693 publications and
5670257 published stereo frames. All resets preceded playback; the last occurred
at trace-relative 0.834486 s. Runner SHA-256:
`60be3d44c4ae51b706c9c04306729f0defce7d19c8b42cbf6705d053bbc6cae5`.
Evidence: `data/gow1/logs/session-game-20261105-184250` and
`data/experiments/audio-transition-20261105/trace-complete-smoke.log`.

Startup had 29 deficit events totaling 6605 missing stereo frames. Publication
count remained 32 while producer age reached 138670 us. The transition had seven
deficit events totaling 1340 missing frames at trace-relative
81.083593-81.113725 s (approximately 82.522-82.552 s collector elapsed).
There was no reset. Producer age was 1-95 us, acquisition 0-1 us and drain 0-8 us.
Publications increased from 70795 to 71102, but total published frames increased
by only 320 over 30.132 ms, versus approximately 1446 frames at 48 kHz.
These endpoints establish continued but insufficient production during the
observed deficit interval; they do not identify which upstream workload caused it.
Neither a queue reset nor a long acquisition explains these seven deficits.
The startup publication pause and transition under-rate are distinct observations.

No buffer enlargement, time stretching or frame-rate gain is claimed. The full
patched build/verify passed 18 CTest groups and VU1 differential/replay checks.
An additional mixer regression run with `GOW_AUDIO_TRACE=1` passed, including
62 sound-engine shutdown records, bounded overflow and idempotent dump coverage
(`data/experiments/audio-transition-20261105/trace-mixer-final.log`).
The old PGO runner remains selected through `data/build-root.txt` (`C:/gow-q59`).

## Producer source review and next gate

The production chain is `EeScheduler::accountCycles` -> `advanceIopEeCycles` ->
`accrueEeCycles` (EE/8, 512-cycle batching) -> `runCycles` -> `serviceSound` ->
`advanceTo`/`mixTo` (768 IOP cycles per stereo frame). Sound time intentionally
uses the granted cycles, capped by `runGrant`, rather than all cycles spent in
native RPC/callback work. Removing that cap would reintroduce oversupply; moving
sound to wall time would change guest timing rather than establish its cause.

One-frame publications do not identify which register/stream access flushed the
mixer. The next discriminating measurement is producer-side attribution around
low queue occupancy: granted cycles, soundBase, totalCycles, pending IOP cycles
and flush reason, correlated with producer-thread sampling near the transition.
The subsequent patch-79 measurement below implements attribution only.

## Producer attribution (patch 79)

Patch 79 reuses the bounded buffer and records the last publication's IOP context
and lifetime frames per flush reason. Pending producer state is never read by the
callback. Reset invalidates the context. The default path adds a call/null check
and reason arguments, not clocks, allocations or logging; its overhead is unmeasured.
Full fetch/build/verify passed, including 18 CTest groups and VU1 comparisons/replay.

The unsampled 120-second normal-boot run passed all 12 gates:
`data/gow1/logs/session-game-20261105-190345`. Candidate SHA-256:
`c3596a1e1a08ce8945312eac7f33c53b9d7f46da0345646879ecc44541e117a3`.
There were 54 events, zero overflow and six resets, all before playback. Nine
transition deficit events totaled 1570 missing stereo frames, with acquisition
0-1 us. Across the first/last deficit timestamps (81.042413-81.081832 s),
publication increased by 395 frames; every added frame was attributed to
`streamPosition` (reason 6). All other reason totals stayed unchanged.
Granted cycles increased by 303396 (8.230 ms of emulated IOP time) over 39.419 ms
of host time. Total IOP cycles increased by 1025324; these include work excluded
from the sound clock by design. This narrows the undersupply to stream-status
polling and slow granted-clock progress; it is not evidence to remove the clamp.

Artifacts: `data/experiments/audio-producer-20261105/`. A separate sampler run
is deliberately excluded from any FPS or dropout-rate comparison.

The sampled session `session-game-20261105-190705` also passed all 12 functional
gates. The six-second sampler window collected 2636 GameThread instruction
samples, including system waits and clock queries; module offsets were resolved
against the exact executable's COFF symbols. This broad window is not a timed
profile of the approximately 40 ms deficit interval, so it does not establish
that a particular function caused the undersupply. Raw/resolved files remain in
the experiment directory; no performance comparison uses this run.

### Tail-loop coverage gap

The generated USA movie routine at `0x189790` calls audio refill `0x189A88`
(return address `0x18979C`), then queue-drain check `0x26CE98`, and loops until
ready. Refill reaches `0x188380` -> `0x188688` -> `0x26C900` -> command `0x40`
-> native stream-position query. The queue check reads `0x30A440`; the VBlank
handler at `0x26CF20` decrements that same queue counter. This loop never calls
`0x188B80`, whose existing override catches up already-due host events to avoid
slow emulated-time progress during movies. Thus that correction does not cover
the final display drain. The targeted candidate reuses the existing catch-up
only on entry to `0x189A88` from `0x18979C`, capped at one field, before calling
the original. It does not remove audio flushes or change global sound timing.

The first intended patch-80 smoke (`session-game-20261105-191447`) exposed an
integration mistake: `fetch,build,verify` tested the new wrapper source but did
not synchronize profile overrides into the runner's owned source copies. Ninja
reported no work, and the runner hash remained the patch-79 hash above. The run
passed 12 gates and recorded 1497 transition missing frames, but is not a patch-80
test. Its log remains `audio-tail-20261105/candidate-1.log`; the name describes
the intended role, not the actual binary. Follow-up uses `sync,build` and checks
the changed runner identity before gameplay. The source/runtime tests already
passed; this failure demonstrates why they do not substitute for artifact checks.

After synchronization exactly one `.cpp` changed, with no header changes/removals.
The compiled override matches its source SHA-256
`66fe9b35317f71d4d0ca0a05931e53091f927389d8e1056738540aad28fce97e`.
The actual patch-80 runner is
`ab55a7220205c72c61b265e460969110249af671e7bbab4edaf3794f056d86e1`.
Its first unsampled 120-second run (`session-game-20261105-191947`) passed all
12 gates and recorded zero post-startup deficits, including the movie transition.
Startup still had 7437 missing stereo frames. The trace was complete (40 events,
zero overflow). This is a local transition result, not a whole-game audio or FPS
acceptance; the repeat below checks local repeatability.

The second identical unsampled run (`session-game-20261105-192231`) also passed
12/12 gates and recorded zero post-startup missing frames (36 trace events,
zero overflow). Startup had 7085 missing frames. Both patch-80 runs reached
gameplay and exited normally; no profiler, captures or concurrent compiler ran.

| Actual runner | Session suffix | Transition missing stereo frames | Startup missing frames |
| --- | --- | ---: | ---: |
| Patch 79 | 190345 | 1570 | 9005 |
| Patch 79 (stale intended candidate) | 191447 | 1497 | 7565 |
| Patch 80, synchronized | 191947 | 0 | 7437 |
| Patch 80, synchronized repeat | 192231 | 0 | 7085 |

These are two reference runs followed by two candidate runs, not randomized
performance pairs. The supported claim is elimination of the observed transition
underrun in these two local runs. Startup undersupply, whole-game audible quality,
other movies/regions, Intel/NVIDIA and weak-PC frame pacing remain unvalidated.
The correction is registered by default for normal USA movie playback; it requires
a matching synchronized runner and no player diagnostic flag. The installed PGO
runner remains selected while this unprofiled candidate stays isolated.

A separate 100-second visual run (`session-game-20261105-192513`, captures on)
passed all 12 gates. The menu and ship images were inspected: expected menu text,
Kratos, ship geometry and scene were present. It also recorded zero post-startup
missing frames and 7085 startup missing frames. Captures make this a separate
functional check, not a performance reference or a whole-game visual-equivalence
claim. Images stay in ignored local data and are not packaged.

## Regional baseline clarification

The apparent regional baseline failure was the correct rejection of newer USA
sources. Repository `0807965ba9cbb464b2658f914b2ac2fb7b323bf9`, pinned runtime
`471c83180a8df575cff4abd3fae6c043b5096925` and its ordinal patches through 58
reproduce every stored baseline hash. Applying each overlay to temporary copies
reproduces all seven affected files in the preserved Europe/Japan snapshots.

`regional-overlays.py --runtime <pre-overlay-snapshot>` now permits that explicit
check. Tests retain strict hash verification and reject changed/missing sources,
path escapes, the newer USA runtime and already-overlaid sources. No hashes,
regional binaries, routing or saves changed. Evidence and the reconstructed
baseline are in `data/experiments/regional-baseline-20261105/`.
