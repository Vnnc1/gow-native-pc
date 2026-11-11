# Open-issue sweep on v0.6.0-rc.1 and the GS frame-latency limit — 2026-11-11

Base: `fix-chore` `71a2bdb` (the `v0.6.0-rc.1` pre-release), runtime pinned at
`471c83180a8df575cff4abd3fae6c043b5096925` plus the 139-patch chain. Work was done in a Linux
container **without a disc, a GPU or a Windows host**. The issue report ZIPs and screenshots
(`github.com/user-attachments/...`) were not downloadable from it. Nothing below is a gameplay
reproduction, and no issue was commented on or closed.

## Open issues against the current branch

| Issue | Status in `v0.6.0-rc.1` | Evidence / next step |
| --- | --- | --- |
| [34: keyboard minigame judged wrong](https://github.com/Vnnc1/gow-native-pc/issues/34) | **Undiagnosed.** The screenshot is the only description of the minigame and could not be opened here. | Ask which minigame and which version. Source fact: keyboard stick directions are digital (`eje()` in `ps2_pad.cpp`: 0/128/255). Releasing one key before pressing the next passes through the stick centre, and the `zzz-317` sequence guide shows only cardinal steps. Whether the game's rotation check rejects that is unverified. The existing rotate assist (Accessibility, G by default) generates a continuous circle and is the workaround to suggest. |
| [33: freeze after the Cronos climb cutscene](https://github.com/Vnnc1/gow-native-pc/issues/33) | **Persists on 0.6.0** (reporter, GTX 1060 3 GB, with and without the new graphics options). | `zzz-305` covers the drained-reader EOF for every USA movie read through `0x188848`, so this freeze is either another mechanism or a non-USA build. Needed: the report ZIP (disc identity, runner hash, last `[gow-fmv] load` line) and a save before the cutscene. Try "skip movies" as a workaround, as in #30. |
| [31: AF / 3x / rain stutter with 45–60 FPS shown](https://github.com/Vnnc1/gow-native-pc/issues/31) | **Persists** (reporter's 2026-11-10 update: 3x still bad, AF16 drops to 30 in particle-heavy Hydra attacks). | Candidate correction `zzz-326` below. Not validated on the reporter's GPU. |
| [30: Cliffs of Madness lever cutscene](https://github.com/Vnnc1/gow-native-pc/issues/30) | **Fixed for the USA build** by `zzz-305`, included in `v0.6.0-rc.1`. The reporter tested 0.5.0. | **Europe SCES_531.33 and Japan SLPM_670.10 overlays do not contain the `gowMovieRead`/`gowMovieIsEnd` wrappers**, so the same EOF hang can still occur on those builds. Porting needs each region's own addresses and a P04MP05 completion run (see the issue-30 report); do not copy the USA addresses. |
| [28: black screen after the Hydra door](https://github.com/Vnnc1/gow-native-pc/issues/28) | **Undiagnosed.** No build, disc or report in the issue. | Ask for a 0.6.0 retest with a report ZIP. Possibly a movie at that door (the 0.6.0 USA EOF fix may already cover it), but a shared symptom is not a shared cause. |
| [20: keyboard/mouse icons](https://github.com/Vnnc1/gow-native-pc/issues/20) | Feature request, implemented since `zzz-310..314` (keyboard/mouse prompt style). | Can be answered on GitHub as available in 0.6.0-rc.1, after a maintainer check. |
| [17: Mac](https://github.com/Vnnc1/gow-native-pc/issues/17), [7: Steam Deck](https://github.com/Vnnc1/gow-native-pc/issues/7) | Platform requests. | Linux remains experimental; see `docs/linux.md`. |

## GPU-06: frames in flight on the GS worker (`zzz-326`)

### Hypothesis

The GS renders on a worker GL context that **never calls SwapBuffers**. A driver's
"maximum pre-rendered frames" limit only applies at a swap, so nothing limits how much
work the worker queues except the vertex ring: 32 MiB in four 8 MiB segments. Entering
a segment waits on the fence taken when it was last left, three segments earlier.
With a few MiB of vertices per frame that is about 12–24 frames of queued GPU work.

When the GPU is the bottleneck (AF16, 3x, many alpha-blended particles), the worker runs
ahead until the ring wraps onto an incomplete fence. Then it blocks until a whole segment
has drained (`ringStalls`). Guest frames are still counted at roughly the GPU rate, so the
counter shows 45–60 FPS while new images arrive in bursts. A pause in the menu drains the
queue. At a 55-vs-50 frame/s mismatch, a 24-frame backlog takes about 5 s to fill again,
which matches the reporter's "smooth for 5–6 seconds after the menu". This is an inference
from source and the report. No GPU trace confirms it.

Not a retest: no ledger entry bounds frames in flight. GS-04 (excluded Waffle batching) and
SYNC-01..04 (stage spin) changed batching and wait strategy, not queue depth. GPU-02/05 made
the shared-slot acquisition non-blocking and measured it. They did not touch the worker's lead.

### Change

`include/runtime/gs/gs_frame_latency.h` (new header, not included by generated code)
keeps a ring of up to 8 fences. `GSHwBackend::Present` calls `limitFrameLatency()` right after
`flushPending()`/`endGpuSample()`:

- fences that have already completed are retired with a zero-timeout poll (no wait when the GPU keeps up);
- one new fence marks the end of the frame's draws;
- while more than `GOW_GS_FRAME_LATENCY` frames (default **2**, clamped to 0..7) are pending,
  it waits on the oldest with `SYNC_FLUSH_COMMANDS_BIT` and a **50 ms** timeout.

These fences guard no memory. The ring's own fences still protect the vertex data. So a
timeout or a failed `glFenceSync` just continues: no `glFinish`, no unbounded wait.
`GOW_GS_FRAME_LATENCY=0` releases the fences and restores the previous behaviour as the reference.
Under `GOW_GS_HW_STATS` a `[gs-hw-latency] limit= frames= waits= timeouts= wait_ms=` line follows
`[gs-hw-wrap]` every 5 s. `[gs-latency-config] frames=N` is printed once, for A/B harnesses.

What to expect, if the hypothesis holds: on a GPU-bound scene the guest rate drops to what the
GPU actually sustains, but frames arrive evenly, with up to ~20 fewer frames of input latency
and no periodic multi-frame ring stalls. On a CPU-bound machine (i3/i5 notebooks, VU1-saturated)
frame N-2 has normally completed already, so the expected cost is one fence and one poll per frame.

### Validation done here

- `tools/test/gs-frame-latency.cpp` (`gow_frame_latency`, added to `verify`): GPU keeping up
  (never waits), GPU-bound (exactly `limit` pending, FIFO waits), timeouts (no further blocking,
  no fence leak), failed fence creation, limit changes, clamping and `0` releasing every fence.
  Passed with g++ `-std=c++20 -Wall -Wextra`.
- `gs_hw_backend.cpp` with the patch passes `clang++ -std=c++20 -fsyntax-only`.
- The whole 140-patch chain applies in ordinal order to the pinned runtime commit, and the
  result is identical to the edited source.

### Not validated (acceptance gates before calling #31 fixed)

No game run, GPU, Windows build, PGO build, FPS or frame-pacing measurement was possible.
Regional overlays were not rebuilt. In the same scene and settings, compare
`GOW_GS_FRAME_LATENCY=0` against the default:

1. GTX 1060 3 GB (reporter): Captain's Cabin rain at 2x/AF off, Hydra particle attack at AF16, menu at 3x.
   Use a report with `GOW_GS_HW_STATS=1` (ringStalls, latency waits) and guest/acquisition intervals.
   Success means fewer >33 ms guest intervals and no 5–6 s stutter cycle. The average FPS may legitimately drop.
2. A CPU-bound notebook (i3-10110U or i5-8265U), fixed arrival route: no FPS/p99 regression.
3. RX 580 PERF-06 arrival probe: no regression, and movies (EOF tail) still complete.
4. If the limit costs FPS on any CPU-bound tier, try 3 before turning it off. Record every run in the ledger.

## Running the comparison (i3-10110U and other machines)

The machine needs a game rebuilt with this chain (`fetch,sync,build`; build both the runner and
`gow-session`). `gs-run-ab.py --compare frame-latency` alternates `GOW_GS_FRAME_LATENCY=0`
(reference) with the shipped value 2, and keeps every other renderer switch at its shipped default.
It enables the bounded `GOW_GS_HW_STATS` counters in both variants. A run is rejected unless its log
contains `[gs-latency-config] frames=<expected>`. Each run also records `latency_waits`,
`latency_wait_ms` and `ring_stalls`, next to the usual frame-interval percentiles and
>33/50/100 ms counts. Use a new output directory for every invocation:

```powershell
python -I tools/test/gs-run-ab.py --runner <runner.exe> --elf <prepared-disc/SCUS_973.99> --collector <gow-session.exe> --output <new-output-directory> --compare frame-latency --scene ship_arrival_frames --pairs 3 --seconds 120 --warmup 30 --gpu-samples
```

On the i3-10110U, the gate is "no regression": the CPU (VU1) is the bottleneck there (GAIN-11/12),
so waits should be rare. The ship arrival scene is short and CPU-bound. For the GPU-bound case, repeat
with `--scale 2 --env GOW_ANISO=16` (or the reporter's settings) in a heavier scene with a private card.
Expect fewer `ring_stalls` and fewer >33 ms intervals with the candidate. Record every run, including
rejected ones, under GPU-06 in the ledger and in `docs/tested-hardware.md`.
