# Community issue triage — 2026-11-09

Repository: `Vnnc1/gow-native-pc`, starting at `fix-chore` `79ec9ff` (issue 30 fix).
The GitHub open-issue list, comments and linked reports were read on this date.
Open on GitHub does not mean missing from the working branch. No issue was
closed or commented on, and no community-provided patch was executed.

## Current disposition

| Issue | Finding in the current branch | Remaining work |
| --- | --- | --- |
| [31: AF / resolution / rain stutter](https://github.com/Vnnc1/gow-native-pc/issues/31) | Rain/AF issue pending. Patch `zzz-307` adds acquisition diagnostics; `zzz-308` fixes a reproduced minimized-window close hang. Neither proves the reported rain stutter fixed. | Current-runner same-scene comparison on GTX 1060 3 GB. The original local control lacks window-state evidence; see [results and limitations](issue-31-stutter-2026-11-09.md). |
| [30: Cliffs of Madness](https://github.com/Vnnc1/gow-native-pc/issues/30) | Fixed locally in `79ec9ff`; P04MP05 completed 741 pictures and returned to gameplay. | Actual lever/save validation and release distribution; see [investigation](issue-30-movie-eof-2026-11-09.md). |
| [29: Xbox hints](https://github.com/Vnnc1/gow-native-pc/issues/29), [20: keyboard/mouse icons](https://github.com/Vnnc1/gow-native-pc/issues/20) | Feature requests, not confirmed crashes. | A separate prompt-replacement implementation and asset/licensing plan. |
| [28: black screen after Hydra](https://github.com/Vnnc1/gow-native-pc/issues/28) | Pending diagnosis: no build, disc identity, report ZIP or save in the issue. | Confirm the movie/file and runtime state before associating it with #23 or #30. A shared symptom does not establish a shared cause. |
| [27: Ryzen 3 3250U menu freeze](https://github.com/Vnnc1/gow-native-pc/issues/27) | Pending. Report source snapshot ends at patch 58; host presentation falls almost to zero while guest/audio activity persists. | Reproduce with a current runner on that GPU; existing shared-presentation changes do not prove this report fixed. |
| [25: lowest renderer contribution](https://github.com/Vnnc1/gow-native-pc/issues/25) | Already reviewed/integrated in part, with rejected and deferred portions. | Follow [delivery review](render-delivery-2026-11-04/README.md) and [PR 26 integration](pr26-integration.md); do not reapply the ZIP or claim universal 60 FPS. |
| [24: choose build location](https://github.com/Vnnc1/gow-native-pc/issues/24) | Feature request. Pipeline already accepts `-BuildRoot`; the requested installer UI is separate. | Preserve short paths and CMake ownership if adding the UI. |
| [23: ten hanging translated movies](https://github.com/Vnnc1/gow-native-pc/issues/23) | Preparation bug already fixed: exact 114692-byte fingerprint and current remapped TOC values. SEMO02/05/10 completion was previously validated. Subtitle proposal remains a separate unverified feature. | Existing discs need preparation rerun; see [prior investigation](movie-placeholder-review-2026-11-04.md). Five preparation tests passed again in this review. |
| [22: Asian translated ISO](https://github.com/Vnnc1/gow-native-pc/issues/22) | Matching Asia disc with the byte-identical USA ELF was already prepared and tested. | Do not generalize this to different-code Asian/Japanese executables; see [regional identities](regional-port-2026-11-02.md). |
| [21: rebuild rejected](https://github.com/Vnnc1/gow-native-pc/issues/21) | Screenshot is the deliberate `runtime differs from the patch chain` guard. It does not reveal which files differ. | Compare that installation's runtime with its prior/current patch trees. Preserve modifications; do not bypass the guard or automatically delete the runtime. |
| [18: installation / short TEMP path](https://github.com/Vnnc1/gow-native-pc/issues/18) | Already addressed by checkout-owned `data/_tmp`, assigned to TEMP/TMP in `build.ps1` (`c9dfb44`); maintainer comment describes the same failure. | Confirm the updated installer on the reporter's machine; no new patch needed here. |
| [17: Mac](https://github.com/Vnnc1/gow-native-pc/issues/17) | Platform request. | macOS implementation and hardware validation remain outside current support. |
| [7: Steam Deck setup](https://github.com/Vnnc1/gow-native-pc/issues/7) | Windows setup under Steam Deck is not validated. Experimental native Linux pipeline now exists. | Follow [Linux acceptance gates](../linux.md); do not label the host-library archive universally SteamOS-compatible. |
| [6: visited-area optimization crash](https://github.com/Vnnc1/gow-native-pc/issues/6) | Log identifies `std::bad_alloc` in `ps2x_vu1_generator`, not a guest crash. New memory correction described below. | Reporter capture set was not supplied; do not close the issue solely from the synthetic test. |

## Issue 6: generator memory correction

The build log's failed command runs `ps2x_vu1_generator` over the capture folder.
It terminates with an uncaught `std::bad_alloc` (Windows code 3221226505).
The maintainer previously asked for a retest on v0.4.0, but no confirming report
followed. Patch `zzz-301` concerns PGO profile scope, not this allocation failure.

Current production `tools/vu1/generar_vu1.cpp` retains a decoded `Code` for every
input image, including 2048 decoded pairs and validity bits, until both generation
passes finish. Most repeated input instructions later deduplicate in the output,
but their decoded copies remain resident. It also reads each entire input before
checking the required 16 KiB size.

`zzz-306-vu1-generator-memory.patch` retains raw 16 KiB images and decodes one
image at a time in each existing pass. Both pass orders and all emission logic
are unchanged. The extra decode pass trades CPU work for lower retained memory;
no build-time speedup is claimed. File length is checked before allocating its
buffer, and failed/short reads return an error before generated outputs change.
Unique generated functions/blocks still consume memory; the tool is not bounded
to a fixed overall memory ceiling for arbitrarily large capture sets.

### Validation

Isolated current-chain Release build on Windows / Xeon E5-2666 v3 / RX 580,
pinned LLVM 20261020, no PGO. The installed game and original captures were not
modified. All input copies and generated C++ remain ignored under
`data/issue-triage/next`.

| Workload | Baseline | Candidate |
| --- | --- | --- |
| 1000 zeroed 16 KiB images | Exit 0, peak working set 158097408 bytes | Exit 0, peak working set 26755072 bytes |
| Same 1000-image output | 13 files | All 13 byte-identical to baseline |
| Eight real captured images | 3942 pair functions, 821 blocks | All 13 output files byte-identical to baseline |
| Synthetic NOP/E-bit fixtures | Reference output retained | Output equality, explicit/directory input parity and unchanged-file timestamps pass |
| Missing, 0/16383/16385-byte and 1 GiB inputs | Not used as acceptance baseline | Rejected; previous output files preserved |

Peak working set was sampled from Windows `Process.PeakWorkingSet64` at 20 ms;
it is not private bytes or a gameplay metric. Both memory-comparison runs
succeeded: the original reporter's allocation crash was **not** reproduced.
This demonstrates removal of a current avoidable memory cost and bounded input
reads, not proof that every possible `bad_alloc` is eliminated.

Commands:

```powershell
python -I tools/test/vu1-generator-tests.py --generator <built-ps2x_vu1_generator.exe> --reference <baseline-generator.exe>
python -I tools/disc/prepare_test.py
python -I tools/test/pipeline_tests.py
python -I tools/test/linux_pipeline_tests.py
```

The generator tests passed. Disc preparation: 5 passed; pipeline: 17 passed.
Linux pipeline: 7 ran, OK with 1 Windows platform skip. The new patch passes
forward and reverse checks on the current 119-patch runtime chain; `git diff
--check` passed.
The optional reference is used for acceptance comparisons; normal future runs
can omit it. No runtime gameplay logic or generated instruction semantics changed;
no new game FPS, NVIDIA, Linux gameplay or full `verify` claim is made.

Candidate generator SHA-256:
`e1662de34353d9e2d86a4d58a2ee73633e1601c0ac3210d76931da816a18338a`.
Baseline generator SHA-256:
`756c5eb59b44d60897bd440048d0a82055b7d5e0c1ee671ca85094564efaea38`.

## Performance reports: evidence boundaries

Issue 31's collector records 178 guest-FPS windows, 28.96–60.2 FPS, five guest
intervals over 100 ms and a maximum of 2621.293 ms. Those session-wide observations
include transitions; they cannot be assigned to combat/rain without synchronized
scene evidence. Late windows report about 54 guest FPS and 60 host presentations/s.
No guest missing-target/budget/termination error was found in that log. The source
patch snapshot is not proof of which patches were compiled into its runner.

Issue 27's attached session differs from the narrative settings: it records a
30 FPS cap, VSync, 2x internal scale, AF 4 and the power-saving GPU preference.
Its first two performance windows report host_hz 7.14 then 0.08, while guest probes
remain around 55–57 Hz. Later audio/IOP logs continue. This is insufficient to
assign a rendering deadlock, input failure or general CPU limit as the cause.
The snapshot and actual settings must be retained in any current-runner retest.
