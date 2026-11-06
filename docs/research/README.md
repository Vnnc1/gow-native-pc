# Research notes (index)

Working documents for whoever continues the project (a person or another AI). Newest first. Each one says what was
done, how it was measured, and what is left.

| Document | Subject |
|---|---|
| [gs-batch-prelude-2026-11-05.md](gs-batch-prelude-2026-11-05.md) | What the ~90 us of a GS batch are spent on: the per-batch GL prelude (pre_fbo 141-194 -> 47-94 ms per 5 s, patch 72), the discovery that this disc decodes only paletted textures (80 M texels per 5 s), and the measured falsification of linear PSMT8 rows |
| [renderer-worker-2026-11-05.md](renderer-worker-2026-11-05.md) | `PS2X_GS_WORKER=1` missing from the manual play script: frames over 33 ms drop from 92% to 61%; vertex-ring overflow guard; why mean fps could not decide the A/B (scene drift) |
| [texture-replacement.md](texture-replacement.md) | Planned runtime patch: texture dump and replacement (texture packs): how PCSX2 does it, hook points in the GS renderer, content-hash ids, indexed textures, tests, legal limits. Design only |
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
