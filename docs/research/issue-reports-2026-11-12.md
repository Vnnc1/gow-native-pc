# Player report ZIPs for issues 33, 31 and 30 — 2026-11-12

The three session-report ZIPs attached to the open issues were downloaded into a private scratch folder,
extracted by name-checked Python (no path traversal, nothing executed) and read as data. They are not committed:
they are player sessions, kept out of the repository like other diagnostic exports. Issues 34 and 28 attach no ZIP.

| Issue | ZIP SHA-256 | Launcher | ELF SHA-256 | Language | Hardware |
| --- | --- | --- | --- | --- | --- |
| [33](https://github.com/Vnnc1/gow-native-pc/issues/33) | `20ee847f…a355` | 0.6.0 | `560aa561…338c` | ru | Ryzen 7 7700, GTX 1060 3 GB |
| [31](https://github.com/Vnnc1/gow-native-pc/issues/31) | `04b3d4df…caa1` (already analysed in `issue-31-stutter-2026-11-09.md`) | 0.5.0 | `560aa561…338c` | ru | same machine |
| [30](https://github.com/Vnnc1/gow-native-pc/issues/30) | `af8b881c…4575` | 0.5.0 | `ec9397d2…ad71c` | en | — |

Issues 33 and 31 come from the same player and the same Russian-translation ELF (the runtime still identifies the
USA tables, `SCUS-97399`, so the `.text` matches the USA code as `game.toml` requires).

## Issue 33: not the movie EOF hang — a null-object virtual call after the Cronos movie

The 0.6.0 build contains `zzz-305` (source patch list in `session.json`). Settings differ from defaults:
2x, `GOW_VU1_FAST=1`, and the three FX mods `GOW_FX_NO_SHADOWS`, `GOW_FX_NO_ADDITIVE3D`, `GOW_FX_NO_TEXTURE_FILTER`.

Timeline from `metrics.jsonl`, `events.jsonl` and `runtime.log` (session time):

1. 160 s, 214 s, 265 s: three MPEG starts (`[MPEG:AddCallback] mpeg=0x304dc8`); the 32 s and 9.6 s guest-interval
   spikes are movies (no guest flips while they play).
2. 282–385 s: zero guest flips for about 100 s while host presentation continues. Host "fresh" publications stay at
   300 per window here and after the crash too, so they do not prove a movie was playing; the 106,118 ms interval ends
   at 384.5 s.
3. 385–390 s: guest flips resume (6, then 25 per window). Unlike issue 30, the movie stage did end.
4. 389.396 s: `[guest-branch:missing-target] kind=IndirectCall op=JALR source=0x1d6d44 target=0x308b527b`,
   then `main thread dormant`. The game never flips again; the player closes it at 463 s (exit 0).

The call site, from the generated `sub_001D6CD0`:

```
0x1d6d30  lw   $a1, 0x0($s2)      # object = *this
0x1d6d38  lw   $v0, 0x4($a1)      # vtable = object->vptr
0x1d6d3c  lh   $a0, 0x68($v0)     # this-adjust
0x1d6d40  lw   $v0, 0x6C($v0)     # method
0x1d6d44  jalr $v0
```

The dump has `a1=0x0`: the object pointer stored in the first word of the argument is null, so the "vtable" came
from address 4 and the target is garbage. `sub_001D6CD0` has no direct JAL callers; it is reached through a function
pointer (a callback or virtual method), which fits an entity whose owner/link was never filled in after the movie's
area transition. No disc/file error, IOP error or CD read failure is logged around it.

What this does **not** establish: which entity is null, whether the Russian translation's data, VU1 fast mode, the FX
mods or a recompilation defect caused it. VU1 fast mode changes VU1 float semantics for rendering and the FX mods only
skip GS draws, so neither is an obvious EE-pointer cause, but neither was excluded by a run. A guard that skips the
call would hide the symptom and change game logic without evidence; no runtime change was made.

Needed to reproduce (ask the player): the memory card (or a save) from before the Cronos climb, a rerun with VU1 fast
mode and the three FX mods off, and, if possible, the same scene with the original USA disc. With a card, the next
step is the private-card route here: reach the cutscene with `GOW_DISPATCH_FULL=1` (fuller branch history), then
inspect the argument object of `0x1d6cd0` at the first null load.

Diagnostic gap found: the missing-target dump prints `a0`/`s0` contents but not `s2`, which held `this` here.
Printing all saved registers (`s0`–`s7`) and the first words they point to would identify the object in the next report.

## Issue 30: matches the fixed USA movie-EOF hang

USA tables, launcher 0.5.0. After the movie starts at 123 s, guest flips drop to 0 at 131 s and never resume up to the
exit at 306 s. That is the drained-reader retry loop `zzz-305` fixed in 0.6.0 (`issue-30-movie-eof-2026-11-09.md`).
The reporter has not retested on 0.6.0; Europe/Japan overlays still lack the wrappers.

## Issue 31

Same ZIP hash as the one analysed on 2026-11-09; nothing new in it. The reporter's 2026-11-10 update (3x still bad,
AF16 drops to 30 under Hydra particles) predates `zzz-326`, which is the candidate to retest (GPU-06 gates).
