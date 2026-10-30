# JIT and incremental-build delivery (2026-10-26)

Base: `prototipo-claude` at `30b007f`. After fetching origin and tags, `git merge-base --is-ancestor v2.0.0 HEAD`
succeeded and `git log HEAD..v2.0.0` was empty. All v2.0.0 commits are already included; no synthetic merge was made.
The existing local hardware-test notes were preserved. No commit, push or release publication was performed.

## Implemented

- Patch 19: `GOW_VU1_CAPTURE_MISSES=1` records context only when an actually dispatched native block is absent,
  before the JIT registers it. Each `block_<key>.bin` is still a full 16 KB image, **not a new block-only file format**. (Patch 26: one `miss_<image hash>.bin` per distinct image instead, same format.)
  Explicit entry heads are recorded even when JIT succeeds. Completed files are published atomically; unchanged
  block keys are not written again. Legacy continuous capture remains available without this variable.
- Patch 19 also adds test-only `GOW_VU1X_ONLY=1`: with the JIT enabled, discard the initial AOT registry before slot
  setup. Unsupported programs still use the exact engine. This makes real-game JIT coverage observable.
- Patch 20: preallocate statement and emitted-byte buffers. Arithmetic and generated instruction order are unchanged.
  This removes repeated allocations; it is not a claim of a measured game FPS improvement.
- Patch 21: partition native blocks by `key % parts` instead of their position in a sorted list. Adding a block no
  longer moves all later functions to different C++ translation units. Changed clean-entry assumptions can still
  legitimately alter existing blocks. The legacy exact-program generator is not sharded by this patch.
- Patch 22: cache the pure control-flow/clean-operand analysis, keyed by image SHA-256, generator contents and entry
  heads. Checksummed compressed JSON, atomic replacement, stored only in the build output directory. `--no-cache`
  provides an independent cold reference. DLL generation does not use this cache. Never distribute these game data.
- Patch 23: the IOP generator retains byte-identical output files and their timestamps. Native maintenance no longer
  recompiles unchanged IOP modules just because the generator ran.
- Disc scanner: recognize MPG with the IRQ bit, stop the entire scan at `--max-images`, preserve unchanged output
  timestamps, and publish `disc-report.json` with counts and timing. Cache hits check source metadata, profile,
  implementation and SHA-256 of every output. `--force` handles external modifications that preserve source metadata.
  Incomplete runs are not reusable cache entries. Old scanner images are pruned only after a completed scan;
  recorded images are preserved.
- Pipeline: recognize patch prefixes when later patches introduce files that do not exist yet; no deletion advice
  on local divergence. First-play recording uses JIT/miss capture and asks the hidden game to close before forced exit.
  Routine configure/native runs skip remote updates of already downloaded CMake dependencies. Initial downloads
  remain allowed; include `fetch,configure` when dependency revisions change to permit fetching new commits.
- Launcher: compiler selection; optional disc scan before compilation; measured disc-report counts; JIT enabled for
  new settings (existing choices retained); inline/helper switch; optional AOT maintenance after a normal game exit
  when new captures exist. Automatic maintenance is off by default and uses the existing cancellable progress screen.
  Failed PowerShell startup clears the busy state. Play is blocked while the pipeline is running.
  Runner detection checks the CMake source folder before accepting an executable; a new installation cannot claim
  that another repository copy's default build is its own game.

## Evidence and boundaries

Machine A: Xeon E5-2666 v3, RX 580 2048SP, Windows, llvm-mingw clang 23.1.4, Release, existing PGO, LTCG off.

- Real prepared USA disc: 956 files, 6 usable images, 470 distinct blocks with strict instruction validation.
  This is not complete disc coverage. The earlier screenshot's suggestion that all stages are already extractable
  is not established. Compressed/relocated/runtime-built programs and indirect entries still need JIT or capture.
- Procedural scanner test: exact block coverage, MPG IRQ parity, cache reuse, corrupt-output repair, unchanged
  timestamps and limited-scan invalidation all passed.
- Procedural generator test: cold/cached C++ byte equality; stable shard placement; unchanged timestamps; invalidation
  after corrupted cache, changed heads, changed implementation and changed microcode all passed.
- IOP regeneration preserved the bytes and timestamps of all 9 existing generated files.
- First JIT-only real-game run: 100 s, hidden 1280x720 hardware rendering, audio off, scripted Start/X input;
  gameplay reached, 619 JIT blocks, 0 unsupported, 517 KiB emitted code, 19.5 us average compilation, 619 captures;
  2,000 comparisons against the exact engine reported 0 mismatches. The captured ship scene was visually inspected.
  This run had no guest-frame probe; its ~60 Hz host presentation rate must not be reported as game FPS.
  Evidence: `data/gow1/logs/jit-smoke-20261026-171435/` (local only).
- Final scanner: 112.088 s cold versus 0.420 s warm with unchanged sources. Native generator: 143.103 s cold
  (Ninja command duration), 15.154 s warm wall time, 9,480/9,480 analysis hits, all six C++ contents and timestamps
  unchanged. This measures these stages, not a full clean build speedup. One of 1,898 blocks remains unsupported
  by the AOT generator and retains the exact fallback.
- Final x64/AOT targets: 4,000 procedural cases each, matching digest `7c9d4a139489ff09`. Both retain the same
  284 known edge-input differences from the exact engine; equality here establishes no regression against AOT,
  not universal exact-engine equivalence. Fuzz seeds 1-6 (4 images x 6 trials), inline versus helper, all matched.
- Final 100 s runs, guest-frame probe enabled, 2x dynamic resolution, 120 Hz host presentation, profile combat input:
  both reached gameplay, checked 2,000 executions with zero mismatches and exited 0 after WM_CLOSE without a kill.
  JIT-only compiled 619 blocks, zero unsupported, 517 KiB, average compilation 16.4 us. At t=40-95 s its 12 frame-rate
  samples ranged 15.40-33.35 FPS (median 28.40). Hybrid used existing AOT (zero JIT compilations), 32.95-59.58 FPS
  (median 56.55). These short scripted runs follow different simulation progress at different speeds; they are not
  a controlled same-frame performance comparison. JIT is a coverage fallback, not a replacement for AOT speed.
  (Patch 27, later: the JIT's block code now executes about as many instructions as the AOT code on the synthetic
  bench, see vu1-x64-jit.md §5.2; the real-game comparison has to be repeated.)
  Evidence: `data/gow1/logs/jit-jit-20261026-172927/` and `jit-hybrid-20261026-173110/`.
  An earlier run at `jit-jit-20261026-172736/` was rejected because the test harness set the presence-based
  `GOW_VU1_NATIVE_OFF` to the string `0`, disabling native execution. The harness now removes it and the path-based
  background-compiler variable, and requires native verification, expected JIT activity and a clean exit.
- Incremental `fetch,native` recognized all 23 patches and Ninja reported `no work to do`: no EE, VU1 or IOP
  recompilation with unchanged inputs. Launcher built successfully with MSVC/Qt 6.8.3. Installation and performance
  tabs were captured and visually inspected at 1280x1000; both processes exited 0 with empty stderr. Compiler,
  experimental disc scan, JIT inline and optional post-game optimization controls fit the existing layout.
  Full installer registration/uninstall and post-game automatic-maintenance interaction are not end-to-end tested.
  A packaged-launcher smoke test exposed a foreign `C:/gow-build-clang` being accepted as an installed game.
  After the CMake source-root check, the empty package correctly shows Install and the development copy still shows
  Installed; both exited 0 with empty stderr. Screenshots: `launcher-packaged-root-fixed.png` and
  `launcher-existing-root-fixed.png` in the local logs directory.

Reproduce synthetic checks:

```powershell
python -I tools/disc/vu1_from_disc_test.py --gen engine/runtime/tools/vu1/vu1n_gen.py <procedural.bin>
python -I tools/disc/vu1_analysis_cache_test.py --gen engine/runtime/tools/vu1/vu1n_gen.py <procedural.bin>
```

For the procedural input use `gow_vu1_jit_test --write <procedural.bin>`, never a published game capture.
Build/run the x64/AOT/fuzz targets as documented in [vu1-x64-jit.md](vu1-x64-jit.md).
Use `tools/test/jit-smoke.ps1 -Mode hybrid`, `-Mode jit`, or `-Mode calls` for real-game comparisons. It reads the
pad script and guest-frame probe from the game profile, writes a JSON summary and isolates validation captures.
For the packaged installer, `tools/test/verify_setup.py <setup.exe> <staging-dir>` decompresses and compares every
file without changing Apps registration, shortcuts, saves or an existing installation.

## Next patches, in order

1. **Coverage by area.** Build a local report relating missed block keys, entry PCs and level transitions to disc
   uploads. Inspect WAD container/compression boundaries before expanding heuristic scanning. Acceptance: no false
   instruction packets in synthetic tests, measured coverage on post-ship/desert/temple runs, bounded scan memory.
2. **Smaller capture representation.** Store block words and entry PC in a versioned, checksummed format, then feed
   the generator with conservative entry-lane assumptions. The current full-context images preserve compatibility;
   dropping them requires testing the legacy exact backend and every indirect target. Compare digests before rollout.
3. **JIT hot loops.** (Largely done by patch 27: vu1-x64-jit.md §5.2, §7 for what is left.) Profile actual VU1 time; investigate retaining VF/ACC in SSE registers across proven self-loops,
   then static timing for known entry states. Keep exact fallback and differential fuzz/AOT/replay verification.
   The existing chaining experiment gave only ~1-2%; do not assume that removing dispatch buys a large gain.
4. **Shader warmup by observed variants.** Record encountered GS shader keys and compile/link timing per level;
   replay those variants during an optional preparation step using the same renderer/settings. Version caches by
   shader source, GPU and driver; invalidate after driver/source changes. Do not distribute opaque cross-GPU binaries
   or claim that boot warmup prepares unseen levels. Current first-play preparation already fills the normal cache.
5. **Renderer and scheduling.** Measure guest frame rate, host presentation, VU1 and GS time separately. Investigate
   the documented EE/VU1 serial gap and texture/CLUT tint issue with deterministic captures. Early FINISH and GS
   display-write reordering require opt-in tests of readbacks/interrupts and both AMD and NVIDIA; do not enable the
   Waffle batching changes that previously saturated AMD. Shader compilation and frame rendering are separate costs.
6. **Skip redundant CMake configuration.** (Done: build.ps1 `Configure -MaySkip`, AGENTS.md "Configure skip".) The final no-change native run still spent 62.5 s configuring and 30.5 s
   generating, even with remote dependency updates disabled; Ninja then had no work. Add a configuration signature
   covering source/options/profile/head changes before safely skipping this work. Measure with no concurrent build.

The skill search requested during this work found Qt's `qt-qml` guidance and community `cpp-pro`. QML guidance was
read from TheQtCompanyRnD/agent-skills; this repository's translation table and component conventions take precedence.
No third-party skill installation or project dependency was added.
