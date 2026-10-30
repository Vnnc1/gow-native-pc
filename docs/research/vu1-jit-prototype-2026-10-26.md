# VU1 code for every area: disc extraction + background compiler (prototype, 2026-10-26)

> Update (same day): the full JIT of step 3 is done: **engine/patches/18, docs/research/vu1-x64-jit.md**. The launcher's
> "Compile new areas while playing" now uses it (`GOW_VU1N_X64`); the background clang compiler below stays available
> by hand. The disc extraction's first real run found no usable MPG packets with the loose check (EE COP2 words were
> taken for microcode); the strict check (commit 4444f0f) has not been run on the disc yet.

Problem: areas the first-play recording did not visit (after the ship onwards) run their VU1 microcode in the exact
engine and drop to ~26 fps on machine A (Xeon E5-2666 v3 + RX 580). A session that went further recorded ~37,500 micro
memories against 783 from the 4-minute recording, and "Speed up visited areas" gets slower every session.

The plan agreed with the owner is a hybrid, with a path to a full JIT:

1. **From the disc, at install time:** read the microcode of every level from the ISO and compile it into the game, so
   no area starts slow and the recording is no longer needed.
2. **Background compiler as the safety net:** blocks the disc scan cannot see (microcode built at run time, entries
   through a register) are compiled while the game runs and switch to native code a few seconds later.
3. **Full JIT later**, if 1 and 2 are not enough. Only the background compiler's backend changes (clang → a direct x86
   emitter); the hooks, the registry and the tests stay.

Both prototypes are in this repository. They are off by default and marked experimental in the launcher.

## 1. Disc extraction: `tools/disc/vu1_from_disc.py` (pipeline stage `vu1disc`)

- **How it finds the code.** The game uploads VU1 microcode with VIF `MPG` commands (code 0x4A: NUM 64-bit
  instructions to address IMMEDIATE*8). These sit in its files as prebuilt VIF packets. The tool scans the boot ELF and
  every TOC file (read in place from PART1/PART2.PAK) for MPG headers. It accepts one when:
  - its data is 64-bit aligned;
  - it fits the 16 KB micro memory;
  - it decodes as VU code (no more than 5 % odd pairs, using the generator's own decoders).
- **Building the images.** Uploads that follow each other in the VIF stream (only NOPs between them) form one program
  load, applied to a 16 KB image. After each load that holds an E bit, a snapshot is kept.
- **Reduction.** Snapshots are deduplicated by content, then cut down to the ones that add **new blocks**. A block's key
  is the runtime's own: entry pc + words (`vu1n_gen.py fnv_block`). This turns the ~190,000 copies seen in an earlier
  test into the few that matter.
- **Output.** `data/<game>/vu1_capture/disc_<hash>.bin`, the same format as the recording. The `native` stage then
  generates and compiles them. Since patch 16, that rebuild compiles only the VU1 code.
- **Safety.** A block taken from a snapshot whose neighbouring code differs from what the game really has resident
  costs only compile time. The runtime looks blocks up by their exact words, so such a block never runs. Clean-operand
  entry assumptions are still checked at run time where the path does not prove them (`runNative` lane check).
- **Tested** (`vu1_from_disc_test.py`, no game data): a fake extracted disc whose TOC file holds random bytes, plus 200
  fake MPG headers, around VIF packets that upload a micro memory in chunks of up to 256 instructions.
  - Runtime JIT test micro memory: 4 of 4 blocks, 0 missing, 0 extra.
  - FMAC test micro memory: 252 of 252 blocks, 0 missing, 0 extra.
- **Not tested yet:** the real disc. Still unknown: how many blocks God of War's files give, how long the scan and the
  build take, and whether some levels keep microcode compressed or build it at run time. Run it once with
  `build.cmd -Stages vu1disc` and look at the `[vu1-disc]` line (files, uploads, distinct images, blocks).

## 2. Background compiler: `engine/patches/17` (`GOW_VU1N_JIT`)

- **Runtime** (`ps2_vu1_jit.inl`):
  1. When a dispatch slot is set up without native code (`slotFor`), the 16 KB micro memory is queued, once per code
     generation.
  2. A worker thread, below normal priority, waits 400 ms for more images and writes them out.
  3. It runs `vu1n_gen.py --dll jit_<n> --skip-keys`: the build's generator, with the blocks the game already has left
     out.
  4. It compiles the module with the build's clang and flags (`-shared -static` on Windows), with no console window
     (`CREATE_NO_WINDOW`).
  5. It loads the module (`LoadLibrary` / `dlopen`). On the next `runNative` entry, the VU1 thread registers the new
     blocks and sets the dispatch slots up again.
- **Module ABI.** The generated blocks call a few `VU1NativeAccess` functions that are not inline in the header:
  `chain`, `callLower`, `callUpper`, `xgkick`. A module reaches them through `VU1JitApi`, a function table the runtime
  passes, so the module does not link against the game. `kVu1JitAbi` (a version plus the sizes of `VU1State`,
  `VU1NativeCtx`, `Slot` and the table) makes a stale module register nothing.
  - Clang builds only: an MSVC game has another C++ library layout than llvm-mingw modules.
  - The launcher reads `data/<game>/vu1_jit.json` (written by clang builds: compiler, Python, generator, flags) and sets
    `GOW_VU1N_JIT*` when "Compile new areas while playing" is on (Performance tab).
- **Persistence.** Modules stay in `data/<game>/vu1_jit/<stamp>/jit_<n>.dll` and load at the next start. `<stamp>` is
  a hash of the generator, the ABI and the compiler command. `jit.log` holds the generator and compiler output.
- **Tested on Linux** (clang 18, `tests/vu1_jit_test.cpp`, procedural micro memory, no game data). The test programs
  are a transform loop (LQI, MULA/MADDA/MADD broadcast, CLIP, DIV + WAITQ, MULq, FCGET, FMAND, SQI, IADDI, IBNE) and an
  FMAC/flag mix.

  | | exact engine | background-compiled | compiled into the build |
  |---|---|---|---|
  | transform loop, 8 vertices | 17.4 µs | **0.89 µs** | 0.82 µs |
  | 4000 random cases | — | digest `7c9d4a139489ff09` | digest `7c9d4a139489ff09` |

  - First compile: 1 micro memory, 4 blocks, ~1.5 s. On the next start the module from the earlier run is loaded
    (0.1 s).
  - **Equal digests:** the background-compiled blocks give bit-for-bit the results of the same blocks compiled into the
    executable, which is what the game uses today.
  - Both differ from the exact engine in the same 284 of 4000 cases. All of these have Inf/NaN/denormal inputs going
    through DIV (zero sign, last bits): the native backend's known behaviour, which `GOW_VU1N_VERIFY` also tolerates
    for floats.
  - The `status` register's sticky bits are not modelled by native blocks, as before.
- **Not tested yet:** Windows (llvm-mingw `-shared -static`, `LoadLibraryW`, `CREATE_NO_WINDOW`) and the real game.
  What to watch:
  - `[vu1n-jit]` lines (stderr, or `jit.log`);
  - the frame rate after the first seconds in a new area;
  - `GOW_VU1N_VERIFY=2000` with the compiler on;
  - whether one compile at a time (one clang process, below normal priority) keeps the game smooth on 4-core CPUs.

## 3. Next steps

1. **On machine A:** `build.cmd -Stages vu1disc,native`. Note the `[vu1-disc]` line, the build time and the frame rate
   after the ship (`GOW_VU1N_DIAG=1`: `missBlocks` should be near 0).
2. **With "Compile new areas while playing" on:** play past the ship. Note `[vu1n-jit]` batch times and how long an
   area stays slow.
3. **If the disc scan finds too little:** look at how the level WADs store packets (compression, packets built by the
   EE). Then decide whether the full JIT is worth it.
4. **Full JIT (if needed):** replace step 4 of the worker (clang) with an x86 emitter that takes the generator's block
   description (`gen_block`'s semantics). Keep `VU1JitApi`, the registry hook, the persistence and `vu1_jit_test` with
   its AOT digest as the acceptance test.
