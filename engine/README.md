# engine/

- `runtime.toml` — which runtime to download (repository + pinned commit). **Required**: PS2Recomp (ran-j) and the
  native runtime built on it (Waffle565, KIexster, Tobiichi-Port). Stage `fetch` (or the launcher's "Download
  runtime") clones it into `engine/runtime/` (git-ignored).
- `patches/NN-*.patch` — this project's changes to the runtime, applied in name order. Each starts with a few lines
  saying what it changes, why, and where it came from; `git apply` skips those lines.

| Patch | What | Origin |
|---|---|---|
| 01-release-ltcg-option | `PS2X_RELEASE_LTCG` option, Release built without LTCG | this project |
| 02-vu1-capture-with-native | VU1 microcode recording with the native VU1 active | KIexster |
| 03-fullscreen-windows-crash | fullscreen / F11 crash on Windows | this project |
| 04-cpu-backports-from-waffle | EE / VIF1 / VU1 / DMA speed-ups (42-45 → 59-60 fps on the reference machine) | Waffle565 |
| 05-gow2-runtime-fixes | GS upscaling fixes (bloom ghost, CLAMP edges, point-sampled scaled targets, sprite edges, Z clears, channel shuffles), anisotropic filtering (`GOW_ANISO`), runtime RPC/TLS pools out of the game heap, scratchpad DMA interleave, MPEG audio stream type, memory card file kept open, IOP `strtok`/`GetSystemTimeLow` | God of War II port (cxldsakeb, DaniSBR1: fork DaniSBR1/PS2Recomp, branch `godofwar2`) |
| 06-recompiler-movn-movz-64bit | MOVZ/MOVN write only the low 64 bits of rd, as on the R5900 (needs a recompile) | God of War II port (`ddcc548`), redone here |
| 07-vu1-heads-sound-batch-pdb | Native VU1: records block entries without native code (`vu1n_heads_seen.txt`); SPU2 mixer: one output lock per batch instead of per sample; `PS2X_RELEASE_PDB` (Release with debug information) | this project |
| 08-codegen-register-locals | Recompiler mode "register locals" (`PS2X_CODEGEN=locals`; the pipeline's default, `build.cmd -Codegen classic` turns it off): guest registers in C++ locals, `ctx->pc` stored only where read; ~22 % less EE thread time in combat. Without the variable the generated code is the same as before | Killzone port's patch 0017 (drakolordx7/KillzoneRecomp), adapted here |
| 09-vu1-capture-gs-stage-copy | The launcher's continuous VU1 capture without the per-change decode, byte hash and file-system query (~15 % of the VU1 worker); GS stage packets copied outside its lock. Combat with the launcher defaults 47.6 -> 57.6 fps average | this project |
| 10-vu1-clean-operands | Native VU1: clean-operand analysis across blocks (no Inf/NaN normalisation where provably unneeded, 9,833 -> 6,273 normalised loads), checked at run time along the blocks actually run | rac-rs `tools/vu/vuclean.py` (AsobiCodes), adapted here |
| 11-sound-batch-ee-count-iop-heap | SPU2 mixer voice by voice in 64-frame batches (bit-identical, `GOW_SND_VERIFY`; ~14 % -> ~4 % of the game thread); COP0 Count follows the EE clock (God of War's per-frame work budget at 0x185A20); IOP heap reuses freed memory | this project; God of War II port (Count), Killzone port 0028 (heap) |
| 12-clang-build-gs-state-compare | Builds with clang / llvm-mingw: GS draw states compared field by field (raw `memcmp` read unspecified padding: with clang every primitive was its own batch), shadow-volume counting batches drawn per colour run, small portability fixes, profile write-out for PGO training builds | this project |
| 13-vu1-block-chaining | Native VU1 blocks jump straight to their successor (guaranteed tail call; clang only, `GOW_VU1N_CHAIN`), lane masks in the dispatch slot, self-loop counters, replay workbench timing. Bit-exact; about -2 % VU1 time | this project (phase 3/5 attempt, see docs/research/handoff-2026-10-25-performance-phases.md) |
| 14-controller-layout | Controller layout chosen button by button in the launcher (`TOBIICHI_MANDO`, same action names as the keyboard map); without it the fixed modern / classic layouts stay | this project |
| 15-hidden-window | `GOW_WINDOW_HIDDEN=1` opens the game window hidden (raylib `FLAG_WINDOW_HIDDEN`): the pipeline's recording and PGO runs play in the background while the launcher shows its loading screen; the GPU still draws, so the shader cache is filled the same way | this project |
| 16-vu1-rebuild-only-vu1 | The include folder of the generated VU1 code set on those files only, not on the game target: the rebuild after the first-play recording compiles the VU1 code instead of the whole game (~959 steps) | this project |
| 17-qte-hold-to-mash | Accessibility: a held button becomes the train of presses the minigames ask for (`GOW_QTE_HOLD`, launcher option "Hold instead of mashing"); logic in `runtime/gow_qte_hold.h`, tested by `tools/tests/qte_hold_test.cpp`. Without the variable nothing changes | this project |
