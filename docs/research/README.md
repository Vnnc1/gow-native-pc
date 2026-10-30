# Research notes (index)

Working documents for whoever continues the project (a person or another AI). Newest first. Each one says what was
done, how it was measured, and what is left.

| Document | Subject |
|---|---|
| [patches-28-29-review.md](patches-28-29-review.md) | Windows call-path regression review, standalone diagnostic initialization and trace-clock fixes, reproducible tests before patch 30 |
| [roadmap-2026-10-27.md](roadmap-2026-10-27.md) | Code survey and next phases: direct JAL calls, dispatch/memory fast paths, ThinLTO/cache/PGO, 60 fps (early FINISH, chain, CD reads, pacing), audio, ISO/texture mods, FSR/DXGI/DLSS limits, GoW2 hook (patches 28-47) |
| [cutscene-audio-2026-10-26.md](cutscene-audio-2026-10-26.md) | Reproduced PT-BR A01MP02 channel-block misalignment; original-disc control, raw PCM comparison and correction plan |
| [audio-standalone-mods-2026-10-26.md](audio-standalone-mods-2026-10-26.md) | Mixer overflow regression, direct launch, audio diagnosis, HUD and mod compatibility roadmap |
| [jit-delivery-2026-10-26.md](jit-delivery-2026-10-26.md) | Patches 19-23, disc scan/cache, miss capture, incremental compilation, launcher integration, real-game JIT validation and next patches |
| [vu1-x64-jit.md](vu1-x64-jit.md) | The in-process x86-64 VU1 JIT (engine/patches/18, 27): design, contracts with the dispatcher, speed work to AOT parity, tests and measurement scripts, how to extend it, bugs found, risks |
| [vu1-jit-prototype-2026-10-26.md](vu1-jit-prototype-2026-10-26.md) | VU1 code for every area: disc extraction (tools/disc/vu1_from_disc.py), background clang compiler (patch 17) |
| [handoff-2026-10-25-performance-phases.md](handoff-2026-10-25-performance-phases.md) | Performance phases 1-5 (patches 10-13), frame timeline, how to measure |
| [ps2-ports-review-2026-10-25.md](ps2-ports-review-2026-10-25.md) | Review of other PS2 ports (rac-rs, PS2Recomp, SpartanPort) that produced the phases |

Rules that hold for all of them: runtime changes are new `engine/patches/NN-*.patch` files (never edit an applied patch's
context), game data never leaves `data/`, and measurements name the machine and the settings.
