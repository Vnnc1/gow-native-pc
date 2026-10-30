# Review of patches 28 and 29 before the memory fast path

Scope: `claude/keen-dirac-42wd1y`, starting at `91ddfc8`, pinned runtime `471c831` plus patches 01–29.
The review is on Windows with an Intel Core i5-8265U, 24 GB RAM and llvm-mingw clang 23.1.4, Release, LTCG off.
The local checkout initially had neither a runtime nor prepared game data. The pipeline's portable tools were
downloaded and verified, and the complete patch chain applied successfully to the pinned runtime.

## Findings

### Diagnostic settings are frozen before standalone boot restores the environment

Patch 28 initializes `g_ps2FullCallDispatch` and `g_ps2CallWatchPc` during C++ static initialization. Patch 25 restores
`gow-native.boot` inside `main`, before constructing `PS2Runtime`. A full-dispatch flag or frame PC supplied by that
profile therefore cannot affect the lean call path. In particular, watched JAL/JALR calls can skip `guestEntry`,
undercounting guest FPS even though the other performance diagnostics are enabled. An inherited setting overwritten
by the boot profile has the converse problem.

The regression sets the environment after `main` begins, constructs the actual runtime, and observes both branch-ring
increments and the actual guest-frame counter. It exercises JAL and JALR separately, including an unwatched address
that must remain lean.

Fixed by `29a-call-diagnostics-init.patch`: both options are instance fields initialized in the constructor, after
boot-profile restoration. The hot call path still performs no environment lookup or local-static initialization.
An additional test clears an inherited flag and creates two runtimes with different settings; one cannot change
the other's routing.

### The worker trace interval starts at a different event

Patch 29 moves `traceStart` into `gsWorkerTraceEvent`. Its first execution is the first *watched* function, whereas the
previous implementation initialized the clock on the first dispatched call. A late first `vid::Flip` consequently
shifts the two-second capture window. The regression dispatches an unrelated function, waits 2.2 seconds, then
dispatches a watched address with `PS2X_GS_WORKER_TRACE=0`; no trace record should be emitted after that window.

Patch 29a starts the shared diagnostic clock when the first dispatched call checks tracing, while retaining patch
29's gate around trace helpers on ordinary calls.

### Existing test infrastructure needs a separate entry point

The full `ps2x_tests` build fails in `ps2_memory_tests.cpp`: it still calls `processPendingTransfers`,
`tryProcessNativeGifImageUploadChain` and `tryProcessNativeGifPackedChain`, which are absent from the pinned memory
interface before patches 28/29. This review does not reintroduce obsolete runtime APIs to make those tests compile.

The isolated CodeGenerator suite initially had two stale assertions requiring the older `Store32` spelling for
native DMA/timer accesses already present in the pinned recompiler. `29b-codegen-mmio-tests.patch` updates these
expectations and explicitly preserves effective-address validation, value operands and the generic-store fallback.
Its VU0 enum test also needs the runtime source directory as its working directory; the CTest entry sets that.

## Results (2026-10-28)

| Check | Original patches 01–29 | With 29a/29b |
|---|---|---|
| Lean/full call parity, cycles, invalid targets, overrides | 111 checks passed | 111 checks passed |
| Environment restored after process startup: full/watch/trace | All three scenarios failed | All passed |
| Worker trace window after a late watched function | Unexpected trace emitted | No out-of-window trace |
| Clearing an inherited setting / independent runtime instances | Additional follow-up coverage | Passed |
| JAL/JALR codegen: classic/locals × lean/dispatch | All four passed | All four passed |
| Isolated upstream CodeGenerator suite | Two stale MMIO expectations | 68/68 passed |
| Full upstream test executable | Build blocked by obsolete memory-test APIs | Still blocked; not claimed green |

The final dedicated suite has ten isolated scenarios and 162 C++ checks, plus positive/negative trace-window assertions.
Pipeline `fetch` verifies all patches, including 29a and 29b, form a valid chain and exactly match the runtime files.
No gameplay, GS-frame equality, AMD/NVIDIA rendering or FPS improvement is claimed: no ISO/prepared disc was available.

Follow-up after the user supplied a compatible PT-BR disc: the complete game now builds with Clang, reaches gameplay
and passes 2,000 VU1 comparisons. Three paired same-binary lean/full runs average 42.90 / 41.59 guest FPS on this
laptop. This small observed difference is not a main-branch comparison or frame-exact equivalence claim.
See [current hardware evidence](../tested-hardware.md) and [build foundation](build-foundation-2026-10-28.md).

Evidence (generated, not committed): `data/gow1/logs/guest-calls-before/`, `guest-calls-after/`,
`review-codegen-tests.log`, `review-build.log` (full-suite compile failure), and `review-patch-chain.log`.

## Reproduction without a disc

`tools/test/guest-calls.cmake` adds a test executable to the existing runtime build using CMake's project include hook.
It links the real runtime and recompiler; no replacement dispatcher or simulated scheduler is used.

Configure `engine/runtime/PS2Recomp` into a short, dedicated build directory, using the repository's clang toolchain
and these options (absolute paths for the compiler and hook):

```text
-G Ninja -DCMAKE_BUILD_TYPE=Release
-DPS2X_BUILD_STUDIO=OFF -DPS2X_BUILD_ANALYZER=OFF -DPS2X_BUILD_TEST=OFF
-DPS2X_RELEASE_LTCG=OFF -DPS2X_ENABLE_DEBUG_UI=OFF
-DCMAKE_PROJECT_PS2RetroX_INCLUDE=<repository>/tools/test/guest-calls.cmake
```

Build targets `gow_guest_calls` and `gow_codegen_tests`, then run (put the clang toolchain's `bin` on `PATH` on Windows):

```text
python -I tools/test/guest-calls.py <build>/gow_guest_calls.exe data/gow1/logs/guest-calls
ctest --test-dir <build> -R "^gow_codegen_tests$" --output-on-failure
```

The script runs return/transfer/stop/checkpoint/nested-call parity, missing/misaligned/out-of-range targets with all
three missing-function policies, cycle accounting, replacement overrides, diagnostic initialization, trace timing,
and JAL/JALR generation in both classic/locals modes with both lean/full-dispatch backends. Each subprocess gets a
clean runtime environment. Logs and `summary.json` go to the requested output directory.

## Acceptance before patch 30

Patch 30 is still a proposed memory-access optimization in the roadmap; it is not present on this branch. The call
optimizations and memory optimization need independent acceptance. Synthetic call parity is necessary but does not
establish gameplay equivalence or a game frame-rate improvement.

With a prepared disc, regenerate the guest C++ (`recomp,sync,build`), run the same pad script with and without
`GOW_DISPATCH_FULL=1`, verify gameplay/clean shutdown and compare guest-frame diagnostics and GS output. Include a
no-argument standalone launch with diagnostics supplied only by `gow-native.boot`. Use identical renderer, resolution,
audio and VU1 settings; host presentation Hz is not guest FPS. Later areas and another GPU remain separate coverage.

For patch 30, add boundary tests before removing memory checks: RDRAM end-straddling accesses at every width, all
supported aliases, scratchpad boundaries, MMIO side effects, and a slow-path reference comparison. `$sp`/`$gp` names
alone do not prove an arbitrary function's effective address belongs to RDRAM. A mirrored tail must reproduce the
existing wrap semantics for writes as well as reads.
