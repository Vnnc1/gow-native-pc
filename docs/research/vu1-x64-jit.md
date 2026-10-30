# VU1 x86-64 JIT (engine/patches/18, 27) — design, contracts, tests, how to change it

Windows real-game validation and follow-up patches 19-23 are recorded in
[jit-delivery-2026-10-26.md](jit-delivery-2026-10-26.md). Patch 27 (§3.3-3.5, §5.2, §8) made the JIT about as fast as
the build's generated code: inline forms for almost every statement, a per-block `nrm` cache, AVX encodings, entry-lane
speculation and JIT-to-JIT chaining past the prologue, plus three native-backend bugs it exposed.

This is the reference for anyone, a person or an AI, who changes, extends or debugs the in-process VU1 JIT. It assumes
`AGENTS.md` (project layout and rules) and, for background, `docs/research/vu1-jit-prototype-2026-10-26.md` (why the
JIT exists, the disc extraction and the clang background compiler).

## 1. What it does

The game uploads VU1 microcode at run time. The build compiles the microcode it knows ahead of time (`vu1n_gen.py` → C++
→ the game executable): the first-play recording, "Speed up visited areas", the disc extraction. Code the build did not
see runs in the **exact engine** (a cycle-accurate interpreter), about 10-20x slower. That is the ~26 fps after the ship.

With `GOW_VU1N_X64=1`, a block without native code is translated **at its first dispatch-slot setup** into x86-64
machine code. This takes ~10-65 µs per block, needs no compiler or files, and works on any toolchain build (MSVC or
clang). The block is registered in the same registry as the build's blocks, so it runs through the same dispatcher
(`runNative`), with the same flag, timing and chaining machinery.

Launcher: Performance tab → "Compile new areas while playing (experimental)" sets `GOW_VU1N_X64=1`
(`launcher/src/lanzador.cpp`).

## 2. Where the code is

All in the runtime, patches `engine/patches/18-vu1-x64-jit.patch` and `27-vu1-jit-speed.patch`:

| File (engine/runtime/…) | Role |
|---|---|
| `PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_x64.inl` | the JIT: decode, translator, helpers, inline tier, emitter, code arena, compile + register |
| `PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_native.inl` | includes it; `slotFor` calls `vu1x::compile` on a miss; `[vu1x]` line in `GOW_VU1N_DIAG` |
| `PS2Recomp/ps2xRuntime/include/runtime/ps2_vu1_native.h` | `VU1NativeAccess::chainFn` (the block-to-block tail jump), `NativeState::jitHash` |
| `PS2Recomp/ps2xRuntime/src/lib/vu/ps2_vu1_jit.inl` | patch 17's clang background compiler; patch 18 passes missed entries as `--heads` |
| `tests/vu1_jit_test.cpp` | procedural micro memory; mode `x64` must print the compiled-in digest |
| `tests/vu1_x64_fuzz_test.cpp` | random VU programs; JIT vs JIT-without-inline vs clang-built generator code vs exact engine; `GOW_FUZZ_SPECIAL=1` Inf/NaN registers |
| `tests/vu1_bench.cpp` (patch 27) | speed: renderer-like programs (transform, light, skin, cull) run exact / hybrid (AOT) / JIT-only, equal digests |
| `tools/ci/pruebas_vu1.cmake` | CMake targets of those tests (include it in a runtime build to get them) |
| `tools/test/vu1-equiv.sh`, `tools/test/vu1-ir-measure.sh` (gow-native-pc) | the equivalence campaign and the instruction-count measurement of §6 |

The translator mirrors `tools/vu1/vu1n_gen.py` (runtime repo, patched by 10, 13, 17). **Rule: a change to the
semantics in `vu1n_gen.py` (`gen_block`, `emit_upper`, `emit_lower`, `lower_info`, `classify`, flag model) must be
ported to `vu1x::translate` and its helpers in the same change.** The fuzz test catches a missed port, as long as its
generator covers the instruction (§6).

## 3. Architecture

### 3.1 Translation (`vu1x::translate`, port of `gen_block`)

Input: the block's words as `slotFor` reads them (`nativeExtent`: up to 64 pairs, ending at a branch + delay slot, an E
pair + its delay pair, or a D/T pair). Output: a `Block`, made of a list of `Stmt` (helper function + `Imm` operands +
optional inline kind) plus end-of-block data. The block summary holds:
- `ebit` and `endPc`;
- `readsEntry` (bit 16 of the registered pair count: the block reads flags written before it, so `runNative` gives it
  exact entry timing);
- `VU1TailDesc`;
- `VU1NativeLanes`.

It follows `gen_block` step by step:
1. **Structural checks.** These are the same `None` cases as the generator: a branch anywhere but the second-to-last
   pair, a branch in a delay slot, a branch with E/D/T, CLIP and FCSET in one pair, and the h1 + (h2 | h3) read/write
   hazard between the lower and upper op. Unsupported blocks stay in the exact engine and are remembered
   (`State::failed`).
2. **Flag writers.** MAC writers are ADD/SUB/MADD/MSUB/MUL with DEST ≠ 0 (`macW`). Clip writers are CLIP or FCSET
   (`clipW`).
3. **Per pair:**
   - the VI backup (`hBackup`) for a branch in the next pair;
   - the branch decision (`hBranch`, conditional reads go through the backup);
   - the upper op, then the lower op. When the upper writes what the lower reads, the lower runs first; with the I bit,
     the upper runs and then `s.i = qnorm(imm)`;
   - the D/T exit (`hHalt`), with flush lists ported from `flush()`.
4. **Block end** (`flush_final`): tail stores (`hTailQ` / `hTailC`), the newest MAC writer pushed with
   `pushMacRaw(…, tail)`, the newest clip writer with `pushClipTail(…, tail)`. Then either `return kVu1nEnded | end`
   (E bit) or `hNext` (taken ? target : end) followed by the chain.
5. **Flag reads** (FCEQ/FCAND/FCOR/FCGET/FMEQ/FMAND/FMOR) take a `FlagSrc`: the writers 1-3 pairs before (visible when
   `n.cyc[i] - n.cyc[j] >= 4`, newest first), then the newest writer 4+ pairs before, then the entry value
   (`macAt` / `clipAt`). This is `visible()` in the generator, unrolled.
6. **Clean operands.** For each operand, `ld` (raw) is used when the lanes are known clean, otherwise `ldn` (Inf/NaN →
   ±FLT_MAX). Inside the block this is the generator's rule. On entry the JIT assumes the lanes clean in the state the
   block is first run with (§3.4); the lanes relied on become `laneReq`, checked by the dispatcher.

### 3.2 Statements and helpers

Each `Stmt` corresponds to exactly one line `vu1n_gen.py` would write. Its helper (`hFmac`, `hLQ`, `hSpecial`,
`hFlagOp`, …) runs that line with the same `vu1n::` functions from `ps2_vu1_native.h` that the generated C++ uses.
Runtime DEST masks go through dispatch tables of the template instantiations (`stfRt`, `itofDispatch`, …), so the code
is the same as in the build, by construction.

Temporaries live in the block's `Frame` on the stack: `q[64]` unclamped FMAC results, `nv[32]` cached `nrm()` values
(inline tier), `m[64]` MAC values, `c[64]` clip values, `vib[64]` VI backups, `taken` / `target` (helper path only).

### 3.3 Inline tier (`emitInline`, default on, `GOW_VU1X_INLINE=0` turns it off)

Since patch 27 almost every statement has an inline form; the helper stays the reference (`x64-calls` mode).

| Statement | Inline form (`ps2_vu1_x64.inl`) |
|---|---|
| FMAC ADD/SUB/MUL/MAX/MINI/MADD/MSUB, all sources | `emitFmac`: `nrm` per operand (or the frame cache), MADD/MSUB overflow test → cold stub calling `hFmac` |
| MAC value `m{i}` | `emitMacVal` (16-byte `kRev4` table in `kConst`), only when a flag op reads it (`Imm::macM`) |
| ITOF / FTOI / ABS | `emitConvert` (FTOI: clamp, scale, `cvttps2dq`, saturation blend) |
| CLIP | `emitClip` (two `cmpps`, `unpck*ps` + `movmskps` → the 6 bits, chain from the previous `c{j}` or `m_workingClip`) |
| FCEQ/FCSET/FCAND/FCOR/FMEQ/FMAND/FMOR/FCGET | `emitFlag`: near writers tested on `n.cyc` inline; **helper** when the source can be an earlier block's flag (`farJ < 0`) |
| DIV / SQRT / RSQRT | `emitQOp` (`qnorm` in SSE, zero-denominator branch) |
| MOVE, MR32, MFIR, MFP, MTIR, XTOP/XITOP, LQ/SQ/LQI/SQI/LQD/SQD, ILW/ISW/ILWR/ISWR, IADD…IOR, I-bit store | `emitInline` / `emitSpecial` |
| branches + next pc | `emitBranch`: next pc straight into r13d (`cmov`), no frame round trip |
| D/T halt | `cmp` of `dBitEnabled` / `tBitEnabled` inline, `hHalt` only when enabled |
| flag pushes at the block end, tail records | `emitRingPush` (`pushMacRaw` / `pushClipTail` written out), `IN_TAILQ` / `IN_TAILC` |
| exact-engine call-outs (`callUpper` / `callLower`), XGKICK | helper |

The rules that keep it exact:
- **MADD / MSUB:** compute `p = a*b` and `r = acc ± p`. If any lane of `max(|p|, |r|)` is above `0x7F7FFFFE`, a cold stub
  after the block's return calls `hFmac`, which redoes the whole statement from the unchanged state (wide evaluation),
  and jumps back. The test looks at **all four lanes** (DEST or not), like `vu1n::madd`.
- **`nrm` cache (`loadNorm`):** a register normalised by one statement is stored in `frame.nv[r]` when a later statement
  reads it normalised before anything writes it; later reads load it. A statement that is a helper call empties the
  cache (it may write any register).
- **`q{i}`** is stored only when something reads it later (`Imm::qNeed`: flag ops, the end-of-block push, a D/T flush,
  the tail record).
- **AVX** (`avxEnabled`, `GOW_VU1X_AVX=0` off): the same instructions in VEX form, three-operand where that drops copies
  (`nrm`, `qnorm`, MADD test, MAC value, CLIP, FTOI, masked stores, `vbroadcastss` for Q/I). Same IEEE operations under
  the same MXCSR, so the same bits.

### 3.4 Speculation on entry lanes (`GOW_VU1X_SPECULATE=0` off)

`vu1n_gen.py` decides per operand between `ld` and `ldn` (normalise Inf/NaN to ±FLT_MAX) from the lanes known clean.
The build's code assumes lanes clean on entry from a static analysis of the image. The JIT compiles a block when it is
about to run it, so it takes the lanes clean **in the state it is run with** (`cleanLanes(vu.m_state)`) as the entry
assumption. The lanes the code then relies on become `VU1NativeLanes::req`.

- The runtime checks `req` against `known` (lanes proved clean along the blocks run since native entry) on every entry,
  in `runNative` and now also in `chain()` (`vu1n::lanesClean`), instead of returning to the dispatcher.
- A failed check calls `vu1x::despeculate(fn)`: the block is compiled again for vf00-only entry (`req = 0`) under the same
  key, the slot is set up again, and the run continues natively. Counted in the fuzz output ("recompiled after a failed
  entry lane check").
- **Equal results are required, not just likely.** A speculative `ld` is used only where `ldn` would give the same bits:
  the lanes read raw must be clean, and for MADD/MSUB vector operands **all four lanes** (the overflow test reads every
  lane). Choices that do not depend on the entry assumption are exactly the generator's. Test: `GOW_FUZZ_SPECIAL=1`
  (Inf/NaN registers) must give the same digest with speculation on and off.
- `known` comes from each block's `gen` / `keep` summary. It must never claim a lane clean that is not: see §8 for the
  two analysis bugs this exposed.

### 3.5 Emitter, ABI, memory

- **Prologue.** Pushes rbx, rbp, r12, r13, r14, r15 and reserves 32 bytes of shadow space plus the `Frame` (+8 for
  alignment). Registers: rbx = `VU1NativeCtx *`, rbp = `kConst`, r12 = frame, r13 = next pc, r14 = `VU1State *`, r15 =
  VU data. The prologue is identical in every block (`emitPrologue`, `prologueSize`).
- **Helper calls.** `helper(n, frame, imm)`, with arguments in rdi/rsi/rdx (System V) or rcx/rdx/r8 (Windows x64).
  Only xmm0-xmm5 are used, so the callee-saved xmm6-15 on Windows are never touched.
- **Halt exit.** A statement with `exitIfNonZero` (D/T halt) returns its value from the block when it is non-zero.
- **End.** `VU1NativeAccess::chainFn(n, next)` (chain()'s bookkeeping, the entry lane check, the next block's function).
  Null: return `next | kVu1nDone`. JIT code (inside the arena's reserved range): jump to it **past its prologue**, same
  frame and registers. Anything else (AOT code, a background module): epilogue, then a tail jump with `n` in the first
  argument register.
- **Code memory (`CodeArena`).** One 1 GB range reserved at start (`VirtualAlloc MEM_RESERVE` / `mmap PROT_NONE`),
  committed read-write-execute 1 MB at a time, never freed; `FlushInstructionCache` on Windows. If the range cannot be
  reserved or is full, separate chunks outside it (those blocks are entered through their prologue).
- **Registration.** `vu1nRegisterBlock` on an existing key (a despeculated block, a background module after the JIT)
  updates the entry in place and keeps its timing table `cyc`: slots, the running block's context and the timing
  history point into it.
- **Threading.** Compilation runs on the VU1 thread, under a mutex. The registry is only touched by the VU1 thread (one
  VU1 thread in this runtime).

## 4. Environment variables

| Variable | Effect |
|---|---|
| `GOW_VU1N_X64=1` | turns the JIT on (the launcher's "Compile new areas while playing") |
| `GOW_VU1X_INLINE=0` | helpers only (A/B checks, bisecting a wrong image) |
| `GOW_VU1X_AVX=0` | legacy SSE4.1 encodings even on AVX CPUs (A/B checks) |
| `GOW_VU1X_SPECULATE=0` | no entry-lane speculation (blocks compiled for vf00-only entry, as before patch 27) |
| `GOW_VU1X_DUMP=<dir>` | writes every block's x86 code to `<dir>/<pc>_<key>[_s].bin` (`_s`: speculative); read with `objdump -D -b binary -mi386:x86-64` |
| `GOW_VU1X_ONLY=1` | test only: drop the build's blocks, the JIT runs everything |
| `GOW_VU1N_DIAG=1` | every 5 s: `[vu1n]` counters (`laneChecks`, `laneFails`) plus `[vu1x] compiled=… unsupported=… codeKB=… avgCompileUs=…` |
| `GOW_VU1N_VERIFY=<n>` | compares native runs (JIT blocks included) with the exact engine, as for the build's blocks |
| `GOW_VU1_NATIVE_OFF=1` | no native blocks at all (exact engine only) |

## 5. Results

### 5.1 Patch 18 (first version)

Transform loop (8 vertices): exact engine 17.3 µs, JIT 1.27 µs, build's code 0.82 µs. First real-game JIT-only run
(machine A, jit-delivery-2026-10-26.md): median 28 FPS against 56 FPS hybrid.

### 5.2 Patch 27 (2026-10-26, clang 18, Linux, Xeon @ 2.1 GHz, builds with -march=haswell unless noted)

Instructions executed by the native blocks of `vu1_bench` (100 reps, `tools/test/vu1-ir-measure.sh`; AOT = the same
programs compiled into the bench by `vu1n_gen.py`):

| Step | JIT blocks (code + helpers) | vs AOT (18.6 M) |
|---|---|---|
| patch 18 | 37.4 M (22.2 + 15.2) | 2.01× |
| every hot helper inline, `rbp` constants, branch/next in r13 | 25.4 M | 1.36× |
| `nrm` cache, dead `q` stores removed, `pmaxsd` + `ptest` MADD test | 23.0 M | 1.24× |
| entry-lane speculation | 21.5 M | 1.16× |
| AVX three-operand encoding | 19.5 M | 1.05× |
| JIT → JIT jump past the prologue | **18.5 M** | **0.99×** |

`VU1NativeAccess::chain` (shared by AOT and JIT) costs 10.0 M in both modes, about 130 instructions per chained block.

Wall time (noisy VM, best of 3): transform loop of `vu1_jit_test`, AOT 0.55 µs, JIT 0.65 µs (was 0.88 µs);
`vu1_bench` total per pass, -march=native build: AOT 16.3 µs, JIT 19.3 µs (was 23.2 µs; part of the difference is
the cold path of JIT compilation that the bench's first pass does not fully hide, and the bench's exact-engine call-outs).

Correctness:

| Check | Result |
|---|---|
| `vu1_jit_test x64 2000` / `vu1_jit_aot_test - 2000` | both `7c9d4a139489ff09` (unchanged) |
| `tools/test/vu1-equiv.sh`, seeds 1, 4, 7, 11, 23 | module = x64 = x64 SSE = x64-calls = x64 no-speculation |
| `GOW_FUZZ_SPECIAL=1`, seeds 3, 5, 9, 12, 31, 44, 57 | speculation on = off (with 170-200 recompiles per run) |
| module + x64 mixed (background module replacing JIT entries) | equal digests (seeds 1, 4) |
| `vu1_bench` hybrid vs jit | `17b71b300f7b9090` both |
| valgrind memcheck, special inputs | 0 errors |
| Windows x64 ABI (MinGW GCC under Wine): AVX, SSE, helpers, chaining on | seeds 1, 4 equal to Linux |

Fuzz digests changed with patch 27 (seed 1 `28d2d98366dd791a`, 4 `cf4b88fc04ab0488`, 7 `3062c248d18231e3`) because
`vu1n_gen.py` changed semantics for one rare case (§8). Seed 7 still differs between Linux-clang and Windows-GCC in
the **exact engine alone** (`fuzz exact`), a compiler difference in existing runtime code; the game's Windows builds use
clang.

**Not tested yet: the real game** with patch 27. On machine A: `tools/test/jit-smoke.ps1 -Mode jit` and `-Mode hybrid`,
compare the guest frame rate after the ship; `GOW_VU1N_DIAG=1` (`laneFails` should stay near 0); `GOW_VU1N_VERIFY=2000`.
If something looks wrong: `GOW_VU1X_SPECULATE=0`, then `GOW_VU1X_AVX=0`, then `GOW_VU1X_INLINE=0`; the first that fixes it
names the layer.

## 6. How to test after a change

Build the runtime with the tests (Linux shown; Windows the same with the project's toolchain):

```sh
# in a runtime checkout with engine/patches applied
cmake -S PS2Recomp -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
      -DCMAKE_CXX_FLAGS="-fno-strict-aliasing -fwrapv" -DPS2X_RELEASE_LTCG=OFF -DPS2X_BUILD_STUDIO=OFF \
      -DPS2X_BUILD_ANALYZER=OFF -DPS2X_BUILD_TEST=OFF -DPS2X_BUILD_RECOMP=OFF \
      -DCMAKE_PROJECT_PS2RetroX_INCLUDE=$PWD/tools/ci/pruebas_vu1.cmake
ninja -C build gow_vu1_jit_test gow_vu1_jit_aot_test gow_vu1_x64_fuzz_test gow_vu1_bench
build/gow_vu1_jit_aot_test - 2000      # reference digest (7c9d4a139489ff09 for the current test; it depends on the count)
build/gow_vu1_jit_test x64 2000        # must print the same digest
tools/test/vu1-equiv.sh build . 1 4 7  # (from gow-native-pc: <build> <engine/runtime>) every JIT mode = the generator's code
build/gow_vu1_bench hybrid 500; build/gow_vu1_bench jit 500   # equal digests; compare the per-pass times
```

- Equal `digest` lines = pass. When they differ, set `GOW_FUZZ_DUMP=<file>` on both runs and diff the files: they
  have one line per run (image, trial, pc, digest, native blocks).
  - A different **native block count** means the two sides cover different blocks: coverage, not semantics. Check the
    heads, and the unsupported shapes in `translate` vs `gen_block`.
  - A different **digest** with the same count is a semantic difference in some statement. Bisect with the A/B
    variables of §4, then `GOW_VU1X_DUMP` + `objdump` on the block of the first differing run.
  - **A digest that changes from run to run** (with ASLR; `setarch -R` makes it stable) is memory misuse: run the
    failing case under `valgrind --tool=memcheck` (it follows JIT code too). That is how the registry use-after-free
    of §8 was found.
- **Speed:** `tools/test/vu1-ir-measure.sh build/gow_vu1_bench` (build with `-march=haswell`: valgrind cannot run
  AVX-512; a compiler launcher that rewrites `-march=native` works, the runtime hard-codes it). Wall time in a shared VM
  varies ±30 %; use instruction counts to compare small changes and wall time only for large ones.
- **Real microcode:** `-DGOW_VU1_BENCH_DIR=<folder of 16 KB .bin>` (e.g. your own `data/gow1/vu1_capture`, game data:
  never commit) adds those images to the bench, compiled in as AOT and run from every program start.
- Keep test sizes small (4-6 images, ≤10 trials). The module oracle compiles each image in ~10 s with every entry as a
  head.
- **New instruction or form:** add it to `Gen::lower()` / `Gen::upper()` in the fuzz test, or the comparison never
  exercises it.

## 7. How to extend

- **Supporting a statement inline:**
  1. give the `Stmt` an `InlineKind` in `translate`;
  2. write the sequence in `emitInline` (SSE and, where it saves copies, the `e.avx` three-operand form), mirroring the
     helper exactly;
  3. add its VF reads/writes to the `Use` pre-pass in `emit` (the `nrm` cache depends on it; unknown kinds count as
     "writes everything");
  4. run `tools/test/vu1-equiv.sh` on several seeds.

  Legacy SSE memory operands need 16-byte alignment: use the `kConst` table for constants and `movups` for VU
  registers and VU memory. VEX forms have no alignment rule.
- **Faster code (ideas, in order of gain per effort):**
  1. `chain()` (shared with AOT, ~130 instructions per block, ~50 % of the blocks' own cost in the bench): a
     specialised path for a block that jumps to itself, or the per-block timing bookkeeping emitted by the JIT.
  2. Keep VF/ACC values in xmm registers between statements (store forwarding is on the critical path of
     MULA/MADDA chains); on Windows that needs xmm6-15 saved, cheap now that chained JIT blocks share one prologue.
  3. Keep VI registers in general registers inside a block (LQI/SQI streams load, add, sign-extend and store each time).
- **Other platforms:** the JIT is x86-64 only (`VU1X_SUPPORTED`). On other CPUs the include compiles to nothing and the
  background clang compiler (patch 17) or the build's blocks remain.

## 8. Known limits, risks, and bugs found

- **Bugs found and fixed by patch 27** (all latent before, exposed by speculation):
  - *Registry use-after-free:* registering an existing key replaced its entry and freed the timing table the running
    context still used. Now updated in place.
  - *Same VF register written by the upper and the lower op of one pair:* the exact engine keeps the upper result
    (`upperVfShadowReg` / `suppressedLowerVf` in `ps2_vu1_step.inl`); `vu1n_gen.py` wrote the lower one last. Now the
    lower VF write is dropped in the generator (`suppress_vf`) and the JIT, and the lane analysis treats such lanes as
    unknown (`apply_pair`). Exact-engine call-outs in the lower slot still write last (rare; the analysis covers it).
  - *MAXi / MINIi:* not clamped and reading I raw, so not clean when I holds Inf/NaN; the analysis assumed clean.
  - These change `vu1n_gen.py`, so the analysis cache (patch 22) is rebuilt once and the generated VU1 code is
    regenerated; only blocks with those rare pairs change.
- **No unwind tables.** The JIT code registers none with the OS, so an exception that unwinds through a JIT frame would
  terminate the game. The helpers and the VU call-outs do not throw in this runtime; keep it that way, or add
  `RtlAddFunctionTable` (Windows) / `__register_frame` (Linux).
- **Executable memory is RWX** and a 1 GB range is reserved (address space only). Some security software or Windows
  "Arbitrary Code Guard" policies refuse it: the allocation then fails and blocks stay in the exact engine (no crash).
- **Windows macros.** `windows.h` defines `near` and `far`, so do not use them as identifiers (`FlagSrc::farJ`).
- **Status register.** The `status` register's sticky bits are not modelled by native blocks, the same as the build's.
  `GOW_VU1N_VERIFY` and the tests leave it out.
- **Every vu1n_gen.py change must be ported** (§2). The fuzz oracle (`module`) uses the Python generator, so it shows
  any drift.
