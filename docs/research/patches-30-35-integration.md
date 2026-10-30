# Patches 30–35 integration (2026-10-29)

The four supplied PowerShell scripts describe successive attempts at the same patch series, following 29f.
The repository already contained the profile, launcher and PGO edits and a partially applied patch 30.
The integration preserves those changes and stores each runtime change as its own replayable patch.

| Patch | Behavior |
| --- | --- |
| 30 | Inline classification of four RDRAM aliases, unlikely scalar wrap paths and removal of impossible aligned 128-bit wraps; memory regressions included. |
| 31 | Explicit Clang ThinLTO when LTCG is requested, plus non-MSVC Release hidden visibility. |
| 32 | Non-MSVC Release math flags; an explicit x86-64-v2/v3 compiler target replaces the upstream unconditional native target. |
| 33 | Drain earlier GS/VU1 work before another VIF1 packet of at least 64 KiB is submitted, when enabled. |
| 34 | Cheaper bookkeeping on self-chains with idle timing, no scalar starts/tail and preserved clean lanes. |
| 35 | Generated C++ self-loops remain inside their function; the x64 JIT can jump directly to its own body after bookkeeping. |

## Corrections to the supplied scripts

- Do not delete patches, clean the runtime or reset the user's Git index to construct a patch. Generate incremental
  diffs against the preceding patch tree using a temporary index, then replay the whole chain from the pinned commit.
- Match the current CMake `elseif(IPO_SUPPORTED)` block, including its warning fallback. Separate patches 31 and 32;
  the last script otherwise saves patch 32 without a new diff. Keep each CMake generator-expression flag separate.
- Restrict patch 33 to DMA delivery. A global replacement also changes the constructor, where `path` and `size`
  do not exist. Call the existing `syncGsWorker`, preserving both worker and GS-stage self-wait guards.
  Snapshot the setting per memory instance; explicit `0` disables it, and absence inherits asynchronous FINISH.
- Adapt slot setup to the actual scalar-pair representation (`uint8_t` indices into decoded instructions).
- A false `chainSelf` result has already completed the block's exit accounting. Return `kVu1nDone` immediately;
  calling `chain` again double-counts that block. The JIT follows the same single-accounting contract.
- Keep the portable CPU tier. An unconditional `-march=x86-64-v3` removes it, while a later upstream `-march=native`
  silently overrides a command-line choice. `PS2X_CPU_ARCH` now controls the runtime's target explicitly.

## Build and diagnostic controls

`build.cmd -Stages fetch,configure,build` uses the portable x86-64-v2 baseline. A prepared disc and synchronized
generated EE sources are still required to build the game; a fresh installation must run the normal preparation
and recompilation stages first.

`build.cmd -Stages configure,build -CpuTarget x86-64-v3` selects an AVX2-class build explicitly. Add `-Ltcg` to test
ThinLTO. Every invocation selects its target again; omitting `-CpuTarget` selects portable. Both choices are part of
the configure signature. ThinLTO remains opt-in, and neither choice establishes a supported performance tier.

The profile's `build.unity_batch = 16` is used with at least 14 GiB physical RAM; smaller machines retain 8.
Existing PGO training changes use the supplied renderer settings and x64 JIT. They are training inputs, not an FPS
benchmark. No full-game PGO, build-time or performance comparison has been performed for this series.

`GOW_VU1_EARLY_FINISH=0` disables the packet barrier for comparisons. The launcher and PGO training explicitly
enable it. The 64 KiB threshold is a packet-size heuristic: it does not prove one packet equals one guest frame.
DMA completion semantics remain those of patches 29d–29f.

## Regression checks

`build.cmd -Stages verify` includes the existing pipeline, memory/DMA, codegen, guest-call and frame-metric checks,
plus procedural VU1 backend comparisons through `tools/test/vu1-equivalence.py`. The VU1 check compares generated
DLL blocks with x64 inline/helper/SSE/no-speculation modes, checks special input values, and checks state plus
native-block counts for self-loops at 7 and 20,000 cycles (budget and depth-limit exits).
The separate `gow_dma_worker_tests` exercises the VIF1 barrier with a blocked worker callback, including explicit
opt-out, asynchronous-FINISH inheritance, per-instance configuration and the below-threshold bypass.

The tests require no ISO. They do not validate GPU rasterization, gameplay sound, frame pacing or FPS. New results
for this series are recorded separately in `docs/tested-hardware.md`.
