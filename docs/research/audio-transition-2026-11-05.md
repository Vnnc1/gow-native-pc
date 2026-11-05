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
This has not been implemented or measured. No speculative patch 79 was added.

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
