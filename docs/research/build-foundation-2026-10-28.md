# Build foundation, 2026-10-28

The foundation work precedes runtime patch 30. It removes redundant generation and toolchain orchestration while
retaining the engine's diagnostic and reference implementations. It does not attribute an FPS increase to pipeline changes.

## Compared with main

The local refs inspected are `origin/main` at `c144f40e` and `claude/keen-dirac-42wd1y` at `65c336f`, plus the
foundation working-tree changes described here. Both pin the same external runtime, `471c8318`; this is a different
patch stack and build pipeline, not a replacement engine.

| Area | Main at the inspected commit | Claude branch plus this foundation |
|---|---|---|
| Runtime patches | 01–16 | 01–29b; patch 30 is still pending |
| EE code generation | Register locals already supported by 08 | Lean JAL/JALR calls and dispatch trimming in 28/29, diagnostic correction in 29a |
| VU1 execution | Recorded native code and interpreter fallback | Background native compilation, x64 JIT, miss capture and JIT optimization (17–20, 27) |
| Native regeneration | VU1 rebuild isolation in 16 | Stable VU1 shards, analysis cache and stable IOP outputs (21–23) |
| Runtime usability | Earlier boot/audio/save behavior | Audio overflow correction, standalone boot profile and save/capture changes (24–26) |
| Build toolchain | Clang and MSVC orchestration | New builds use pinned Clang; compatible Qt, manifest-driven tools, local object cache and content-validated EE generation |

Main was not built or benchmarked on this laptop in this delivery. Its FPS/build-time delta is therefore unknown.
The lean/full experiment below switches one behavior in the current executable and cannot substitute for that
branch comparison. Historical results on the Xeon/RX 580 remain historical, with different hardware and settings.

## Architecture

`tools/pipeline/build.ps1` owns parameters, the checkout lock, stage order and error protocol. Modules separate
portable tools, context, compiler setup, game process helpers, runtime/disc setup, game generation/build, optimization,
regression verification and distribution. The launcher still consumes the original step/progress/status messages.
Each completed or failed invocation writes `data/<game>/logs/pipeline-*.json` with stage and total seconds.
The report identifies compiler/cache packages, configuration, runtime commit, patch hashes and any PGO profile hash.
`cache-game.json` / `cache-verify.json` contain cache statistics accumulated over the local daemon's lifetime;
they are not per-stage hit rates unless compared against an earlier snapshot.

`toolchains.json` pins portable tool versions/checksums and Qt source modules; both the launcher tool-readiness check
and pipeline read it. New game, installer and launcher builds use llvm-mingw. The legacy `-Toolchain msvc` argument
prints a migration status and selects Clang. The existing compiler marker changes only after a successful game build,
so a failed migration can still use the old installed game. Old build directories are not deleted.

Qt 6.8.3 is built from its verified qtbase/qtshadertools/qtdeclarative archives into a compiler-specific prefix.
Some Windows tar versions require an absent external `xz` executable for these archives. `Expand-QtSource` uses
the pinned Python's liblzma to stream each verified archive into a temporary plain tar, extracts it with Windows
tar, and removes the temporary file even on failure. This adds temporary disk usage during SDK bootstrap without
requiring another installed tool. A real `.tar.xz` fixture is covered by the PowerShell pipeline tests.
Its bootstrap syncqt source needs an explicit `<algorithm>` include with libc++ 23; the idempotent source adjustment
is recorded in `modules/qt.ps1`. The Widgets source `qwidgetwindow.cpp` is excluded from unity batches because its
export declaration conflicts with `qwidget.cpp` when Clang combines the two. Upstream declarations stay unchanged.
Qt's QML sequence proxy iterator also lacks operations required by libc++ 23 sorting. A local adapter sorts owned
`QVariant` values and writes them back through Qt's typed iterator, with no QtCore ABI change. This adds temporary
storage during QML sequence sorting, not in the engine. The bootstrap runs 24 real Qt sorting cases on contiguous
and linked containers before marking the SDK complete. The adapter and regression source hashes are part of that stamp.
Qt's supported unity-build option reduces first-build work. This is a one-time
developer dependency build, separate from player installation. Never reuse a prebuilt MSVC Qt with llvm-mingw.
Deployment uses windeployqt's automatic MinGW/Clang detection against this Release-only SDK: forcing `--release`
misclassified lld PE debug entries and omitted the Windows platform plugin. The compiler runtime DLLs are copied
explicitly, and launcher startup is checked with the compiler and Qt SDK removed from `PATH`.
The installer embeds its manifest through llvm-rc and statically links the compiler runtime; Windows UCRT/system
libraries remain normal platform dependencies.

## Incremental generation and synchronization

The first real installation exposed a Windows PowerShell 5.1 ordering bug: culture-dependent sorting placed `29a`
before `29-...`. The shared ordinal patch-order helper now validates/applies 01–29b in the correct dependency order.
The PowerShell regression suite checks this ordering explicitly.

`recompile.py` hashes ELF, function map, template, game profile, recompiler binary, helper implementation and PS2X
environment (including codegen mode and any function-filter contents). A cache hit additionally requires every
generated C++/header hash to match. Timestamps alone cannot hide changed inputs. `-ForceRecomp` bypasses this skip.
Generated game data stays under ignored `data/`.

The Xeon/RX 580 review reproduced transient Windows access-denied errors while replacing two different generated
files. Atomic file replacement now retries Windows errors 5/32/33 up to six attempts (1.55 seconds of total backoff).
Persistent failures still propagate and leave the previous target intact; other permission errors fail immediately.
The Python regression suite covers recovery and failure preservation, and the real 6,418-file synchronization passes.

Generation happens in a temporary sibling directory. Only successful, structurally complete output is published;
failure leaves the previous output intact. Identical generated files retain timestamps. Publication uses sibling
renames with rollback on a normal rename failure. An unexpected `.previous` directory after process/power loss
requires inspection and recovery; it is not silently discarded. This is not a claim of a crash-atomic filesystem
transaction across all possible Windows power-loss conditions.

Synchronization records destination ownership/hashes, copies only changed files and removes obsolete owned files.
Modified obsolete files cause a failure before removal. Unrelated files remain untouched. On first migration,
ownership can be inferred only from the previous generation still present; older orphan files whose provenance
cannot be proved remain for manual review. A source output manually changed after generation is rejected.

## Cache and PGO

Pinned sccache uses a local cache capped at 5 GB. Both C and C++ launchers are configured from the pipeline, covering
recompiler and runtime targets. `-CompilerCache none` clears launchers and disables the runtime's automatic cache
discovery. Instrumented PGO builds also disable the launchers. Profile-use flags contain the `.profdata` content
digest, invalidating Ninja commands when training data changes at the same path.
The pipeline supplies a local configuration file and a checkout-specific daemon port; it does not inherit the host's
remote-cache configuration. The configuration selection follows the
[pinned sccache configuration contract](https://github.com/mozilla/sccache/blob/v0.19.0/docs/Configuration.md).
The pinned sccache release also hashes the profile file itself, as specified by its
[Clang profile-use parser and tests](https://github.com/mozilla/sccache/blob/v0.19.0/src/compiler/clang.rs).

Cache coverage depends on compiler flags, PCH and profiling support; unsupported invocations still compile normally.
A warm cache is not a substitute for Ninja's no-op build. Do not compare a cold full build with a warm no-op and
report the ratio as a compiler or engine speedup.

`-Pdb` now emits Clang CodeView and a separate lld PDB per executable; the upstream `PS2X_RELEASE_PDB` option only
implemented MSVC flags. A small optimized fixture produced a valid EXE/PDB pair. The sampling profiler also builds
with the pinned Clang toolchain (`-ldbghelp -lwinmm`) without a Visual Studio developer prompt.

## Validation and remaining gates

On the i5-8265U laptop, the real PT-BR game builds successfully with Clang Release, without PGO or LTO:

| Measurement | Elapsed time | Scope |
|---|---:|---|
| First installation pipeline | 2,005.895 s | Fetch, disc preparation, configure, recomp, sync and build |
| First game build/link stage | 1,625.804 s | Before populating the game object cache |
| Clean runner target, populated cache | 31.344 s | Ninja removed 956 outputs; compile/link reused eligible objects |
| Stable unchanged recomp/sync/build | 9.369 s | Hash validation, no copies, no compilation |
| Real EE generation/publication | 134.703 s | 6,418 C++/header files |
| EE cache-hit validation | 2.090 s | Matching inputs and all output hashes |

The warm rebuild reduces elapsed build-stage time by 98.1% in this scenario. This is cache reuse on identical code,
not a 52x compiler improvement, a clean empty-cache comparison with MSVC, or an FPS result. The later `optimize`
stage recorded 109 VU1 images and eight IOP modules and compiled only their native code; its pipeline took 456.760 s,
including 120 s of recording. These prepared native objects were not present in the initial compile-time comparison.
The runner grew from 73,003,008 to 101,830,656 bytes after adding recorded native code (both Release, no PGO/LTO).
The complete frame-rate observations and rendering limitations are in [tested hardware](../tested-hardware.md).

- Behavioral pipeline tests cover content invalidation despite unchanged timestamps, mode/environment changes,
  forced generation, output corruption, failure preservation, incomplete output, incremental synchronization,
  modified stale files and path traversal. Run `python -I tools/test/pipeline_tests.py`.
- `tools/test/pipeline-tests.ps1` checks configure reuse, same-path PGO changes, quoted profile paths, cache opt-out
  and environment restoration/error propagation around recording processes. A real exit-7/stderr probe reproduces
  and guards against shadowing PowerShell's global `LASTEXITCODE` with a local variable; external command failures
  must stop the pipeline immediately. This was exposed by the Qt unity-build failure during integration.
- An isolated real compiler test (`tools/test/compiler-cache.ps1`) produced byte-identical objects with one miss
  and one hit: 5.302 s cold versus 0.402 s warm on this laptop, including daemon startup in the cold measurement.
  This tiny fixture is not a game-build speedup estimate. Cache stats reported zero failed/unsupported calls.
- The cache test also replaces real training data at the same `.profdata` path: two profile versions cause two
  misses, a repeated version hits, and the final cached result matches a direct compilation after normalizing the
  COFF timestamp. This verifies the pinned tool's profile hashing, in addition to the pipeline's Ninja invalidation.
- `recompile-smoke.py` uses the real `ps2_recomp` on a synthetic three-instruction MIPS ELF. Generation, skip,
  forced regeneration with preserved timestamps, no-op synchronization and switching to classic codegen pass.
- `build.cmd -Stages verify` builds the isolated guest-call and upstream codegen suites. Follow-up patches 29d–29f
  restore the stale memory suite and add it to this gate (80 passing cases); they also correct scratchpad chain
  completion and DMA submission counts. This does not certify all upstream test modules or patch 30 fast paths.
- The Clang installer is built and its synthetic packed payload independently decompressed and compared byte-for-byte.
  This fixture test does not exercise registration/uninstallation of a real player installation.
- Final `fetch,verify,launcher` validation passes. Qt 6.8.3 and the launcher build with the pinned Clang toolchain;
  all 24 Qt sequence-sort compatibility cases pass. The deployed GUI starts with only Windows system directories
  on `PATH`, recognizes the prepared PT-BR disc and reports the game ready without stderr output.
- The user supplied a compatible standalone PT-BR translation (ELF CRC `D95720D3`), which was identified and
  prepared successfully. Real EE generation produced 6,418 C++/header files in 134.703 s. Gameplay and build
  results are recorded in `tested-hardware.md` as they are validated; historical Xeon/RX 580 figures must not
  be attributed to this i5-8265U laptop or these changes.
- `standalone-smoke.ps1` starts the game without arguments and supplies diagnostics only through `gow-native.boot`.
  It reaches gameplay, observes guest-frame counts, verifies 2,000 VU1 runs without mismatches and exits 0, then
  restores the exact original boot-file bytes. This integration check corroborates the late-initialization regression
  covered by 29a's unit tests; its timings are not a benchmark.

The [roadmap](roadmap-2026-10-27.md) defines the required cold/warm build matrix and memory/gameplay gates.
`tools/test/perf-compare.ps1` alternates lean/full call dispatch in the same executable, using fresh private cards,
fixed internal scale, frames-only diagnostics and raw five-second guest-frame samples after warm-up. This isolates
call-dispatch behavior; it is not a substitute for building and measuring `main`, nor a per-frame p99 measurement.
Keep the engine capped at its intended simulation rate; prioritize reduced frame-time spikes and sustained 60 guest
frames/s. No “1000%” improvement is demonstrated by organization, compiler selection or these regression tests.
