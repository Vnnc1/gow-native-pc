# Gameplay reports

Every game started through the launcher gets a local session report. No report is uploaded automatically.

The private diagnostic kit's detailed mode also records `[gs-cache]` for patch 60:
resident decoded-texture bytes, budget, cumulative evictions and cumulative storage
reuses. These are not total process/GPU memory measurements. The regular FPS mode
does not enable these renderer statistics. The collector preserves the numeric fields
in `metrics.jsonl` and records `GOW_GS_HW_STATS` when explicitly set.

1. Play normally. Basic collection records guest FPS/frame intervals and process health. If an issue repeats,
   enable **Performance → Audio and compilation diagnostics** before the next launch. Detailed timing can lower
   FPS; identify that mode when comparing performance.
2. When a problem occurs, return to the launcher through the taskbar and use **Other → Mark a problem during play**.
   Describe the area and symptom, then choose **Mark now**. The marker uses the collector's session clock; it is not
   an exact guest-frame replay point. Do not enter personal information.
3. Close the game, then choose **Other → Export report ZIP**. The same export action is available in the error dialog.
   The launcher shows the ZIP path and opens its containing folder. A live export is possible, but only contains
   evidence available at that moment. Export again after a crash or normal exit to include the final status.
4. Review the ZIP and attach it to a bug report in this project's issue tracker. Include the game area/save point,
   reproduction steps, expected and actual behavior, whether this was the first visit, and the marker/approximate
   time. A screenshot or short video can help with visual errors, but must be selected separately. Do not attach an
   ISO, extracted game data, memory cards or credentials.

## Contents and interpretation

| Evidence | Meaning |
|---|---|
| `session.json` | Session ID, UTC times/status, actual executable and ELF hashes, OS/CPU/RAM, display adapters/drivers, settings, source patch hashes and selected build options |
| `startup.log` | First 256 KiB, including renderer/device initialization when the runtime emits it |
| `runtime.log`, `runtime.1.log`, `runtime.2.log` | Current and two previous 4 MiB logs, with milliseconds since collector startup |
| `metrics.jsonl` | Structured runtime windows and five-second process samples, capped at 4 MiB |
| `events.jsonl` | Player markers, process errors/exit, warning candidates and audio missing-frame events, capped at 1 MiB |
| `README.txt` | Interpretation and sharing instructions embedded in the ZIP |

Normal mode uses `GOW_PERF_DIAG=frames` and `GOW_FRAME_DIAG=1`. The runtime's frame function comes from the game
profile. Five-second windows include guest FPS, host loop frequency, guest interval mean/p50/p95/p99/maximum and
counts above 16.67, 33.33, 50 and 100 ms. Guest intervals include pauses and loading; they are **not display latency
or measured GPU time**. Host loop frequency is not proof of distinct displayed game frames. Percentiles use nearest
rank over at most 4,096 intervals per window; `intervals` and `samples` expose any overflow, while totals/maxima count
all intervals. No window is emitted while the guest frame function stops; use the host heartbeat and last output time.

Runners with patch `zzz-307` also emit `[gow-present]` in the shared-texture path under the same diagnostics.
`fresh` counts acquisitions of a new publication sequence; `repeated` counts reuse, `unavailable` failed acquisition,
and `blank` blank output. Their sum is `polls`. `skipped` counts publication sequences skipped between valid
acquisitions, not lost guest frames. `acquire_hz` is fresh acquisitions divided by the reporting window.
`max_hold_ms` measures the oldest retained acquisition observed, including the interval before its replacement
and holds spanning report windows. These are not changed-pixel counts, scanout, GPU time or input latency.
The RAM presentation path and older runners omit this tag; absence is not zero. A blocked host cannot emit
a window until it resumes: inspect the last output time alongside guest/audio/process activity.

Before patch `zzz-308`, minimizing the game could stop host reporting while guest/audio
continued, and closing it while minimized could end in the collector's forced termination.
Include whether the window was minimized/restored when reporting this signature. A missing
host window alone cannot distinguish that condition from another host/driver stall.

Detailed mode also enables exclusive elapsed-time buckets (EE/VU/GS/IOP and waits), VU1/JIT counters, audio requested,
missing/dropped frames, playback-rate ceiling/buffer range and IOP cycle drift. These measure elapsed time or runtime
counters, not hardware CPU/GPU utilization. Some counters may be absent depending on code paths, disabled sound,
missing devices or an older runner. Missing values mean unavailable, never zero. Sound-device startup failures remain
in the raw log. Selected graphics hardware is established by the runtime's renderer initialization, not by the list
of installed adapters or the launcher's GPU preference.
In basic mode, the raw runtime line prints zero timing buckets; structured metrics omit these unavailable buckets
and set `timing_scopes_enabled=false`. The session's observation summary includes startup and loading windows, so
its minimum FPS and maximum interval are investigative leads, not a gameplay benchmark.

Detailed VU1/JIT output is also parsed from the runtime's `[vu1n]` and `[vu1x]` tags into `metrics.jsonl`.
These counters include native misses, lane failures, compiled blocks and unsupported blocks; their values are
not FPS. Most `[vu1n]` activity counters reset after each roughly five-second report; `[vu1x]` compilation counts
are process totals. `native_missBlocks_max_counter` is the largest observed window count, not a session sum.
`compiled=0` can mean the existing AOT code covered the scene;
it does not prove that JIT execution has been tested.

Windows process samples include CPU (`100%` = one logical core; values can exceed 100), working set/peak/private bytes,
page faults, cumulative I/O byte counts, available system RAM and AC/battery state. Battery value 255 means unknown.
There is no GPU utilization, VRAM, temperature or clock-speed sensor collection yet. A quiet log or a matching warning
word is a lead to investigate, not proof of a hang or defect; even a line saying "0 errors" may match the warning filter.

Detailed mode also enables `[gow-sync]` worker/GS-stage wall-time aggregates. Site 0 is the large-VIF1 barrier, site 1
is MMIO and site 2 is other explicit synchronization. `worker_ms` and `stage_ms` are sequential portions of the wait,
including locking overhead, not GPU timings. `stage_waits` can be nonzero while `worker_waits` is zero. Intervals are
approximately five seconds with a partial final flush. `[gow-sync-config]` reports effective barrier/worker/timing
settings, so an omitted environment override is not mistaken for a disabled feature. These metrics are opt-in.
VU1 task corpora are separate local research files and are never included in exported player reports.

The source/configuration snapshot describes files at launch. Local changes may not have been compiled; use
`runner_sha256` to distinguish actual binaries. Reports are written atomically at each heartbeat and exit. A remaining
`running`/`starting` state with a stale heartbeat indicates interrupted collection or an incomplete live snapshot;
it does not establish the game's exit cause. Windows exception codes are also recorded in hexadecimal.

## Storage, privacy and lifetime

Reports live under the launcher's application-data folder (`registros/sessions`), separate from pipeline logs in
`data/<game>/logs`. The collector is a separate `gow-session` process and continues if the launcher closes. Use the
game's close action normally; the launcher's stop action asks only this session's child to close, then records a
forced termination if it has to kill that child after five seconds.

At new-session creation, the ten newest completed reports are retained. Active or interrupted reports and exported
ZIPs are not automatically deleted; old ones can be removed manually after review. Each session uses bounded logs
and records rotation/truncation/write-failure flags. A long session can fill the metrics cap: export/reproduce a
shorter session when a late issue needs detailed counters.

The export reads only the report-file allowlist. It does not include the ISO, game files, saves, images, arbitrary
environment variables, boot profiles or crash memory dumps. Known home/project/disc/build/temp paths and email-like
strings are redacted before logging. Redaction is best effort: user notes and unusual runtime output can contain
personal data, so review before sharing. Nothing automatically posts an issue or sends a message.

## Maintainer validation

- `build.cmd -Stages fetch,verify,build,launcher`: apply/validate the ordered patch chain, test bounded frame metrics
  and existing call/codegen behavior, then build the game and launcher/collector.
- `python -I tools/test/session_diagnostics.py launcher/build-clang/deploy/gow-session.exe`: synthetic child processes
  test real nonzero/crash/failed-start outcomes, metrics, redaction, markers, stop, rotation and ZIP integrity.
- `python -I tools/test/session-game-smoke.py`: prepared-disc functional check with a private card, scripted input,
  sound enabled and a hidden game window; tests gameplay, VU1 parity, frame windows, markers and report export.
  This test is not an FPS benchmark or a listening/rendering quality certification.

Compare normal versus detailed diagnostics separately. Measure collector overhead in controlled paired runs before
claiming it is negligible on a hardware tier. The public stable-60-FPS gate still requires visible, audible play.

## Queue capacity waits (patch 59)

With `GOW_SYNC_DIAG=1`, `[gow-queue]` separates producer backpressure from the
existing explicit synchronization metrics. Queue 1 is the VU1-to-GS stage ring;
`queued_peak` is occupied ring bytes (including record overhead/padding). Queue 2
is the GS backend queue; `queued_peak` is pending chunks, excluding the active chunk.
Configuration records contain `enabled=1` and the effective spin/queue limits.
Wait records contain `window`, `waits`, `wait_ms`, `max_ms`, and `final`.

Only initially full capacity checks are timed. Stage timing includes its spin and
condition-variable wait; backend timing starts after acquiring the queue mutex.
Neither includes initial mutex-acquisition time. Counters are producer-serialized,
bounded, emitted at most once per five seconds when waits occur, and flushed at
shutdown (`final=1`). A wait crossing a window is charged in full when it ends;
intervals need not align with FPS windows. Absence of wait records is not evidence
of disabled instrumentation; check the configuration record. Abrupt exit can lose
the partial window. Disabled diagnostics read no per-wait clocks.

These are elapsed waits, including scheduling, not CPU/GPU utilization. They can
overlap other scoped times and must not be added to VU/GS buckets as frame time.
Detailed runs diagnose bottlenecks; compare FPS separately with diagnostics off.
The collector retains these records and the explicit stage-spin/chunk-limit values
without changing the report file allowlist.

# Developer audio trace

For developer-only audio transition diagnosis, patch 78 enables `GOW_AUDIO_TRACE=1`
(`session-game-smoke.py --audio-trace`). It stores up to 512 events per sound engine
and emits `[gow-audio-trace]` records after audio shutdown. Normal playback does not
enable it. `kind=0` is a reset (available frames discarded), `kind=1` a partial/empty
drain, and `kind=2` an acquisition or drain lasting at least 1 ms. Reset/publication
counters and `total_published` are lifetime totals for that engine.
For drain events, `available` is the queue after latency trimming; `total_published`
also includes samples later discarded by queue limits or reset.

Use each event's `t_us`, relative to its `begin=1` marker, for event timing: the
collector's `elapsed_ms` on dumped events is their late emission time. Acquisition
`wait_us` includes thread scheduling as well as mutex acquisition; `drain_us` includes
existing audio-stat logging when enabled. Neither is pure CPU execution time.
`producer_age_us` is valid only when `producer_known=1`. Require matching begin/end
markers, zero overflow and complete event counts; forced termination can lose the
trace. These diagnostics do not establish clean FPS or audible quality.

Patch 79 adds `grant_cycles`, `sound_base`, `total_cycles`, `run_grant` and
`pending_iop`: the producer's last service snapshot before the recorded publication,
not scheduler values at callback time. Context is invalid after reset until the
next publication (`producer_known=1`). `reason` identifies that publication:
0 batch, 1 explicit flush, 2 other register read, 3 register write, 4 sample RAM,
5 stream change, 6 stream position, 7 stream-half check, 8 envelope read,
9 other parameter read. `frames_*` are cumulative published stereo frames by reason,
not call counts or CPU timings. Their sum equals `total_published`, including frames
later discarded. Default audio timing and buffering are unchanged.
`pending_iop` is normally zero because the scheduling batch clears it before
running the IOP; zero does not exclude a lack of upstream EE progress. Disabled
tracing still adds a call/null check and reason arguments, but no trace clocks,
allocation or logging.

# Private diagnostic kit

`gow-diagnostics` is a separate Windows frontend for a precompiled test runner.
Its installer identity and Qt application data are independent of the normal launcher.
It validates the profile ELF code hash, required prepared-disc files and runner/helper
hashes, then uses the existing detached collector. Each run copies the adjacent card
to private application data; reports never include that card. See
[the Portuguese test guide](diagnostic-kit.pt-BR.md) for the player workflow.

The collector also exports `summary.json` and `RESUMO.txt`, derived only from bounded,
redacted report files. FPS summaries exclude windows overlapping the first 30 seconds,
weight by window duration and retain zero-FPS windows. They still include later menus
and loading; they are not controlled benchmarks. Queue totals cover the whole session.
The median of window p95 values is not a pooled p95. VU1 misses are interval counters;
JIT unsupported counts are cumulative. Unavailable counters are omitted. The GS renderer
comes from the actual context startup line. Alerts indicate observations, not root causes.
