# Isolated regional runtime overlays

These overlays reproduce the Europe/Japan runtime sources used in the Windows
ship-gameplay tests on 2026-11-02. They are **conditional**, not additions to the
USA ordinal patch chain. Never apply them to the installed `engine/runtime`.
The normal installer still rejects these foreign-code ELFs; use their separate
tested builds. See `docs/research/regional-port-2026-11-02.md` for local paths and
the remaining acceptance limits.

Run `python -I tools/test/regional-overlays.py` to check source baselines,
patch applicability, bounded maps, stub/entry addresses and frame probes.

Each region contains:

- `runtime.patch`: differences from the current patched USA runtime to the
  isolated regional source. Includes code/data relocation and disables the
  optional host target-lock assist whose camera allocation is unvalidated.
- `baseline.json`: SHA-256 of each original UTF-8 source with normalized LF
  newlines. Require an exact match before applying the overlay to a copy.
- `functions.csv`: bounded recompiler function ranges for the exact profile ELF.
- `entries.json`: relocated SDK stubs and additional entry-point declarations.
  These contain addresses and symbol names, not guest instructions or media.

Reproduction requires the runtime revision in `engine/runtime.toml` with the
current `engine/patches` chain applied, the exact ELF identity from
`games/gow1/game.toml`, and a separate runtime snapshot/build directory. Verify
`baseline.json`, then run `git apply --check <absolute-runtime.patch>` and
`git apply <absolute-runtime.patch>` from that snapshot. The overlay also changes
`src/gow_overrides.cpp`; copy it to the snapshot's runner directory after codegen.

Generate with `PS2X_CODEGEN=locals`, `single_file_output=false`,
`patch_syscalls=false`, `patch_cop0=true`, `patch_cache=true`, the regional
`functions.csv` as `ghidra_output`, and the two lists from `entries.json` as
`general.stubs` and `general.entry_points`. Use the actual regional ELF as
`general.input` and isolated output as `general.output`. Do not carry over the
USA instruction patches. Validate the compiler report with `validate_report`
in `tools/pipeline/recompile.py` before synchronizing generated files. Install
generated headers in both `ps2xRuntime/include` and `ps2xRuntime/src/runner`;
otherwise stale runner-local declarations shadow the regenerated headers.

Entry hints include aligned executable pointers in `.data`/`.rodata` and
LUI+ADDIU/DADDIU/ORI address constructions within each decoded function range.
The latter deliberately overapproximates possible saved-register values across
calls. Hints create additional dispatch entries; they do not rewrite guest
instructions or replace function boundaries. Counts: Europe 4093, Japan 4020.

Prepare each disc separately with `iso_extract.py --layout`, then call
`prepare.normalise(folder, profile)` so `IOP_MOD` aliases exist. Compile using
the pinned llvm-mingw, `-O3`, x86-64-v2, without USA PGO or generated VU1 output.
Enable the in-process VU1 JIT. Use independent cards and save directories.

The overlays were applied to temporary baseline copies and compared byte for
byte (normalized newlines) with every changed source in both tested builds.
Do not reuse them after changing the baseline without repeating that check,
recompilation, linking and regional gameplay tests. The normal pipeline does
not yet automate this separate regional build procedure.
