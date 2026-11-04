# Renderer delivery review — 2026-11-04

Follow-up: the corrected patch 66 has now been isolated and integrated directly onto 01–58. See
[integration, validation and laptop results](integration.md). The findings below describe the original delivery;
the ring-buffer overlay remains review-only and has not been imported into the production patch chain.

The delivery has plausible CPU-side optimizations, especially patch 66's primitive grouping, but does **not**
establish higher gameplay FPS or better frame pacing on this laptop. Two reproducible correctness defects block
promotion of the delivered defaults. Review overlays below fix those defects in an isolated source copy; they are
not part of `engine/patches`, the installed executable, or a performance-support claim.

Reviewed input: `gow-render-engine-delivery-2026-11-04`, supplied beside this checkout. Project baseline:
`7426579`, branch `fix-chore`; pinned external runtime `471c83180a8df575cff4abd3fae6c043b5096925`.
The Ponytail full workflow was used: trace callers, reproduce defects, make narrow corrections, rerun checks.

## What the delivery actually demonstrates

| Change | Potential benefit | Evidence and remaining gate |
|---|---|---|
| 59: 32 MiB vertex ring | Reduce repeated vertex allocation/upload overhead | Unsafe mapped-buffer reuse in the original; no local GPU-driver or frame-time validation |
| 60: VU1 JIT fast mode | Bring the JIT closer to the existing optional AOT fast arithmetic | Changes exceptional floating-point semantics; require AOT/DLL/JIT differential tests, keep opt-in |
| 61: two-pass shuffle and texture reuse | Reduce draw calls and repeated texture decoding | Need renderer output parity, wrapped texture-span coverage, and Intel/AMD/NVIDIA checks |
| 62–65: cost/hot-entry/opcode diagnostics | Locate expensive functions and synchronization | Diagnostic instrumentation is not an FPS optimization; keep expensive timing out of acceptance runs |
| 66: primitive grouping | Amortize state copying, allocations and queue submission | Best first isolated candidate; original encoder reads beyond a local vertex; full decoder/order/GPU parity remains open |

The supplied `verification/VERIFICATION.md` reports frontend cost falling from 366–427 to 86–118 ns/vertex.
That is a subsystem measurement, not a proportional game speedup. Its diagnostic sample shows 19.56–21.16 guest
flips/s while host presentation is about 59 Hz; a separate clean-build smoke sample reaches 35.18 guest flips/s.
These are different samples, not a before/after FPS comparison. The report explicitly makes no FPS-gain claim.

The tests use the Japanese `SLPM_670.10`, hidden window, 0.5x scale, audio disabled, optional VU1 fast mode and
intrusive timing. They cannot certify USA/PT-BR gameplay, visible audio-enabled play, this laptop, or the RX 580.
CPU/GPU identification, paired repeated frame-time distributions and raw benchmark logs are absent from the
provided verification material. Overlapping `vu_ms` and `gs_ms` windows do not alone identify the critical path.
Static/black frame hashes and drifting animated screenshots do not establish animated rendering equivalence.

## Confirmed defects and review fixes

### P1: Run encoding reads beyond the default vertex

Delivery source: `PS2Recomp/ps2xRuntime/src/lib/gs/gs_threaded_backend.cpp`, `SubmitRun`, original lines 474–476.
The frontend supports point primitives; its runs reach this compact encoder and then the worker's `Op::Run`
decoder. With one active vertex, the encoder copies two vertices from a single local `GSVertex empty`.
Zero-count input copies three. The classic path initializes each missing vertex separately.

AddressSanitizer reproduced `stack-buffer-overflow`, including an 80-byte read from a 40-byte object for the
one-vertex case. This is a memory safety defect, not evidence that it caused a particular observed game hitch.

[`submit-run-tail.patch`](submit-run-tail.patch) uses a three-element default-initialized array and copies only
the required elements. It preserves `GSVertex::q = 1`; replacing the tail with zero bytes would break classic
field equivalence. The fix does not change queue layout or active vertices.

### P1: Persistent vertex storage is reused before the current GPU work completes

Delivery source: `PS2Recomp/ps2xRuntime/src/lib/gs/gpu/gs_hw_backend.cpp`, `ringAppend`, original lines 2583–2596.
Both ordinary vertex uploads and shuffle uploads use this allocator. The first wrap inserts a fence and immediately
overwrites the beginning of the mapped buffer without waiting. Later wraps wait on an older generation, and ignore
the final timeout/failure result. Coherent mapping does not transfer ownership of storage still read by the GPU.

A mock GL completion protocol, executing the actual delivered allocator body, fails on the first wrap. It also
checks three successive generations and incomplete/error waits. This establishes faulty ordering; it does not
claim visual corruption was observed on a real driver.

[`vertex-ring-fence.patch`](vertex-ring-fence.patch) fences the current generation at each mapped wrap, waits for
completion, and uses `glFinish` if fence creation/waiting cannot establish completion. Each created fence is deleted.
The unmapped `BufferSubData` fallback retains driver-managed synchronization. No synchronization is added before a wrap.

This is a conservative correctness repair. Waiting for the GPU can stall the CPU; the patch is **not** a frame-pacing
optimization. A future segmented ring must retire each region independently and prove ownership before reuse.
The semantics follow the primary specifications for
[persistent buffer storage](https://raw.githubusercontent.com/KhronosGroup/OpenGL-Registry/main/extensions/ARB/ARB_buffer_storage.txt)
and [client fence waits](https://raw.githubusercontent.com/KhronosGroup/OpenGL-Refpages/main/gl4/glClientWaitSync.xml).

## Local checks and reproducibility

`tools/test/render-delivery-tests.py` extracts the actual function bodies from the supplied source and compiles them
with pinned llvm-mingw Clang 23.1.4, C++20, `-O1`, AddressSanitizer and assertions. It uses the delivered GS types,
stubbed inventory/publication, and a mock GL API. This is not a full runtime build or full queue execution test.

| Check | Original delivery | Corrected scratch copy |
|---|---:|---:|
| Encoder counts 0, 1, 2, 3, plus 129 mixed primitives crossing the 64-primitive record boundary | 2/5 pass; 3 ASan failures | 5/5 pass |
| Ring: no wrap, current completion, already signaled, timeout, failed wait, null fence | 1/6 pass; 5 ordering assertion failures | 6/6 pass |
| Both overlay patches apply to a fresh delivery copy | Applicable | Applied result matches tested source, ignoring line endings |

Encoder comparisons inspect every vertex field, including inactive tails, against the actual classic branch.
They do not compare unspecified struct padding. The ring uses a reduced test capacity to exercise repeated wraps;
it does not measure OpenGL performance, driver recovery or application shutdown.

From the project root, with the supplied folder still beside the checkout:

```powershell
& data/_tools/python/python.exe -I tools/test/render-delivery-tests.py `
  --runtime ../gow-render-engine-delivery-2026-11-04/runtime/PS2Recomp/ps2xRuntime `
  --compiler data/_tools/llvm-mingw-20261020-ucrt-x86_64/bin/clang++.exe `
  --output data/render-review-20261104/original

& data/_tools/python/python.exe -I tools/test/render-delivery-tests.py `
  --runtime data/render-review-20261104/candidate/PS2Recomp/ps2xRuntime `
  --compiler data/_tools/llvm-mingw-20261020-ucrt-x86_64/bin/clang++.exe `
  --output data/render-review-20261104/corrected
```

The first command intentionally returns failure on the original. Each output directory contains build logs,
per-case logs, extracted sources and `summary.json` with source SHA-256 identities. The candidate and the separate
patch-application check tree were created under ignored `data/render-review-20261104/`; the supplied directory was
not edited. Overlay paths are relative to its `runtime/` directory; apply them only to a scratch copy of that tree.

The normal runtime, build output, installed runner, game data and saves were not modified by this review.
No full `build.cmd -Stages verify`, gameplay benchmark or GPU test was performed: no production runtime change
was installed. Those remain mandatory when promoting a candidate into the real patch chain.

## Integration findings

All 64 existing project patch files match the corresponding delivery files after CRLF normalization. Eight files,
59–66, are new. An isolated Git index loaded from the pinned runtime successfully applied the first 64 patches and
then failed at `59-gs-vertex-ring.patch`. The complete delivery diff applies to that pristine index successfully.
This local result differs from the delivery's claim that 29a also fails: 29a applied in ordinal order here.
Neither check modified the real runtime index or working tree. Evidence: `data/render-review-20261104/` files
`patch-comparison.json` and `delivery-applicability.json`.

The complete diff is a whole-baseline replacement, not an incremental patch for the current installation.
Its exclusion of the delivery's local `src/gow_overrides.cpp` instrumentation and the Japanese validation setup
must not be turned into a global USA runtime overlay. Reconstruct the intended delta and regenerate ordinal
patches before integration, preserving isolated regional builds and PGO identity checks.

Additional unresolved audit items: the ring accepts a byte count without checking its 32 MiB capacity, while the
pending vertex vector has no explicit capacity gate in the inspected path; establish an upper bound or split
uploads safely before promotion. Texture revalidation hashes a span clamped to the VRAM end; reject or correctly
cover wrapping spans and test invalidation before treating hash equality as full source equality. These are
code-review risks, not failures reproduced in gameplay by this investigation.

## Next execution phases

1. **Recover a reproducible candidate.** Repair ordinal patch applicability in a separate runtime; initially keep
   ring and texture reuse disabled, optional fast arithmetic off, and expensive diagnostics off. Bring in the
   corrected primitive grouping as its own concern; run the full runtime `verify` gate and an actual game build.
2. **Prove behavior.** Exercise point/line/triangle runs, state changes, uploads/CLUT/TEXFLUSH/FINISH and publication
   boundaries in the real backend. Compare deterministic GS command streams on grouped/ungrouped paths, then
   visible USA/PT-BR gameplay with sound. Keep private test cards. Static screenshots alone are insufficient.
3. **Measure on this laptop.** At least three paired runs per setting after warm-up, same binary/build flags,
   CPU/GPU power conditions, disc, scene, resolution and input. Start with `PS2X_GS_RUN=0/1`; keep ring/reuse/fast
   arithmetic fixed. Use frames-only diagnostics with the profile's frame PC. Report guest FPS, interval p50/p95/p99,
   long-frame counts, first-visit stalls and audio behavior; guest intervals are not presentation latency.
4. **Separate CPU and GPU limits.** Repeat at 1x and 0.5x as distinct experiments, not mixed samples. Profile waits
   in a separate intrusive run. If grouping lowers submission cost without changing frame time, prioritize the
   measured remaining VU1/GS/EE dependency instead of increasing batch sizes blindly.
5. **Promote independently.** Validate bounded ring reuse under GPU lag and texture/shuffle parity before enabling
   each optimization. Run the same acceptance gates on the RX 580 and other supported GPU families separately.
   Keep fallbacks and reject regressions in tail frame times even when average FPS rises.

Stable 60 guest FPS remains the target. Neither this delivery nor these local correctness tests demonstrate that
target on the laptop, and they do not establish a percentage gain or universal hardware support.

Next execution: [scene-controlled CPU/GPU investigation and opt-in countdown](scene-bottlenecks.md).
