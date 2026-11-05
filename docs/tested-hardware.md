# Tested hardware and results

## Experimental high logic rate (2026-11-05, i5-8265U / UHD 620)

Patch 73 adds opt-in 120/240 logic rates; original 60 Hz remains the default.
Release build/full verify passed, including 41 synthetic adapter cases, 13 CTest
groups and VU1 equivalence. A visible, audio-enabled private-card `ship_guard`
pair at 1x/1280x720 passed the session and scene-envelope gates. With host cap 120
in both variants, original 60 measured **21.06 guest FPS**, versus **15.60** for
experimental 120. Median window p95 worsened **63.32 -> 115.20 ms**; game-time/wall-time
ratio fell **0.980 -> 0.853**, and audio missing frames increased **5,125 -> 15,523**
out of 2,400,000 requested. This single pair supports no default promotion or
general performance claim. The scene envelope is not a frame-identical replay.

A separate 240 pilot reached 22.79 guest FPS, not 240; its different host cap and
unpaired execution prevent a performance comparison. Original saves remained
unchanged. A separate capture verified rendered opening combat; after user-requested
minimization that session required forced termination, so its exit check failed.
An earlier original-60 run also had a presentation stall and was rejected.
No gameplay above 60 FPS, 120 Hz scanout, QTE/combo parity or whole-game compatibility
was validated. See [settings, evidence and limitations](research/experimental-logic-rate.md).

## Paused VU1/combat investigation (2026-11-04, i5-8265U / UHD 620)

The new private-card combat-corner pilot reached an active rendered encounter and
exited gracefully in both runs, with original saves unchanged, but failed the
same-scene trajectory gate. It included screenshots and one intrusive sampler;
its FPS is not an accepted comparison. VU1 wall samples again concentrated on
chain bookkeeping (29.14%) and block timing (2.69%); actual worker CPU time was
32.97% of one logical core, a different metric.

A source-only scalar-loop outline built the isolated replay/fuzz executables.
Five paired JIT replays of the same 32 tasks measured median summed warm costs
561.8 -> 507.8 us (-9.61%), with all record baselines/block counts matching.
The fuzz executable was built but not run in this follow-up. Full equivalence,
shipped hybrid gameplay, frame tails and audio acceptance remain pending.
The installed runner is unchanged; runtime sources were restored and drafts
saved outside the ordinal chain at the user's pause request. No game/sampler
process remained running. See [checkpoint and exact evidence](research/render-delivery-2026-11-04/resume-checkpoint.md).

## Frame-aligned arrival and VU1 chain (2026-11-04, i5-8265U / UHD 620)

Patch 70 stabilizes the first 360 rendered ship-arrival frames with frame-indexed
input, trajectory gates and bounded interval/audio measurements. It does not yet
stabilize combat. All three initial hybrid pairs and three final JIT-only pairs
passed the arrival scene gates; all used private cards and verified unchanged
original saves. Tests ran in hidden windows with audio, fixed 1x and 1280x720.

Patch 71 is an optional JIT adapter (`GOW_VU1X_CHAIN_INLINE=1`), default off. The
hybrid arrival uses AOT and did not exercise it; the final gameplay comparison
explicitly forced JIT-only in both variants. Mean FPS was **52.263 -> 52.621 (+0.68%)**,
but median per-run p95 worsened **26.981 -> 28.440 ms**, with a candidate p99 outlier
of **56.288 ms**. The tail gate failed. Same-binary 32-task CPU replay measured
**460.4 -> 458.6 us (-0.39%)**, within observed variation; this did not reproduce
the initial unconditional experiment's 4.08%. No default promotion or significant
FPS/resource-consumption improvement is established.

All short arrival windows had zero missing audio frames; this does not fix or
validate long-combat sound. GPU load remained near saturation. `fetch,build,verify`
passed with 13 CTest groups, VU1 backend/self-loop equivalence including the optional
adapter, and task replay. The methodology and final explicit-mode replay checks
also passed. Final runner: `bbf74abfb8971e3b8d526a92fdedb5aeac4640b788a19601729734d7272bee7b`.
See [complete results, rejected attempts and remaining gates](research/render-delivery-2026-11-04/vu1-chain.md).

## Oscillation/audio follow-up (2026-11-04, background sessions under competing load)

i5-8265U, 24 GiB, Intel UHD 620 / driver 27.20.100.9664, AC, portable Clang Release -O3,
1x internal rendering, 1280x720, audio enabled. Original player cards were never supplied;
every session used a private disc/card root and verified unchanged original save inventories.

- A separate intrusive diagnostic pair measured 98% peak GPU engine utilization even with
  primitive grouping off. Process CPU averaged about 1.6 cores, not the whole eight-thread CPU.
- Patch 67's provably empty alpha-pass elimination passed the exhaustive 16,777,216-case oracle,
  but three paired hidden tests favored the reference: 43.552 vs 36.124 mean guest FPS.
  The feature remains opt-in, like patch 66. No stable 60 FPS or resolved-audio claim.
- The existing bilinear output filter reduced observed average GPU busy time (58.50% to 45.65%),
  but also had lower observed FPS (28.394 to 22.379) and more missing audio frames. No player
  filter setting was changed. These runs had competing system load; the final pair measured
  83.0% / 81.2% mean total CPU, reaching 100%, and real-time scene alignment is not guaranteed.
- The final runner is `6635147d6d41398e020b21d2e2dcef2ba837ae4f0306ba42b443aa41e343942b`.
  `fetch,build,verify` passed with 12 CTest groups plus codegen, memory, sound, VU1 equivalence
  and task replay checks. Python methodology checks and live Windows PDH collection passed.

These results reject default promotion; they do not isolate a universal renderer regression or
measure watts/temperature. The earlier firmware-limit event predates these runs. Visible play,
listening assessment, stable scene/clock evidence and other GPU tiers remain open.
See [every run, metrics and next gates](research/render-delivery-2026-11-04/followup.md).

## Patch 66 laptop A/B (2026-11-04, background sessions, experimental)

i5-8265U, about 24 GiB RAM, Intel UHD 620 (driver 27.20.100.9664), Windows 11 Pro 22631, AC power.
The user requested hidden-window testing. Same binary, PT-BR disc, audio enabled, fixed 1x/1280x720, optional VU1
fast arithmetic off; three alternating pairs of 120 seconds, complete windows after 60 seconds only.

Mean guest FPS: **32.107 off → 34.101 on (+6.213%)**. Every pair improved FPS, but the last pair regressed p95
50.243 → 63.274 ms, p99 68.690 → 86.469 ms, maximum interval 176.359 → 215.599 ms, and missing audio frames
7,026 → 14,628. There was substantial slowdown in both modes across the session; its cause was not isolated.
Grouping remains opt-in (`PS2X_GS_RUN=1`), and neither stable 60 FPS nor visible-play/tier acceptance is claimed.

All six sessions reached gameplay, exited gracefully with code 0, and preserved the original project save inventory.
Only private card/save roots were used. Separate off/on ship-combat captures showed no obvious corruption; they are
not animated-frame byte equivalence. Full verification, production queue/frontend parity and ASan checks passed.
See the [complete results and next gates](research/render-delivery-2026-11-04/integration.md).

## Renderer delivery review (2026-11-04, CPU-only checks)

On this laptop, the supplied renderer's extracted `SubmitRun` and `ringAppend` implementations were compiled with
pinned Clang 23.1.4 and AddressSanitizer. The original passed 3/11 cases; two review overlays passed 11/11, covering
default vertex tails, records split at 64 primitives, and current-generation fence completion/error handling.
GL completion was mocked; no GPU, gameplay FPS or frame-pacing improvement was measured. The installed runtime
and saves were unchanged. See the [review and promotion gates](research/render-delivery-2026-11-04/README.md).

## Installed SEMO movie fallback validation (2026-11-04, i5-8265U laptop)

Applied the corrected standalone PT-BR TOC to `data/gow1/discs/translation-pt-br-d95720d3` after preserving the
previous index. Exactly 15 widescreen entries changed; all now point to their matching part-0 PSS payloads.
Installed TOC SHA-256: `c586396bcbedfa6ef375b05fc76a6f686327ea05150a0667c74e94995b29bc57`.
The source ISO/PAKs and `.orig` were not rewritten.

Tested the existing installed Clang runner from 2026-10-28, SHA-256
`515a5bdbf91d6fdda3fee5f953d231d33119da8fdbc1d5ff49b3996ad738d682`; this is not a new v0.5.0 runtime build.
Intel UHD 620, fixed 1x rendering, hidden window, audio enabled, FMV skipping disabled. Each movie was started by
`GOW_MOVIE_OVERRIDE` through the bonus-menu diagnostic path, without scripted skip input. Each run used a private
ELF/disc root with an identical corrected TOC, shared read-only PAK inputs, separate mc0/mc1 directories, and private
`GOW_MC0` / `GOW_SAVES_DIR` paths. No player card or save directory was supplied to the game.

| Movie | Pictures served at decoder end | Whole test session, including boot/shutdown | Result |
| --- | ---: | ---: | --- |
| SEMO02 | 4,229 | 158.25 s | Sequence end, movie state 11 to 0, exit 0 |
| SEMO05 | 3,340 | 128.98 s | Sequence end, movie state 11 to 0, exit 0 |
| SEMO10 | 6,731 | 241.72 s | Sequence end, movie state 11 to 0, exit 0 |

All three recorded `ended=1 failed=0 seqEnd=1`, returned to the menu and closed gracefully. No guest budget error,
missing branch target, access violation or forced termination was logged. Picture 300 was dumped and visually
checked for each movie; SEMO05 includes the translation's burned-in subtitle. These are complete playback tests
of the replacement movie streams, not just a first-picture check. There was one run per movie; normal story entry,
audible synchronization and a rebuilt v0.5.0 runner were not tested.

The installed TOC still matches the corrected hash after testing. The checked installed mc0/save directories and
disc-card inventory were unchanged (no existing save files were present in those project paths). Test cards and
HLE save paths remained isolated even if the runtime used its ELF-relative fallback.

Evidence: `data/gow1/logs/movie-installed-20261104-123510/validated-results.json`, `installation.json`,
`GODOFWAR.TOC.before`, and each movie's session logs/metadata/events and local picture capture. These ignored
artifacts contain game-derived media and are not packaged or committed.

## Translation movie preparation review (2026-11-04)

On the local compatible PT-BR standalone disc (`D95720D3`), confirmed ten 114,692-byte SEMO widescreen placeholders
matching the submitted SHA-256. Private-TOC normalization maps 15 entries after fixing the stale tuple lookup;
adding only the fingerprint leaves four part-1 duplicates uncorrected. Source media and installed TOC were preserved.
Three preparation tests (including three new regression subcases), eight import tests, the offscreen import QML
check and 17 pipeline tests pass. Six real CHD cases were skipped without `chdman`.
This validates preparation, not full movie playback, subtitles, audio synchronization or FPS. See the
[investigation](research/movie-placeholder-review-2026-11-04.md) for evidence and unresolved report claims.

## RX 5500 XT player observation (2026-11-03; not locally validated)

Player reports drastic FPS drops near full GPU utilization during Hydra attacks
above and below the ship deck, launcher 0.5.0, defaults and VSync off. No target
runner hash, driver, exact FPS range or trace supplied yet. This is an observation,
not an RX5500 XT benchmark, confirmed root cause or performance-support claim.
The [source investigation](research/gpu-saturation-2026-11-03.md) records the
destination-blending fallback, presentation/queue mechanisms and required measurements.

For prior hypotheses, rejected changes and incomplete gains, start with the
[performance experiment ledger](research/performance-experiments.md). Consult its
retest rules before repeating a performance investigation; detailed evidence follows here.

## VU1 / synchronization follow-up (2026-11-03)

On Xeon E5-2666 v3 / RX 580 2048SP, three isolated candidates were compared with
the patch-60 baseline using three alternating visible, audio-enabled pairs each
(100 seconds, complete measurement windows after 40 seconds, 1x, precise VU,
GS early FINISH on). No compilation/profiling overlapped FPS measurements.

| Candidate | Baseline → candidate mean guest FPS | Decision |
| --- | ---: | --- |
| Separate stage head/tail cache lines | 59.4245 → 59.5143 | Rejected: +0.15%, inconsistent pairs/pacing |
| Separate VU1 timing history from flag tails | 59.4121 → 59.4173 | Rejected: gameplay tied despite -0.37% isolated JIT replay time |
| Publish consumed stage space every 4 KiB / batch end | 59.3409 → 57.7046 | Rejected: -2.76%, lost all pairs |

All 18 runs passed gameplay, graceful exit and measurement checks. The VU1
candidate passed the full verify gate and the local 128-task corpus across five
backends; the queue candidate passed production DMA/worker/ring tests. Runtime
sources were restored exactly. No additional FPS gain, notebook validation or
28-minute-scene reproduction is claimed. Details and local evidence paths:
[experiment report](research/vu1-sync-2026-11-03.md).

## Default GS texture storage update (2026-11-03)

Patch 60 bounds decoded RGBA/index texture storage to 128 MiB before upload and
updates existing same-shape storage with `TexSubImage2D` instead of redefining it.
No player setting is required. The budget excludes render targets, replacement
packs, driver staging and other process memory; it is not a total RAM cap.

On Xeon E5-2666 v3 / RX 580 2048SP, three alternating pairs of visible, audio-enabled
100-second scripted runs used internal 1x, 1280x720, host cap 60, VSync off, early GS
FINISH and precise VU defaults. Complete measurement windows begin after 40 seconds.
No concurrent compilation or profiling ran during these FPS comparisons.

| Pair | Baseline guest FPS | Updated guest FPS | Change |
| --- | ---: | ---: | ---: |
| 1 | 59.091 | 59.382 | +0.49% |
| 2 | 58.600 | 59.690 | +1.86% |
| 3 | 59.127 | 59.471 | +0.58% |
| Mean | 58.940 | 59.514 | +0.97% |

Lowest five-second windows across these runs were 45.2 and 54.8 FPS respectively;
neither variant had a measured interval above 100 ms after warm-up. Window-p95
medians were 17.060–17.148 ms versus 17.075–17.121 ms. Private-memory peaks overlapped
(baseline 326.9–336.5 MiB; updated 319.0–347.8 MiB), so no process-memory reduction is
established here. This timed input route does not guarantee identical scene alignment;
the small positive result in 3/3 pairs is not locked-60 or full-game acceptance.

The earlier budget-only layout was slower: 59.145 -> 58.596 FPS. It is not the final
implementation. The final change also reuses storage and appends accounting members
to preserve existing renderer member offsets. Evidence is retained under
`data/experiments/gs61/{ab,ab-reuse,result.json}`. Baseline runner SHA-256:
`d1a6b52699c4964e3a87fbc14a889f3e9200ae91d72cb87d4a2771f5c33b9ab2`;
updated runner: `f269bfc2fe3762b9446e4124176c236b9a1833547d4e79fd6df2232d1e52be0c`.

Validation: `build.cmd -Stages verify` passed (11 native suites, synthetic ELF,
VU1 equivalence and isolated replay); Linux pipeline tests passed with one
platform-specific skip. The production eviction policy passed a 9,996-upload
stress loop. The optional real-GPU `gow_texture_upload_test` verified alternating
red/blue pixels after 20 invalidating uploads each in CT32, T8 and T4 on RX 580.
The visible `session-game-smoke.py --capture --early-finish --texture-cache` run
passed all 13 checks, including 2,000 VU1 parity checks, and its gameplay image was
inspected. It recorded 17,222 storage reuses; its approximately 7.2 MiB working set
did not exercise in-game eviction. Eviction pressure is covered by the synthetic
policy test, not by a reproduced Intel memory spike.

The i3-10110U/Intel UHD multi-second stalls and near-6-GiB process-memory spike
remain unvalidated with this revision. NVIDIA is also untested. No VU1 semantic or
queue-ordering changes were adopted; existing unsuccessful chain/spin experiments
remain rejected. The private kit now enables GS cache counters in detailed mode.

## Supplied Asia disc and Europe code generation (2026-11-02)

The supplied `God of War (Asia).iso` boots `SCUS_973.99` and has the same complete
ELF SHA-256 as the USA disc: `ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c`.
Disc SHA-256 and file layout differ, so the actual Asia disc was extracted through
`discs,recomp,sync,build`, not substituted with USA media. The installed manifest
now uses that prepared disc. Generation processed 6,414 functions (6,339 translated,
75 stubs), with zero decoder failures or unhandled instructions; native build passed.

Three 100-second private-card smoke runs reached `state=11 levelReady=1` and passed
all collector checks: frames, audio/IOP activity, native/JIT metrics, 2,000 VU1 parity
checks without mismatches, marker and graceful stop. The first desktop capture
attempt timed out; the final run used `session-game-smoke.py --visible --capture`
and its 80-second GS image was inspected: Kratos, enemies, ship deck and HUD rendered.
Audio processing was enabled/observed in metrics, not independently listened to.
This validates opening gameplay only, not the whole game or a new performance tier.
Captures stay in ignored data and are excluded from report export.

Europe `SCES_531.33` / `FB0E6D72` was inspected and translated in isolated data.
Automatic discovery initially decoded data as instructions (1,341 reported errors
although exit code was zero). A candidate function map bounded to `.text` generated
6,410 functions with zero unhandled instructions, but lacks verified SDK bindings,
overrides and globals. It was not linked or run and remains blocked in the launcher.
The production recompiler now rejects a foreign ELF/name or code signature before
replacing generated output, including stale/hand-edited language manifests. Sixteen
pipeline regressions passed; Linux orchestration passed six tests with its POSIX-only
case skipped on Windows. Details: [regional investigation](research/regional-port-2026-11-02.md).

## CHD import and regional identification (2026-11-02; Windows host)

Fourteen import tests passed, including real CHDs created with pinned MAME 0.289
from a synthetic ISO: DVD and legacy MODE1/2048 round trips, cache repair/reuse,
corruption, interrupted extraction, concurrent locks, disk space, Unicode paths,
source changes and mixed-track rejection. A clean Windows tool bootstrap and
offline reuse were also exercised. `chdman verify` returning zero on a hash mismatch
was reproduced; the importer now requires both SHA-1 success confirmations.

The actual Install QML passed retry replacement, region/demo gates, original CHD
path forwarding, logs and import-busy state. Pipeline tests passed (14 Python,
7 Linux orchestration with the POSIX-only case skipped on Windows), as did disc
normalization and launcher languages. The launcher built against the existing
llvm-mingw Qt SDK; its deployed Portuguese Install page was visually inspected.

The actual Japan ISO was identified as SLPM_670.10 / CA052D22. Its code differs
from USA; a scratch preparation correctly rejected it before publication. Japan,
Asia and Europe are recognized but are NOT enabled for gameplay. No real game CHD,
Asia/Europe ISO, Linux execution or regional gameplay was tested. Analysis and
remaining requirements: [disc import](disc-import.md).

## Accessibility conflict review (2026-11-02; synthetic validation)

Patch 58 protects all simultaneous button combinations from repetition, including
R2 + Cross when face-button repetition is enabled. The production-input regression
passes with all face and shoulder buttons selected; the isolated suite checks all
28 face/shoulder pairs and preserves single-button repetition. All 10 CTest tests
passed. The real QML test also confirms conflict-free defaults and that legacy
migration does not assign Alt/G over existing custom bindings. Occupied new
shortcuts remain unassigned for the user to configure in Controls.

No crate-scene completion, Medusa escape, controller hardware or Linux gameplay
was tested in this review. These results validate input behavior only.

## Accessibility and held keyboard combinations (2026-11-02; synthetic validation)

Patches 56–57 add explicit keyboard/mouse left-stick gestures and preserve held
button combinations. Ctrl remains R2, while the default evade modifier migrates
to Alt. Shoulder repetition is individually selectable and pauses during stick
movement or multi-button interactions. The launcher groups these assists and
the existing texture-pack controls on Accessibility.

Validation: the game runner rebuilt successfully; the complete `verify` stage
passed (10 CTest tests, pipeline/patch-stack regressions, synthetic EE generation,
guest-call checks, VU1 equivalence and task replay). The production input reader
was exercised with a fake host for Ctrl + WASD, Ctrl + Space, Alt + movement,
keyboard/mouse gestures, four controller slots, focus loss and scripted-test
exclusion. The actual QML test passed saved choices, legacy-map migration,
custom-binding preservation, conflict reporting and texture-pack enablement.
The Windows launcher was rebuilt and deployed to `launcher/build-clang/deploy`;
its Accessibility page was inspected through the built-in Portuguese capture mode.

These tests establish input behavior, not successful completion of the opening
ship's crate scene, Medusa petrification or every grab/QTE. No gameplay FPS or
new hardware support claim was measured. Instructions: [input accessibility](input-accessibility.md).

## Linux integration foundation (2026-11-02; Windows host only)

Added a native Clang/Qt/SDL2 source-build pipeline and Linux launcher routing.
Local validation: 14 existing generation/synchronization tests and 6 Linux
orchestration tests passed; the POSIX lock test was skipped on Windows. Launcher
language validation passed, and the llvm-mingw/Qt 6.8.3 Windows launcher compiled.
These tests cover patch-prefix resume/local-edit protection, compiler flags,
argument handling and failed-build publication, not Linux execution.

The new Linux CI workflow has not been executed in this session. No Linux
launcher/runtime binary, GPU rendering, sound, gamepad input, frame pacing or
Steam Deck gameplay was validated. All Linux hardware tiers remain unvalidated;
see [Linux acceptance requirements](linux.md). The existing Linux OpenGL and
System V JIT implementations were not changed or measured in this work.

## Player log review (2026-10-29, Xeon / RX 580; observational)

Session `20261029-232953-466-5d1a01d1` completes in 565.277 seconds with exit code 0. Recorded configuration:
Release, portable x86-64-v2, ThinLTO off, scale 2 with dynamic scaling, FXAA on, 60 Hz host cap and basic diagnostics.
Seventy complete FPS windows contained in runtime t=130–485 seconds average 44.42 guest FPS (32.10–59.97), while
host frequency averages 59.95 Hz. No stable-60 claim is supported. The corresponding frame-window selection has
zero intervals above 100 ms; full-session long gaps include MPEG-associated transitions and require separate interpretation.

Earlier retained sessions do not establish a controlled baseline: the ELF hash differs and scene/input alignment
is unknown. Nine records around t=75–115 seconds average 52.33 FPS before and 52.15 FPS after, a descriptive comparison
that establishes neither improvement nor regression. No build, running process or original report was modified.
Full methodology, patch-specific limits and next investigations: [session review](research/session-20261029-patches-30-35.md).

## Loading progress correction (2026-10-29)

The install log contained nested CMake dependency counters (`7/7`) followed by the real game build (`1/558`).
Those were incorrectly mapped to the same weighted stage, showing about 78% and then 37%. The pipeline now ignores
regeneration counters until the outer CMake build resumes; raw logs and build commands are unchanged. The overall
loading bar retains its highest valid weighted value and reaches 100% only on a successful pipeline exit.

Validation: 14 Python pipeline tests, the PowerShell pipeline suite (including mocked Build-Game output, no-op and
failure cases), and the actual LoadingScreen QML driven by fake signals pass. QML checks cover intermediate
property updates, stage transitions, revised totals, malformed counters, retries, failures, PGO and success.
The tests did not invoke a game build or modify/restart the installation already compiling in `Documents/test2`.
This is source-level validation; the previously delivered installer and the running launcher are unchanged.

## Patches 30–35 integration (2026-10-29, Xeon; synthetic checks)

Checkout: `C:/Users/dzvini/Documents/gow-claude/gow-native-pc`, with the supplied changes adapted as documented in
`docs/research/patches-30-35-integration.md`. Hardware: Xeon E5-2666 v3; the synthetic GS initialization reports an
RX 580 2048SP. Compiler: pinned llvm-mingw Clang 23.1.4. Regression build:
`C:/gow-build-c75e3561-verify-clang`, Release, x86-64-v2, ThinLTO off, object cache disabled.

- All patches through 35 replay from the pinned runtime commit and reproduce the runtime working tree exactly.
- `build.cmd -Stages verify -CompilerCache none` passes: Python and PowerShell pipeline regressions, synthetic ELF
  generation/synchronization, guest-call parity/diagnostic modes, 81 memory/DMA tests, 68 codegen tests and frame metrics.
- The separate VIF1 worker regression passes explicit enable/disable, asynchronous-FINISH fallback, per-instance
  configuration and the small-packet bypass, while preserving the count of two DMA submissions.
- VU1 generated DLL, inline x64, helper x64, forced SSE and no-speculation digests match for seeds 1, 4, 7, 11 and 23
  (one procedural image and three measured trials per seed, 24 programs per image). Special-value inputs also match
  with speculation enabled/disabled. Deterministic self-loops at 7 and 20,000 cycles match generated unchained code,
  generated chained code and both JIT tiers, including native-block counts (9 and 20,001 over three trials).
- A separate two-translation-unit executable and static library compile, link and run successfully with explicit
  ThinLTO, hidden visibility, the new math flags and lld's two-job limit. This is a toolchain smoke check, not a full
  game ThinLTO build or a build-time comparison.

Local evidence: `data/verify-patches-30-35-final.log`, `data/gow1/logs/vu1-equivalence/vu1-equiv-k06j7ngc/`, and
`data/thinlto-probe/`. This checkout has no prepared discs or generated EE game sources. Full game/launcher rebuild,
visible gameplay, sound, first-visit stalls and FPS are not validated for this series. No hardware support tier or
performance improvement is claimed.

## Branch review (2026-10-28, Xeon / RX 580)

`prototipo-claude` at `2e0f0cf`, plus the local review corrections below. Hardware: Xeon E5-2666 v3
(10 cores / 20 threads), 17,012,953,088 bytes of RAM, Radeon RX 580 2048SP, driver 31.0.21924.61.
The existing Maximum Performance power plan was read, not changed. This is separate from the laptop evidence.
The recorded build directory was absent; other available builds belonged to different checkouts. All game tests
here use the newly built `C:/gow-build-44a8e3b6-clang/ps2xRuntime/ps2EntryRunner.exe` and the prepared USA disc.

### Review corrections and checks

- Generated-file synchronization failed twice with Windows error 5 on different files. Bounded atomic-replacement
  retries resolve transient Windows denials while preserving targets and propagating persistent failures.
  All 14 Python pipeline regressions pass, including recovery/failure preservation.
- Windows tar could not extract the Qt XZ archives without an external `xz` executable. The pinned Python now
  streams XZ into a temporary plain tar. The PowerShell fixture and all three real Qt source extractions pass.
- The collector omitted real `[vu1n]` / `[vu1x]` rows from structured metrics. Both tags now parse; seven deployed
  collector integration tests pass, including the new assertions, redaction, export, crashes and parent exit.
- The implemented Saves page had no sidebar entry. Page 7 is now reachable and renders without QML errors.
  Previewing it did not create, import, delete or restore player saves.
- Runtime `verify` passes: 80 memory/DMA cases, 68 code-generator cases, guest-call/codegen scenarios, synthetic
  ELF generation, frame metrics and the PowerShell pipeline suite. The patch chain applies through 29f.
- AOT, JIT-only and forced-SSE4.1 JIT checks each reach gameplay, verify 2,000 runs without mismatches and exit 0
  without forced termination. Both JIT-only runs compile 623 blocks with zero unsupported blocks. These checks used
  intrusive diagnostics; the JIT-only checks overlapped Qt compilation and are not FPS benchmarks.
- Standalone startup using only the boot file passes gameplay/parity/exit checks and restores byte-identical boot
  contents. The real-game collector check passes all 11 assertions, including native/JIT metrics and marker export.
- Qt's 24 sorting compatibility cases pass. The deployed launcher starts with only Windows directories on PATH,
  recognizes the game as installed and exits 0 after its screenshot, with empty stderr. The deployed collector
  remains byte-identical to the binary that passed its integration tests after the sidebar rebuild.
- The real compiler-cache fixture hits with identical output, and replacing PGO data at the same path misses the
  cache and matches uncached compilation. This small fixture is not a game-build speedup measurement.

### Build observations

Clang 23.1.4, Release, existing PGO profile `54e4abaf0077464918e0e34425c4c03ce23542193331a72a22645eb27cdb33fa`,
ThinLTO off, seven parallel compilers and 9,480 existing VU1 images. New native analysis generates 1,897 blocks;
one unsupported block retains its fallback. No whole-game native-coverage claim is made.

| Operation | Seconds | Scope |
|---|---:|---|
| Real EE generation | 55.329 | 6,418 C++/header files; first attempt before the synchronization correction |
| Successful game compile/link | 1,041.542 | New build directory, existing PGO/native inputs; not a comparison against an older compiler |
| Successful recomp/sync/build invocation | 1,136.719 | Includes the post-fix EE generation and synchronization |
| Unchanged recomp/sync/build | 28.731 | Sum of successful stages before the independent Qt extraction failure; zero copied files or compilation |
| First launcher invocation with matching Qt | 2,559.033 | Includes source bootstrap of QtBase, QtShaderTools and QtDeclarative, launcher build and deployment |
| Incremental launcher/sidebar rebuild | 30.975 | Reuses the completed Qt SDK |

Unchanged EE hash validation takes 3.951 s; the unchanged Ninja game stage takes 1.359 s. Most remaining no-op time
is synchronization/hash I/O (18.061 s), a candidate for further profiling. Compilation-process working sets sampled
every five seconds peak at 4,108,992,512 bytes; sampled private bytes peak at 3,692,318,720. Sampling began during
the C++ stage, so this is not a guaranteed peak for the entire dependency/bootstrap pipeline.

### Visible/audio FPS comparison

Six 120-second runs, alternating lean/full order, fresh private-card paths, 60 seconds of warm-up per run,
1280x720 visible window, fixed 1x scale, 16:9, FXAA/VSync off, hardware GS worker and asynchronous FINISH.
Host cap: 120 Hz. Frame accounting/distributions and audio statistics are enabled; per-call timing, detailed VU1/IOP
counters, verification and captures are disabled. No compiler or build process is active during these runs.
Each run supplies eleven warmed five-second FPS windows and exits 0 without forced termination.

| Call mode | Run means (guest FPS) | Mean | Five-second range |
|---|---|---:|---|
| Lean (default) | 57.77 / 54.66 / 57.54 | 56.66 | 50.58–59.79 |
| Full dispatch reference | 58.36 / 57.24 / 58.18 | 57.93 | 53.37–59.99 |

The default mode is 2.19% lower in this observation. This does not demonstrate an FPS gain or establish a causal
regression: input follows real time, simulation progress differs, three runs provide limited repeatability, and
temperatures/clocks were not collected. The same executable's dispatch switch does not recreate main or the entire
older patch stack. **Stable 60 guest FPS is not achieved by this test.** All warmed audio windows have zero missing
or dropped samples; none of the warmed guest-frame intervals exceed 100 ms. These are guest intervals, not GPU or
display latency. There is no listening-test or whole-game audio certification.

Across the warmed windows, median p95/p99 guest intervals are 20.049/27.002 ms (lean) and 19.869/26.042 ms
(full). Worst intervals are 41.663 / 36.505 ms respectively. These are medians of individual five-second-window
percentiles, not a percentile computed from all raw frames in the session.

The local benchmark driver initially rejected the first run because its gameplay matcher expected adjacent fields;
the raw line contains `pending` and `stage` between them. Its matcher was corrected, the raw logs validated, and
the remaining runs resumed with unchanged settings/binary; the first measurements were retained.

### Remaining review findings and acceptance limits

- **Open: cross-instance save protection.** `Lanzador::jugando()` sees only its own `QProcess`. Closing the launcher
  leaves the game/collector alive, but a fresh launcher has no such process object. `restaurarPartida()` therefore
  does not reject that running game, and `iniciar()` can also start another instance. This violates the closed-game
  restore requirement. Add a reliable running-session/card guard before treating Saves as fully accepted. This is
  a source-review finding; no restore was attempted against a running player's card.
- A host back-buffer snapshot omitted the HUD in both a JIT run and an AOT control, while other internal/host
  snapshots show it. The captures are not the same guest frame and the omission is not isolated to JIT/AVX.
  HUD correctness/fade behavior remains an observation to investigate, not a confirmed new regression.
- No classic/locals frame-exact GS differential, Athens/heavy-area coverage, PT-BR movie check, 30-minute sustained
  session, installation/uninstallation registration or NVIDIA validation was performed. The roadmap gates remain open.

Local evidence (ignored): `data/gow1/logs/branch-review-20261028/` (settings, six session directories, FPS summary,
build-memory samples and launcher captures), `review-20261028-*.log`, `jit-hybrid-20261028-201103/`,
`jit-jit-20261028-203017/`, `jit-jit-20261028-203334/`, `standalone-20261028-204257/` and
`session-game-20261028-210121/`. Review changes remain local and uncommitted; no game-derived assets belong in Git.

## Next-phase memory gate and gameplay checks (2026-10-28, i5-8265U laptop)

Branch `claude/keen-dirac-42wd1y`, base `4283ea2` plus patches 29d–29f. Same prepared PT-BR disc, Intel UHD 620,
fixed 1x rendering, visible 1280x720 window, audio enabled, scripted ship sequence and a private card per run.
These are correctness/profiling checks, not a controlled before/after performance comparison.

- The old memory suite initially failed to compile against removed native-DMA APIs. Restoring compilation exposed
  20 failing cases out of 79. Migrating obsolete DMAC/CPU-rasterizer expectations preserved texture uploads and
  primitive state/vertices through the real texture store and backend boundary. Two actual bugs remained:
  scratchpad chain completion restored STR, and MMIO VIF/GIF submissions inflated the DMA counter.
- Patches 29e/29f correct those defects. The isolated memory suite now passes **80/80**, including both scratchpad
  directions, single completion, preserved mode, direct/empty/chained/MMIO counter paths and reinitialization.
  This is not a claim that the entire upstream `ps2x_tests` executable is repaired.
- `build.cmd -Stages fetch,verify,build` passes: the complete patch chain matches the working runtime, 11 Python
  pipeline tests plus PowerShell cases, synthetic ELF generation, ten guest-call scenarios, 68 codegen cases,
  frame metrics and the 80 memory cases. Incremental game build/link: **11.602 s**; whole pipeline: **54.848 s**.
  Existing dependencies/cache were reused; this is not a cold build or EE recompile measurement.
- Two 100-second visible gameplay runs (frames-only and intrusive timing) both reach `state=11, levelReady=1`,
  verify 2,000 VU1 executions with zero mismatches, export valid local reports and exit 0 without forced termination.
  Report checks also cover process memory, audio/IOP metrics and the player marker. No compiler ran during gameplay.

Frames-only run: over eleven complete five-second windows starting after 40 seconds, weighted guest frequency was
**23.36 Hz**, with window averages **16.58–27.96 Hz**. Window p95 was **54.227–91.896 ms**, p99 **65.053–166.130 ms**.
The 60 fps gate remains open. This visible/audio run cannot establish a regression or gain against the earlier
hidden/audio-off 42.90 Hz measurement. No listening assessment, image-parity comparison, thermal sensors or
three-run reproducibility are claimed. Frames-only audio windows collected after 40 seconds have zero missing or
dropped frames; startup did report missing frames.

The separate intrusive run averaged per five-second window: VU **4148 ms**, EE **2241 ms**, GS **2270 ms**, IOP
**917 ms**, guest wait **1850 ms** and host wait **4785 ms**. These are wall-time scopes on overlapping threads,
including scheduler waits, not additive CPU percentages or GPU timings. It also logged **11,822 missing audio
frames** after 40 seconds (zero dropped): detailed timing is not a transparent performance probe or an audio pass.
The smoke harness checks presence of audio metrics, not zero underruns. Reproduce this separately before attributing
the underrun to a particular subsystem.

Both runs report zero native VU1 misses in the sampled interval. In the frames-only run, self-loops account for
about **31.6% of native pairs** and **12.7% of native blocks**. Prioritize profiling VU1 execution/chain timing and
EE/VU1 synchronization (roadmap 34/35); a larger JIT coverage effort is not justified by this ship trace. Keep the
patch 30 address-boundary/MMIO differential gate and require repeated comparisons before enabling a new fast path.

Evidence under `data/gow1/logs/`: `phase-next-validation.log`, `pipeline-20261028-164743-172.json`,
`phase-next-summary.json`, and `session-game-20261028-164759` / `session-game-20261028-164946` (checks, raw logs,
metrics, session metadata and exported ZIP). Runner SHA-256:
`515a5bdbf91d6fdda3fee5f953d231d33119da8fdbc1d5ff49b3996ad738d682`.

## Session diagnostics validation (2026-10-28, i5-8265U laptop)

Patch 29c and the separate Clang/Qt `gow-session` collector add local player reports. This is instrumentation,
not a performance optimization. The existing ten guest-call scenarios and 68 codegen cases pass, alongside new
frame-window checks for nearest-rank percentiles, invalid values, budget boundaries, fixed-storage overflow and reset.
The full 01–29c patch chain applies and matches the runtime; game and launcher builds succeed.

Seven real child-process integration cases cover crash code `c0000005`, nonzero exit, failed startup, process metrics,
audio parsing, path/email redaction, exclusion of saves/ISO/environment secrets, markers, stop requests, bounded log
rotation, ZIP CRC/integrity, oversized-input rejection and collection after the launching parent exits. An initial
failed-start test exposed an exit-before-event-loop race in the collector; it is fixed and covered by the suite.

A 100 s prepared PT-BR gameplay run with sound enabled and a hidden window reaches `state=11`, `levelReady=1`;
2,000 VU1 comparisons report zero mismatches. The report contains guest interval distributions, process memory,
audio and IOP windows and the player marker. The stop request exits 0 without forced termination. Exported ZIP
contents validate independently. Evidence: `data/gow1/logs/session-game-20261028-161551/checks.json` and `report.zip`.
This is functional coverage, not a listening test, a visible-presentation certification or a controlled FPS comparison.

The Portuguese Other page renders the report export and marker controls; startup with only Windows system
directories on `PATH` exits 0 with empty stderr. Evidence: `data/gow1/logs/session-diagnostics-ui.png`.
Remaining measurement limits: collector overhead has not been quantified in paired game runs; actual GPU/display
presentation latency, GPU utilization/VRAM and temperatures are not collected. See [report semantics](reporting-bugs.md).

## Build foundation validation (2026-10-28, i5-8265U laptop)

Windows, Intel Core i5-8265U, 24 GB RAM, Intel UHD 620 / Radeon 520; pinned llvm-mingw 20261020 (Clang 23.1.4).
This is a different machine from the Xeon/RX 580 gameplay measurements below. The supplied PT-BR standalone
translation (ELF CRC `D95720D3`) was identified as compatible and prepared successfully.
The owner confirms that this laptop is less powerful than the earlier RX 580 desktop. Keep hardware baselines
separate: lower absolute FPS here does not establish a regression, and elapsed build times cannot be transferred
to the desktop. Compare changes on the same machine, driver, power plan, scene and settings.

- Eleven behavioral pipeline tests pass, plus PowerShell checks for configure reuse, PGO-content invalidation,
  profile paths with spaces, cache opt-out and recording environment restoration on success/failure.
- Real generation from a synthetic MIPS ELF passes in locals/classic modes; repeated inputs skip generation,
  forced identical output preserves timestamps and synchronization makes no unnecessary copies.
  The actual supplied ELF generated 6,418 C++/header files in 134.703 s (generation/publication timer).
- `build.cmd -Stages verify` builds and passes ten isolated guest-call scenarios and all 68 codegen cases.
  The pinned general memory suite still needs an independent repair of stale API references before patch 30.
- A real one-object cache fixture measured 5.302 s cold / 0.402 s warm (cold includes daemon startup), with an
  identical object hash and one cache hit. This is **not** a full-game compile-time or FPS measurement.
  A second fixture confirms same-path PGO replacement misses the cache; output matches an uncached control after
  normalizing COFF timestamps (two hits, three misses in the combined test, no unsupported/failed compilations).
- Clang-built installer: synthetic package round-trip verifies two files, one LZMS block, 357 unpacked bytes;
  imports are Windows system/UCRT DLLs, with no Visual C++ or libc++ runtime DLL requirement.
- Invalid stage and concurrent pipeline invocations return exit code 1 through `build.cmd`; PowerShell syntax
  parsing passes.
- Final `fetch,verify,launcher` validation passes with the complete 01–29b patch chain. The Clang Qt 6.8.3 SDK
  passes 24 sequence-sort compatibility cases. The deployed launcher starts and exits 0 with compiler/SDK paths
  removed from `PATH`, displays the prepared PT-BR disc and reports the game ready; stderr is empty.
  Fixed installation-time estimates were removed because duration depends on hardware and cached artifacts.
- The first real pipeline (`fetch,discs,configure,recomp,sync,build`) completed in 2,005.895 s; the game build/link
  stage took 1,625.804 s. After cleaning the runner target's 956 build outputs with Ninja, the same build/link
  stage completed in 31.344 s with the populated local object cache (98.1% less elapsed time). This compares a
  cold and warm object cache on the same Clang code/configuration, not Clang versus MSVC or a compiler speedup.
- A stable `recomp,sync,build` invocation with unchanged inputs completed in 9.369 s: 2.721 s recompiler stage,
  5.955 s synchronization, 0.272 s game build; no generated source was copied. The first cache-hit generation
  validation itself took 2.090 s versus 134.703 s for generation/publication. Fetch/disc preparation are excluded.
  Raw reports: `data/gow1/logs/foundation-{cold,stable-noop,cache-rebuild}-pipeline.json`.
- First-install gameplay smoke: 100 s, PT-BR disc, Intel UHD 620 / OpenGL 3.3 driver 27.20.100.9664, hidden
  1280x720 window, 2x dynamic resolution, audio off, no previously recorded AOT/IOP code. Gameplay reached;
  2,000 VU1 comparisons passed, 623 JIT blocks compiled with zero unsupported, process exited 0 without forced
  termination. The 80 s capture shows the ship, characters, textures and HUD. Eight diagnostic windows at
  t >= 60 s measured 11.91–20.79 guest FPS (median 15.49). This instrumented JIT-first smoke is not a controlled
  FPS comparison with prepared native code. Evidence: `data/gow1/logs/jit-hybrid-20261028-144139/`.

After recording 109 VU1 images and eight IOP modules, the same Release executable was measured with lean/full
call dispatch (`GOW_DISPATCH_FULL=0/1`). Settings: Intel UHD 620, fixed 1x internal scale, 1280x720 hidden window,
16:9, FXAA off, audio off, hardware GS worker, async FINISH, VU1 recording/background compilation off, frames-only
diagnostics, a GS screenshot at 80 s and the profile's pad script. Each run used a fresh private memory card; order was lean/full,
full/lean, lean/full. All six 120 s runs reached gameplay and exited 0. Eleven five-second windows per run start
after the 60 s warm-up. No compiler build ran during these measurements; the existing power plan was unchanged.

| Round | Lean mean guest FPS | Full mean guest FPS |
|---|---:|---:|
| 1 | 42.64 | 42.19 |
| 2 | 44.23 | 42.53 |
| 3 | 41.84 | 40.05 |
| Mean of runs | **42.90** | **41.59** |

The observed difference is +3.2%, with overlapping ranges and visible run-to-run variation. This is a narrow
same-binary comparison of call routing, **not main versus this branch**, not a statistically established general
speedup, and not a per-frame p95/p99 measurement. Real-time scripted input does not guarantee identical guest frames
at capture times, so screenshot equality is not asserted. Prepared native coverage shows zero misses/lane failures;
the inspected lean and full captures show the ship, characters, textures and HUD. Later levels, heavy combat outside
this scene, audio, AMD/NVIDIA and an actual main-branch build still require separate coverage.

Evidence: `data/gow1/logs/perf-20261028-145147/{summary,statistics}.json` and the six run folders. The report records
the runner SHA-256, settings, CPU, memory and power-plan identity; raw logs retain the graphics-driver information.

Standalone follow-up: a 100 s no-argument launch with diagnostics supplied only by the boot file reaches gameplay,
reports guest frames, verifies 2,000 VU1 runs with zero mismatches and exits 0. The test restores the original boot
file and uses a private card. This functional test ran while Qt was building; no performance result is inferred.
Evidence: `data/gow1/logs/standalone-20261028-150433/summary.json`.

Final delivery: `launcher,package,installer` exits 0. The updated launcher capture has no fixed installation-time
estimate and starts with only Windows system directories on `PATH` (exit 0, empty stderr). The generated setup's
1,456 files / six LZMS blocks / 96,256,472 unpacked bytes independently decompress and match the staging directory.
Setup SHA-256: `9e6acf2bb8328b1f928171c3b0c7e95718e5729aba578dc47ceddfa0f4d32cfe`.
Evidence: `data/gow1/logs/foundation-delivery.log`, `launcher-clang-install-final.png` and
`python -I tools/test/verify_setup.py data/_package/gow-native-pc-setup.exe data/_package/gow-native-pc`.
This verifies the payload, not Windows registration or uninstallation. This final verification record postdates
the documentation snapshot embedded in that package.

Implementation and remaining acceptance gates: [build foundation](research/build-foundation-2026-10-28.md).

## Gameplay measurements

Frame rates of the game itself (the in-game counter, `TOBIICHI_FPS_GOSTER=1` / launcher "FPS counter"), on the
Aegean Sea ship (first level, rain, several enemies) unless noted. The game never exceeds 60: its logic follows the
PS2's 60 Hz VBlank. **These are references, not guarantees**: drivers, power plans, background programs and other
areas of the game change the numbers. Add your own results with a pull request (same columns).

## Measured in this project

### Call-path review (2026-10-28, no gameplay measurement)

Intel Core i5-8265U, 24 GB RAM, Windows, llvm-mingw clang 23.1.4 Release, LTCG off. Patches 01–29 apply cleanly.
New regressions reproduce late diagnostic-setting and worker-trace-window failures; follow-up 29a fixes both.
Final call suite: ten isolated scenarios, 162 C++ checks plus trace-window assertion, all passing. Isolated upstream
CodeGenerator suite: 68/68 after 29b updates two stale DMA/timer expectations. Pipeline verifies the complete patch chain.
The full upstream test executable still cannot build because its memory tests reference removed APIs. No ISO/prepared
disc was available, so gameplay, frame hashes and FPS gains are unverified. See [review](research/patches-28-29-review.md)
for reproduction, local evidence and acceptance work before patch 30.

### Earlier gameplay measurements

**Machine A** — Intel Xeon E5-2666 v3 (10 cores / 20 threads, 2.9-3.5 GHz, Haswell), 16 GB RAM, AMD Radeon RX 580
2048SP (driver 26.1.1, OpenGL), Windows 10 Pro 22H2 (19045), power plan "Maximum Performance", 1280×720 window,
internal resolution 2× (dynamic), hardware renderer on.

| Code combination | Result | Notes |
|---|---|---|
| Waffle565 runtime, `runtime` + `switch` branches (2026-10-18) | **unplayable** | Title, menus and 3D black: textures sample black on this AMD OpenGL driver (`GOW_GPU_BISECT`: draws happen, "no texture" phase grey). Logic ran at 60 presents/s. |
| Tobiichi runtime (2026-10-16), Release without LTCG | 34 fps (1×, combat) – 42-45 fps (2×) | Image correct. CPU-bound (1× was not faster). |
| + IOP and VU1 native code (optimize stage, 856 micro-memories) | 42-45 fps | |
| + Waffle CPU speed-ups (`engine/patches/04`) | **59-60 fps**, window 120 Hz | EE thread ~3.1 s and VU1 ~3.5 s busy per 5 s: ~30 % headroom; scenes with more enemies dip (below). |
| same, scripted ship combat (3-4 enemies on screen, `optimize` pad script, t=75-125 s) | 44-50 fps | VU1 worker 3.8 s busy per 5 s: the limit. 28 VU1 block entries had no native code (`vu1n_heads.txt` not passed to the generator), ~1.2 M interpreter fallbacks per 5 s. |
| + `engine/patches/05`-`07` and the VU1 heads in the pipeline (2026-10-24) | **55-60 fps** in the same combat | Current configuration. 0 VU1 fallbacks; image checked against the previous build. |
| + `engine/patches/08` with `-Codegen locals` (now the pipeline's default, 2026-10-25) | 55-60 fps in the same combat | EE thread 3.0-3.4 -> 2.3-2.6 s busy per 5 s (about -22 %); the VU1 worker stays the limit, so the frame rate is the same here; more headroom on slower CPUs. Scripted run only (ship): boot, gameplay, image as before. |
| Launcher defaults (full screen 1920x1080, 16:9, FXAA, 2x dynamic, sound, continuous VU1 capture), 01-08 + locals | 44-52 fps in combat (average 47.6) | The continuous capture cost ~15 % of the VU1 worker (the frame's critical path: VU1 job ~13 ms + ~3 ms of EE work in series per frame). |
| + `engine/patches/09` (2026-10-25) | **53-60 fps** in combat (average 57.6) | 4:3 instead of 16:9: +1 fps; capture off: no difference. No launcher default needs changing. |
| + `engine/patches/10`-`11` (2026-10-25) | **56-60 fps** in combat (average 58.8, minimum 56.0, against 56.5 / 51.4 measured the same day without them) | VU1 worker 3.58 -> 3.46 s busy per 5 s; sound mixing ~14 % -> ~4 % of the game thread. Verified: GOW_VU1N_VERIFY 20,000 runs 0 mismatches, 11.8 M clean-operand checks 0 failures, GOW_SND_VERIFY 5.9 M frames identical. The frame's critical path is now the VU1 worker (job ~13 ms + ~3 ms of EE work in series). |
| + `engine/patches/12`, built with llvm-mingw 20261020 (clang, static, 2026-10-25) | 50-60 fps in combat (average 55.6) | Without patch 12 the clang build ran at ~2 fps in 3D (GS states never compared equal). EE thread faster than MSVC, VU1 worker slower. Full build ~15 min instead of 45-60. |
| same + PGO (profile from the scripted ship run) | **58-60 fps** in combat (average 59.4, minimum 57.9, against MSVC 58.0 / 53.1 the same day) | EE thread -27 %, GS -21 %, VU1 worker +8 % against MSVC. The profile comes from the same scene it was measured on; other areas not measured yet. |
| + Waffle GS draw-batching commits (00bda7f 09ea6cb 91ac954 c558c21) | game 62 fps, **window 0.2-2 Hz** | The GPU queue saturated on the RX 580 (SwapBuffers blocking); left out of patch 04. |
| Release **with** LTCG (`/GL /LTCG`) | link > 2.5 h, cancelled | MSVC 14.44; the pipeline builds without LTCG by default. |

Discs on machine A with the current configuration (clean build of this repository with `build.cmd`, 2026-10-24):

| Disc (`data/gow1/discs/`) | Result |
|---|---|
| USA + a PT-BR fan translation (full) | Portuguese menus and texts, 58-60 fps, window 120 Hz |
| PT-BR fan translation ISO only (standalone) | Portuguese title menu, gameplay reached, image correct |

Other findings on machine A: fullscreen start crashed (0xC0000005) until `engine/patches/03`; without `IOP_MOD/` the
game waited on the legal screen forever (handled by `tools/disc/prepare.py`).

## Local Windows JIT validation (2026-10-26)

Branch `prototipo-claude`, commit `30b007f` (same commit as `origin/claude/keen-dirac-42wd1y`), runtime patches 01-18.
Built on machine A with llvm-mingw clang 23.1.4, Release, existing PGO profile, LTCG off, and 9,501 captured VU1 images.
Executable: `C:\gow-build-44a8e3b6-clang\ps2xRuntime\ps2EntryRunner.exe`.

- Full game build and the three documented JIT test targets completed successfully on Windows.
- `gow_vu1_jit_aot_test - 2000` and `gow_vu1_jit_test x64 2000`: both exited 0; 4,000 cases, 22,000 native blocks,
  identical digest `7c9d4a139489ff09`. Both had the same 284 known edge-input differences from the exact engine.
- Transform microbenchmark: exact engine 18.448 us, JIT 1.838 us per run (10.0x); AOT 1.135 us in its separate run.
  These are synthetic timings, not a game frame-rate improvement.
- Fuzz: seeds 1-6, 4 images x 6 trials each, `x64` versus `x64-calls`: all exited 0 with matching digest and compiled
  block count per seed (242-262 compiled blocks). Inline compile time averaged 13.7-15.0 us per block.
- Game smoke test: 100 seconds, prepared USA disc, hardware renderer, hidden 1280x720 window, audio off,
  `GOW_VU1N_X64=1`, `GOW_VU1N_VERIFY=2000`, fast boot and scripted Start/X input. Gameplay reached
  (`state=11 levelReady=1`); 2,000 native checks, 0 mismatches; gameplay diagnostics showed `missBlocks=0` and
  `laneFails=0`. Host presentation rate at t=50-95 s was 59.72-59.92 Hz. The 80-second capture showed the ship,
  Kratos, enemies, textures and HUD. The process ended after WM_CLOSE without forced termination; the PowerShell
  process wrapper did not report an exit code, so no exit-code assertion is made for this run.
- **Coverage limit:** `[vu1x] compiled=0` throughout the game smoke test: existing AOT captures covered the scene.
  Actual JIT execution was validated by the synthetic tests; newly encountered game areas beyond the ship remain
  untested. This does not establish correctness or performance throughout the game.

Local evidence (generated, not committed): `data/gow1/logs/jit-smoke-20261026-164716/`, `jit-aot-test.log`,
`jit-x64-test.log`, `jit-fuzz-<seed>-<mode>.log`, `jit-test-build.log` and `build.log` in `data/gow1/logs/`.

## Incremental build and JIT delivery (2026-10-26)

Machine A, runtime patches 01-23, clang Release with existing PGO and LTCG off; rebuilt game and Qt 6.8.3 launcher.
v2.0.0 is already an ancestor of the working branch. Full details and reproduction commands:
[JIT delivery report](research/jit-delivery-2026-10-26.md).

- Disc scan: 956 files, 6 usable images, 470 blocks; 112.088 s cold, 0.420 s cached. This is partial disc coverage.
- Native analysis: 9,480 images; 143.103 s cold, 15.154 s cached, six generated C++ files and timestamps unchanged.
- Final x64/AOT digest and six inline/helper fuzz seeds matched. The 284 documented synthetic edge-input differences
  from the exact engine remain; the new patches do not change arithmetic.
- Two 100 s real-game checks (JIT-only and normal hybrid): gameplay reached, 2,000 comparisons with zero mismatches,
  exit code 0, no forced termination. JIT-only compiled 619 blocks with zero unsupported, 16.4 us average compilation.
  Guest FPS at t=40-95 s: JIT-only 15.40-33.35, median 28.40; hybrid 32.95-59.58, median 56.55. Different simulation
  progress prevents a controlled same-frame comparison. The host's ~120 Hz is not the game frame rate.
- The ship capture showed characters, textures and HUD. Later levels and NVIDIA were not tested in this delivery.
- Final setup: 61,673,468 bytes; all 1,417 files matched staging after independent LZMS decompression (8 blocks,
  128,323,300 unpacked bytes). Setup preview exited 0 with empty stderr; launcher binaries in development and staging
  have identical SHA-256. This validates packaging/startup, not Windows install/uninstall registration end to end.
  Installer SHA-256: `95f951e5bb25ecda4db3551d33807e495f017435be3ff9d39a38a4602fdb3632`.
  This artifact checksum was recorded after packaging; the copy of this document inside that artifact predates it.

## Audio/direct-launch follow-up (2026-10-26)

Same local RX 580 machine and clang build, 2x OpenGL. Patch 24's deterministic multi-voice mixer regression fails
before the correction and passes in batch/per-frame/verification modes afterward. Original and PT-BR translated
disc runs, 100 seconds each with audio, reach opening combat and verify 2,000 VU1 runs with zero mismatches.
Both exit normally; after startup, 17 five-second windows each have zero missing/dropped output samples.
The hatch and sailor scene have not been reproduced; this is not an all-audio-bugs-fixed claim.
See [audio investigation and compatibility plan](research/audio-standalone-mods-2026-10-26.md).

## Worker synchronization and task replay (2026-10-29)

Original checkout `C:\Users\dzvini\Documents\gow-claude\gow-native-pc`, Xeon E5-2666 v3, RX 580 2048SP,
Windows 10 22H2, approximately 16 GiB RAM. Fresh Release runner with patches 01–37, Clang 23.1.4,
portable x86-64-v2, ThinLTO off, no PGO or captured VU1 AOT corpus. JIT enabled. The USA disc was prepared into
this checkout; no other installation or player card was modified.

Runner SHA-256: `e820daccd23900ddbccad3c28239c57d0d9782c75d4456d7d7a8aec78a518233`.
ELF SHA-256: `ec9397d252f14d4412daffaad6be1f1931769e56222b5dbb9b39a947fc8ad71c`.

Six 90-second visible runs with audio enabled, fixed 1280×720 window, internal scale 1, dynamic scale/FXAA/VSync off,
60 Hz host cap, profile-supplied scripted input and a new private card per run. Each average uses nine complete
five-second windows after 40 seconds of warm-up. Detailed timing and capture were disabled in this comparison.

| Order | Large-VIF1 barrier | Guest FPS | Median of window p95 intervals (ms) |
| --- | --- | --- | --- |
| 1 | On | 46.36 | 23.99 |
| 2 | Off | 43.81 | 24.94 |
| 3 | Off | 44.98 | 24.99 |
| 4 | On | 42.18 | 29.15 |
| 5 | On | 40.58 | 28.18 |
| 6 | Off | 40.56 | 29.11 |

Mean of the three runs: **43.04 FPS on, 43.11 FPS off** (off/on difference approximately +0.18%).
This does not establish a useful barrier speedup or regression: run variation is much larger, and real-time inputs
do not ensure identical simulation/scene trajectories. The existing default remains unchanged. This compares
patch 33's setting within one new binary, **not** patches 36–37 against an older binary. It cannot be compared
directly with the user's earlier 2× dynamic-resolution session. Stable 60 guest FPS is not achieved.

All six runs reached `state=11 levelReady=1`, exited 0 and stopped gracefully through their own collector.
Audio-device initialization succeeded. No post-warm-up interval exceeded 100 ms in the recorded windows; this does
not erase startup stalls or prove later-scene pacing. Evidence: `data/gow1/logs/worker-ab-fps-20261029/summary.json`.

Full `verify` passed: pipeline, guest calls, 81 memory tests, 68 codegen tests, frame metrics, worker/stage waits
and VU1 differential cases. Focused replay tests passed again after the final timing refinements, including an
XGKICK fixture, capture noninterference, all five replay modes, invalid input, overwrite refusal and deliberate
baseline mismatch. The deployed collector passed all eight tests. Game and Qt launcher builds completed.
Contracts and reproduction: [worker waits and task replay](research/worker-sync-task-replay.md).

Two separate 90-second detailed runs also reached gameplay and exited 0. With the barrier on, its 3,817 calls
observed zero busy worker/stage waits; aggregate overhead was 0.482 ms worker-side and 0.390 ms stage-side across
the whole session. MMIO aggregates observed one worker wait and two stage waits in each setting, under 5 ms combined
per session. These measured sites are not the dominant waits in this route; they do not cover every guest scheduler
or presentation wait. Post-warm-up five-second windows averaged 3,791/3,805 ms in the VU scope (on/off),
1,638/1,574 ms EE and 2,276/1,968 ms GS. Scopes can overlap across threads and include instrumentation overhead;
do not sum them into a frame budget. Both runs ended with 623 compiled JIT blocks, zero unsupported blocks and
zero reported native misses. Early diagnostic windows recorded up to two lane-check failures, which use the existing
despeculation/fallback path; final windows had zero. Post-warm-up audio windows reported zero missing/dropped samples;
audible quality was not independently assessed. Evidence: `data/gow1/logs/worker-ab-timing-20261029/`.

The separate 100-second capture run recorded 128 fresh MSCAL tasks (4,284,416 bytes), stride 256 after a 40-second
delay, spanning approximately 44.2–45.0 seconds of collector time. It exited 0 without forced termination.
The game-rendered 50-second image showed ship combat, Kratos, enemies, textures and HUD. The corpus contains
78 microcode hashes and entry PCs 0, 24 and 48; it is a short local sample, not whole-level coverage.

All 128 tasks matched their corresponding captured baseline in hybrid, JIT, helper, SSE and exact replay, with
five warm repetitions after the first execution. Every sample used native blocks in the four native modes.
All 128 native baselines differ from their exact baselines: this validates repeatability within each backend,
**not** native/exact bit equivalence. Existing procedural differential checks remain a separate gate.
This build has no captured AOT corpus, so hybrid replay primarily exercises JIT, not a new AOT coverage claim.

Median of per-task warm execution medians: hybrid 9.50 us, JIT 9.00 us, helper 22.70 us, SSE 9.45 us, exact
180.40 us. These isolated timings exclude input reconstruction, hashing and final pipeline flush; they are not
FPS gains or an unbiased workload profile. The slowest JIT sample was record 1, PC 24, code hash
`0449e3d7d30cee7d`, 217.4 us warm and 6,205 native blocks. The corpus/ranking is a starting point for investigating
that task, not enough evidence to replace its algorithm. No hand-written native task replacement is enabled.
Evidence: `data/gow1/logs/worker-task-capture-20261029/` and `worker-task-replay-20261029/summary.json`.
Captures remain local and excluded from exports. All 43 runtime patches reproduced 66 patched files from the
pinned tree using a temporary index; the developer's runtime index was unchanged.

## Reported by the projects this builds on (not re-tested here)

| Machine | Code | Reported result | Source |
|---|---|---|---|
| NVIDIA RTX 4050 Laptop (Linux) | Tobiichi | 2× 60 fps (GPU 49 %), 3× 47-57 fps, 1× 60 fps (ship deck) | Tobiichi-Port docs/ESTADO.md |
| AMD Radeon 680M (integrated, Linux, Mesa) | Tobiichi | 1×-2×; ship combat at 1×: 50-60 fps with the performance power profile, lower on battery | Tobiichi-Port README |
| AMD Radeon RX 5700 XT | Tobiichi (GPU renderer) | OpenGL 4.6 renderer verified (no frame rate given) | Tobiichi-Port docs/ESTADO.md |
| Dedicated NVIDIA/AMD (general) | Tobiichi | 2×-3× at 60 fps "typical" | Tobiichi-Port README |
| Waffle565's PC | Waffle runtime + switch | zones 0-4 at 60 fps | God-Of-War-Native-Port docs/status.md |
| Nintendo Switch (Cortex-A57) | Waffle `switch` branch | title menu 25 fps, gameplay 9-12 fps | God-Of-War-Native-Port docs/status.md |
| Ship, KIexster's stack | KIexster | median ~53-56 game frames/s with the camera still (in progress) | god-of-war-recomp README |

## What usually limits the frame rate

- **CPU (most machines)**: the game thread (EE) and the vector unit (VU1) — single-thread speed matters most. The
  optimize stage and "Speed up visited areas" turn recorded VU1/IOP code native; areas never visited still run the
  VU1 interpreter (slower) until their code is recorded and compiled.
- **GPU**: internal resolution (each step costs its square); dynamic resolution lowers it when the GPU falls behind.
- **Power plan / laptops**: "power saver" or battery lowers the CPU clock and the frame rate.

### Follow-up artifact validation

The updated setup is 61,683,346 bytes, SHA-256
`7300d6ffd55c5bfbd8275839c6025ceae63b765980d23eae46b234d9bbcd69f1`.
Independent decompression verified all 1,421 staged files, 8 LZMS blocks, 128,355,429 unpacked bytes.
No installation/uninstallation registration test was performed on the player's existing install.
Standalone no-argument boot reached gameplay in a 100-second test with 2,000 VU1 checks / zero mismatches and exit 0.
The 300-second empty load screen had zero missing/dropped samples after startup, 54.17-58.99 guest FPS after 20 s;
this does not validate a populated save list. The final artifact checksum and standalone result were recorded after
packaging; the embedded documentation predates those final result lines.

## Cutscene audio investigation (2026-10-26, RX 580)

Same installed clang runner and private card copies, 180 seconds per disc, new game then ATHN01D warp. A01MP02
plays in both runs, graceful exit 0, no guest branch errors. PT-BR reproduces periodic PCM channel-block corruption
before output resampling; original control matches the identical source audio at gain 0.999764 and residual RMS
1.17 (source second 4). PT-BR residual is 2244.99, with 16,813 of 46,822 distinct-channel samples matching the wrong
channel. No runtime fix is claimed. The player's card remains byte-identical to its backup.
See [reproduction evidence and correction plan](research/cutscene-audio-2026-10-26.md).

## PGO, CPU target and patch 38 (2026-10-30, Xeon E5-2666 v3 / RX 580 2048SP)

Checkout `Documents/gow/gow-native-pc`, patches 01–38, clang 23.1.4 Release, AOT VU1 from the optimize stage, JIT on.
Scripted ship route (profile pad script), private card, visible 1280×720 window, internal scale 2, audio on, 60 Hz
cap, frames-only diagnostics. Each value is the mean of guest-FPS windows at t=25–100 s of one 105-second run; the
"dip" is the combat windows at t≈30–50 s. Runs alternate between the two builds within one session: run-to-run noise
is about ±3 FPS and the level drifts between sessions, so only alternating pairs are compared.

| Comparison (alternating pairs) | Mean FPS | Dip FPS | Result |
| --- | --- | --- | --- |
| Patch 38 vs 01–37 (2 pairs) | 54.71, 52.36 vs 55.07, 52.78 | 46.09, 41.69 vs 44.96, 42.13 | neutral |
| PGO vs no PGO, portable (3 pairs) | 54.96 vs 52.51 | 45.60 vs 40.20 | +4.7% / +13.4%, all pairs |
| PGO x86-64-v3 vs PGO portable (3 pairs) | 52.11 vs 52.91 | 40.49 vs 43.42 | no gain; portable kept |

All runs reached gameplay. A first non-alternating three-run baseline (51.52) wrongly suggested a patch 38 gain.
Sampling profile (PDB build, same route): the EE thread waits ~57%; the VIF1/VU1 worker is ~78% busy, of which
`VU1NativeAccess::chain` is 19.6%, `blockTiming` 3.5%, slot setup/code-change checks ~3%, GS-stage locking ~5% and
interpreter call-outs (OPMULA/OPMSUB/EFU) ~3.5%. Stable 60 guest FPS is not reached; the worst combat window with PGO
averages ~45 FPS. Analysis and next steps: `docs/research/revisao-2026-10-30.pt-BR.md`, section 6.

Patch 39 (same machine and protocol, FXAA on with the sharp scaler, two alternating pairs): 52.99 / 54.97 FPS against
54.88 / 50.95 for the patch 38 PGO build: no measurable change. In-game screenshots confirmed the F1 menu (pt) and a
borderless 1920×1080 window with FXAA followed by the sharp scaler, correctly oriented.

## Early FINISH, patch 40 (2026-10-30, Xeon E5-2666 v3 / RX 580 2048SP)

Same executable with GOW_GS_EARLY_FINISH=1 and =0, alternating runs, scale 2, audio on, PGO build (profile trained
before patch 40). Ship route from a new game, 1280×720 window, 3 pairs: mean 57.80 vs 54.63 FPS (+5.8%), combat
windows 52.22 vs 43.45 FPS (+20%). Route from the player's own save (copy of the native port's memory card, later on
the ship deck), exclusive full screen 1920×1080 with the FPS counter, 3 pairs: mean 51.52 vs 42.82 FPS (+20%), worst
window 42.9 vs 35.9; one of the three pairs was reversed (47.5 vs 49.1), route variance. Four in-game window captures in
heavy combat were correct. Batching the worker's GS-stage pushes (64 KiB) measured slower in 3/3 full-screen pairs
(53.8 vs 57.1 mean) and was dropped. Stable 60 guest FPS is still not reached in combat.

## Regional gameplay (2026-11-02, Xeon E5-2666 v3 / RX 580 2048SP, 16 GB)

Separate Europe SCES_531.33 and Japan SLPM_670.10 Release builds passed the
11-check session smoke with private cards: 100 seconds with fast boot and
150 seconds with normal startup/FMVs for each region. GS captures confirmed
ship gameplay. VU1 verification reported 2000 checks with zero mismatches;
audio and IOP metrics were present. Japan requires Circle at its menus.
Original Asia/USA runner and installation metadata hashes remained unchanged.
These are functional checks, not a 60 FPS result or whole-campaign validation.
See [regional evidence and limitations](research/regional-port-2026-11-02.md).

Follow-up launcher audit: both regional runners also passed 100-second private-card
ship tests at 2x with FXAA and early FINISH enabled; screenshots showed scenery,
characters and HUD. Asia/USA passed its repeat with longer menu-confirm holds.
The original runner hash and sampled disc assets remained unchanged. No controlled
before/after FPS comparison was performed; these results do not establish equal
performance between the unprofiled regional builds and the USA PGO build.

## Experimental WSL Linux build (2026-11-02)

An isolated Ubuntu 26.04.1 WSL2 checkout built the native x86-64 launcher,
diagnostic helper and USA-compatible game with Clang 21.1.8, Qt 6.10.2 and
two compiler jobs (7.7 GiB available to the VM). No Windows build, card or
regional registration was reused. The Linux preparation now supplies lowercase
IOP module aliases: the first launch exposed missing `IOP_MOD/*.irx` on the
case-sensitive filesystem despite a successful compilation.

After that fix, the scripted private-card run reached ship gameplay
(`state=11 levelReady=1`); the 80-second GS capture showed the ship and Kratos.
Audio/IOP/frame metrics were present, and the session's VU1 verifier completed
2000 checks without mismatches. WSLg used llvmpipe software rendering, with
very low guest FPS; this is not a playable-performance result. A temporary
D3D12 driver probe identified the RX 580 but exposed OpenGL 4.2, below the
renderer shaders' 4.3 requirement. No driver-version override was used.
The final session passed all 11 smoke checks, including exit code zero after a
normal close event sent to the test-owned game window. The first close attempt
targeted a hidden GS context instead; its subsequent SIGTERM was not counted as
a successful exit. No player card was used in either run.

Validation also passed 17 generation tests, 7 Linux pipeline tests, 14 real
synthetic CHD tests, 2 disc-normalization tests, 4 regional-registration tests,
the import/region/loading QML suites, language checks, 8 Linux diagnostic tests
and all 10 native CTest suites. VU1 differential tests matched generated modules,
x64 inline/helper/SSE paths and deterministic self-loop exits for all five seeds.
The diagnostic suite and import QML also passed on Windows. The Linux input test
needed the fake host's `IsWindowReady` stub; production runtime code was unchanged.

Steam Deck hardware, Steam Input/reconnects, audible output, suspend/resume,
Gaming Mode, regional Linux game builds and Mesa/NVIDIA GPU gameplay remain
unvalidated. The launcher archive uses its build host's libraries, not a portable
Steam Linux Runtime baseline. See [Linux instructions](linux.md).

## GS queue instrumentation (2026-11-03, Xeon E5-2666 v3 / RX 580 2048SP)

Patch 59 was built separately at `C:/gow-q59-clang` with Release `-O3`,
portable x86-64-v2, PDBs and the existing local PGO profile (not retrained).
The executable SHA-256 is
`ffd4e85d3f40a3395da46aec4ef0618c9b43401894fd98efd6aa3b33f92b83df`.
Local evidence and build provenance are under `data/experiments/queue59/`.

The complete `verify` stage passed, including all ten native CTest suites,
VU1 differential checks and task replay. The new forced-capacity backend test
verified producer blocking, wakeup, payload contents and packet order. Eight
collector tests passed against the deployed helper. A separate 100-second visible
private-card smoke run passed all eleven checks, including gameplay, audio metrics,
2000 VU1 comparisons without mismatches and graceful shutdown. The 80-second
capture showed ship gameplay. Audible output was not independently checked.

Two 105-second detailed runs compared the stage's existing 50-us idle spin with
immediate sleep. Both used scale 1, GS early FINISH, no large-VIF barrier and
private new-game cards. Whole-session queue capacity waits were:

| Stage idle spin | VU1-to-GS ring total / longest wait | Backend total / longest wait |
| --- | --- | --- |
| 50 us | 0.591 ms / 0.170 ms | 3416.076 ms / 4.818 ms |
| 0 us | 13.254 ms / 3.653 ms | 3513.929 ms / 8.024 ms |

These elapsed waits overlap other work; they are not GPU time or directly
recoverable frame time. The ring was not a substantial capacity bottleneck on
this route. Backend counters also showed no texture decodes in the final warm
windows, which does not establish texture behavior in other scenes. Renderer
`batches` are not GL draw-call counts: shadow-volume and alpha-fail paths can
issue several draws per batch. Profile these paths before changing their semantics.

The separate FPS experiment completed three alternating pairs of 105-second runs,
discarding complete windows that overlapped the first 25 seconds. Detailed timing
and captures were disabled; each run supplied 15 complete FPS windows (about 75 s).
All six runs passed gameplay, effective-setting and graceful-exit checks.

| Pair | Existing 50-us spin, guest FPS | Immediate sleep, guest FPS | Sleep change |
| --- | --- | --- | --- |
| 1 | 56.719 | 56.013 | -1.24% |
| 2 (reverse order) | 58.772 | 59.038 | +0.45% |
| 3 | 58.972 | 55.467 | -5.94% |
| Mean of runs | 58.154 | 56.839 | -2.26% |

The lowest five-second windows were 47.2 FPS with spin and 46.0 FPS with sleep;
neither achieved stable 60 FPS. Median window p95 frame intervals ranged from
16.849 to 17.570 ms with spin and 17.372 to 19.535 ms with sleep. No measured
interval exceeded 100 ms. CPU samples from 30–100 s averaged 416.7% versus 422.5%
of one logical CPU (spin versus sleep), with inconsistent pairwise changes;
there is no demonstrated CPU saving. These are process CPU samples, not power
measurements. Keep the 50-us default: immediate sleep did not demonstrate a gain.
The comparison uses the same patched binary, not pre/post-patch binaries.
Detailed evidence: `fps/summary.json` and `fps-analysis.json` under the local
experiment directory.

This is the scripted opening ship route, not a reproduction of the historical
28-minute scene. Real-time inputs do not guarantee identical guest-frame scene
alignment. The i3-10110U and weaker hardware were not available for new runs;
these results establish neither their performance nor a stable-60-FPS tier.

## Rejected shuffle scratch experiment (2026-11-03, Xeon E5-2666 v3 / RX 580 2048SP)

An experimental patch reused four temporary geometry vectors in `tryShuffle`, clearing all
four before each mapping attempt. Partial geometry from a rejected sprite never
enters the queued pass. Shader code, geometry calculations and draw ordering are
unchanged. Storage is owned by the backend and retains its high-water capacity
until destruction; it is not a cache keyed by game content.

A separate 30-second sampling run showed `tryShuffle` in 7.22% of GSThread
samples, with VU1 chaining also prominent (29.51% on its worker). Sampling includes
waiting threads and is intrusive: these are not whole-frame cost percentages.
Local evidence is in `data/experiments/gs60/profile.txt`.

The synthetic test compiles the actual renderer source and calls its geometry
builder without a GL context. It repeats 100,000 valid sprites interleaved with
14,286 failures after partial mapping, hashing queued geometry. Both revisions
produced `6b52eb0da9289d43`; warm allocations fell from 428,572 to zero. Five
alternating pairs of the final layout gave median 143.381 ms before and 110.191 ms after (23.15% less
elapsed time, including output hashing). This is a synthetic routine result,
not a gameplay FPS improvement or GPU rasterization check. The local
`gs_shuffle_scratch.cpp` regression requires the reference digest and zero warm
allocations, but deliberately has no timing threshold.

The experiment used `C:/gow-q59-clang`; its pre-change executable is
preserved under `data/experiments/gs60/baseline`. Both builds retain the same
portable CPU target and existing PGO profile. The candidate passed the visible
100-second private-card smoke test, including 2000 VU1 checks without mismatches;
the 80-second capture showed ship gameplay with HUD. Audio metrics were present,
but audible output was not independently checked.

The initial placement of scratch storage before hot renderer fields measured
58.413 versus 59.008 mean guest FPS in three alternating pairs (candidate versus
baseline). A second variant instead appended storage after all existing members,
preserving their offsets. This controls a layout difference; it does not establish
cache layout as the cause of the initial result. The initial evidence is retained
in `data/experiments/gs60/fps`, with final-layout measurements kept separately.

The second series (`fps-layout`) did not complete: its fourth run lost complete
`gow-perf` windows and needed forced termination, while `gow-frame` continued.
Its incomplete averages must not be used as performance evidence. The cause was
not established. Neither variant demonstrated a gameplay improvement, so the
renderer change and its native test target were removed from the production
patch chain. Source variants, the experimental patch, binaries and the test
fixture remain local under `data/experiments/gs60`; the baseline renderer was
restored. Do not ship or advertise the synthetic speedup as a game FPS gain.

The `verify` command stopped twice at a synthetic ELF test with Windows access
denied while renaming temporary output under `data/_tmp`. That test passed
separately using the normal Windows temporary directory. The remaining checks
were run explicitly: native suites, guest calls, VU1 equivalence/task replay and
language checks passed. The final-layout native build passed all eleven CTest
suites including the new geometry/allocation regression; 17 pipeline tests and
the A/B methodology checks also passed. Do not describe the interrupted aggregate
`verify` invocations as successful.

## Rejected VU1 branch-hint experiment (2026-11-03, same Xeon)

The sampled route reported approximately 11–12% self blocks. Removing the
`[[likely]]` annotation on `chain`'s self-loop branch changed the unprofiled
machine-code layout, placing the ordinary successor path nearer the entry.
No VU1 arithmetic, timing or dispatch conditions were changed.

A private-card capture with the baseline runner completed normally and recorded
128 real MSCAL tasks. All JIT replays matched their captured native baseline;
all 128 tasks used native blocks. Native and exact baseline digests differed on
all 128 tasks, so this is backend-preserving parity, not exact/native equivalence.
The first unpinned comparison suggested a small benefit, but five alternating
pairs pinned to the same logical CPU after a warm-up pair did not confirm it.
Summed per-record warm medians (100 repetitions per task) were:

| Pair | Original hint (us) | Hint removed (us) |
| --- | --- | --- |
| 1 | 2105.5 | 2063.0 |
| 2 | 2174.1 | 2194.1 |
| 3 | 2169.7 | 2435.5 |
| 4 | 2076.9 | 2081.9 |
| 5 | 2028.2 | 2055.4 |

The candidate lost four of five pairs and was reverted before any game build was
made from it. These isolated execution costs exclude reconstruction/hashing/final
flush and are not FPS. Affinity mask 4 controlled scheduling for this test only;
it does not simulate notebook hardware. Logs, assembly and results are local in
`data/experiments/vu60`, and the captured corpus stays under ignored `data/`.
Neither this candidate nor the shuffle experiment is in the runtime patch chain.

## Build time and the tune stage (2026-10-30, Xeon E5-2666 v3, 20 threads, 16 GB)

The following measurements are historical. The v0.5.0 release packaging did not
repeat a controlled whole-installation timing or full-campaign FPS benchmark.
Patch 55 separately measured a native IOP compile unit shrinking from 126.5 s
to a longest parallel part of 24.5 s on the Xeon; do not report that ratio as
the speedup of a complete installation.

Compiler jobs now one per 1.0 GB above 4 GB (11 here; measured 0.5 GB average, 0.64 GB peak per compiler); patch 41
builds register_functions.cpp alone at -O1 (331 s -> 9.8 s). Stage tune (instrumented build, one recorded run for VU1
code and profile, final build): 24.1 min against about 63 min for the former build, optimize and pgo sequence. Save
route, full screen, 3 alternating pairs: tune build 54.81 vs traditional PGO build 52.51 FPS. A -O1 training build was
slower (45.0 vs 49.7, 3/3) and is not used. PGO retrained with early FINISH: neutral (51.9 vs 52.2). Intro movies with
early FINISH: gameplay reached, no errors. 30-minute session from the save: 48.1 FPS mean after loading, 3 windows over
100 ms (max 309 ms), memory stable over the last 8 minutes.


## 2026-11-04: CPU/GPU scene-isolation follow-up

Same i5-8265U / Intel UHD 620 notebook, private blank cards, audio enabled, hidden
sessions. The new state/zone/position gate rejected the combat comparisons; do not
report their FPS deltas as an optimization result. A rejected short run combined
99.13% mean total-system CPU with 43.36% game GPU busy time, so GPU saturation alone
does not explain every slowdown. No clocks/thermals attribution or RX 580 result.

A separate intrusive 20-second profile measured GameThread CPU 61.80%, VU1 worker
46.57%, GSThread 38.32% and GS-stage 34.16%, each relative to one logical CPU.
The sampler now takes CPU end times before symbol resolution and retains module
RVAs without a PDB. RIP sample percentages still include waits and are not CPU
self-time. VU1 chaining, GS vertex conversion/view mapping, command parsing and EE
FINISH waiting are concrete follow-up targets.

Patch 68 is an opt-in countdown candidate, with 560 isolated equivalence cases;
patch 69 removes the disabled GS dump's per-draw clock read. Neither establishes a
measured gameplay FPS gain or resolved audible glitches. Original save/card inputs
were never used as writable test roots. See [method and local evidence](research/render-delivery-2026-11-04/scene-bottlenecks.md).

Final `fetch,build,verify` passed (12 CTest groups plus codegen/VU1/procedural replay).
Two bounded diagnostic sessions reached gameplay and exited cleanly; both recorded
32 VU1 tasks with private cards. Replay of one identical corpus passed on all five
backends against their own baselines (native/exact differ in all 32 records).
These are CPU isolation inputs, not a valid FPS comparison or audio-quality gate.
Final runner SHA-256: `6476be39ceb5ef33e5f0594fc0c44cb01dedd41f4bb9d02c239579913b34da35`.

## 2026-11-05: scalar replay repetition

The maintainer resumed testing on the i5-8265U. Five alternating pairs reproduced
lower isolated scalar-candidate replay cost: 490.9 -> 468.2 us (-4.62%). All five
backend replays passed their own captured baselines. No production optimization
was installed; combat, audio and full equivalence acceptance remain open.
See [reproduction and limits](research/render-delivery-2026-11-04/scalar-repeat-2026-11-05.md).

Patch 72 follow-up: Release and full verify passed. Visible 100-second candidate gameplay passed 2000 VU1 comparisons and graceful exit, but smoke failed native/JIT metric checks (9/11). Both A/B attempts were rejected before candidate comparison. No FPS improvement established.

# Private diagnostic kit — 2026-11-03

Built the isolated `gow-diagnostics` frontend and `gow-session` with pinned LLVM/Qt.
Packaged the preserved queue-59 runner (`ffd4e85d3f40a3395da46aec4ef0618c9b43401894fd98efd6aa3b33f92b83df`),
without the rejected GS/VU1 experiments. Installer: `data/_package/diagnostic-kit-20261103-final/setup.exe`.
All 1,356 payload members matched staging; a separate silent installation matched every member and opened
the dedicated UI. Ten collector tests, 17 pipeline tests and launcher language checks passed.
The detailed scripted session reached `state=11 levelReady=1`, produced a visually inspected gameplay
capture, completed with exit 0 and exported its summary/metrics. The installed light mode also launched
the game and recorded frame windows; it was stopped early to deliver the kit to the user.
These are functional checks on the Xeon/RX 580, not notebook performance acceptance or an FPS gain.
No new optimization is adopted. Notebook diagnostics and reproduction of the 28-minute scene are pending.

## Shared presentation contention — 2026-11-03 (GPU-02)

Read-only LK report (`E:/doc/lk`): Ryzen 5 5500 / RX7600, launcher 0.4.0,
patches through 55, 2x/FXAA on/VSync off. Late-session guest windows averaged
56.22 FPS while host stayed 59.91 Hz. No GPU-utilization, queue or input-latency
measurements; this is not the RX5500 XT / 0.5.0 report and does not identify a cause.

Patch 61 removes an unconditional host wait on the shared-image publisher mutex.
The production-code synthetic test failed on the old implementation (2.007 s)
and passed on the candidate. Full verify passed. Xeon/RX580 alternating comparison
(3 pairs, 100 s each, 40 s warmup, 2x, FXAA off): 59.05 -> 59.40 guest FPS,
2/3 pairs positive; small variable difference, not a confirmed general FPS gain.
Retained for the demonstrated lock-stall fix; no stable 60 or physical input-lag
claim. See [GPU-02](research/shared-present-input-2026-11-03.md) for hashes,
pacing, route/settings, limits and artifact paths. RX7600/RX5500 XT/NVIDIA and
notebook gameplay validation are pending. Real AMD FSR remains a documented
proposal (GPU-03); the existing scaler is bicubic plus sharpening.

The separate visible 100-second 2x/FXAA-on smoke passed all 11 checks, with
2000 VU1 parity runs (zero differences), audio/IOP metrics and graceful report
export. The 80-second GS capture was visually inspected (ship combat and HUD).
Artifact: `data/gow1/logs/session-game-20261103-215811`. This is functional
coverage, not a default-FXAA performance comparison or physical latency test.

Packaged 100-second light game smoke also reached `state=11 levelReady=1`,
recorded the candidate runner hash and exited zero without forced termination.
Evidence: `data/experiments/present61/packaged-smoke.json`.

## FSR 1 isolated experiment — 2026-11-03 (GPU-03, rejected)

Xeon E5-2666 v3 / RX580 2048SP, driver 31.0.21924.61, portable Release O3/PGO.
Official AMD EASU/RCAS FP32 prototype passed actual OpenGL orientation/resizing,
visible 1x/FXAA gameplay and 2000 VU1 parity checks. Full verify passed. Nine valid
100-second runs (40 s warmup, 1280x720, FXAA on, cap 60, VSync off): current 2x
59.6545 FPS; current 1x 59.3880; FSR 1x 59.3395. No reliable FPS or pacing benefit.
The isolated identical-input GPU scaler timing increased ~0.107 -> ~0.243 ms.
FSR output was softer; no clear quality advantage established. Original source
and build restored, preserving patch 61; no new public setting/patch/package.

One no-FSR 2x control stalled in presentation/host reporting and required forced
termination; excluded, evidence retained. Its replacement exited zero but left
stale session metadata; actual exit was cross-checked with the event and collector
result, without rewriting raw files. Details, hashes, exact sequence and artifacts:
[FSR 1 experiment](research/fsr1-experiment-2026-11-03.md),
`data/experiments/fsr62/comparison.json`. Weaker GPUs, NVIDIA and Hydra attack
remain unvalidated; this result must not be generalized into a universal FSR loss.

## Notebook installer delivery — 2026-11-03

Rebuilt the normal launcher/collector/diagnostic frontend and packaged both
installers from current sources through runtime patch 61, without the rejected
FSR prototype. Normal: `build.cmd -Stages launcher,installer -NoReleaseProfile`;
no compatible freshly trained release PGO manifest was available, so no stale
profile was shipped. The normal installer uses the standard game installation/
compilation workflow; the diagnostic kit embeds the previously validated restored
runner (`07e5cedfe449e9776efb0fc3c3845b917c2bbdbe419069c7cb5f11ab2a463dd8`).
These are different installation workflows, not a notebook performance comparison.

Both installers are in `data/_package/notebook-p61-20261103/` with SHA256SUMS.txt.
Normal payload: 1,571 members / 6 LZMS blocks; diagnostic: 1,358 / 12. Every member
matched its staging directory. Current runtime patches matched byte-for-byte;
normal staging contains no PGO profile, ISO, card or generated data directory.
Normal and diagnostic UI captures passed and were inspected; 11 deployed-collector
tests and launcher language validation passed. Artifacts:
`data/experiments/delivery61/`. No clean full game installation or physical notebook
performance validation is claimed by these packaging checks.

`gow-native-pc-setup.exe`: 28899958 bytes, SHA-256 `885501c3dec5fe096eec31390ead92d456b9b43e47d41279e827c49fb22641e4`.

`gow-native-pc-diagnostic-setup.exe`: 50073886 bytes, SHA-256 `fceb85867262c7d477261e419c2cbc7f0e637974f57dfe80f61880c623f46ab5`.

The newly packaged diagnostic kit also passed a 100-second gameplay smoke:
state=11/levelReady=1, matching runner hash, exit zero and no forced termination.
Evidence: `data/experiments/delivery61/game-smoke.json`.

## Local branch integration (2026-11-04, correctness only)

Combined main `37290ba` with fix-chore `2e0b023`, preserving both histories and
experimental defaults. Full `fetch,verify` passed with 15 CTest groups, VU1
backend equivalence and task replay. Disc-preparation and Linux orchestration
checks also passed. Patch 67 required context-only rebasing over patch 60.
No combined FPS/GPU or notebook acceptance claim; the game runner was not rebuilt.
See [integration evidence](research/merge-fix-chore-2026-11-04.md).

## RX580 merged renderer candidates (2026-11-04)

Separate correctness follow-up: [Japanese post-intro tests](research/black-intro-tests-2026-11-04.md)
rebuilt the preserved regional snapshot in `C:/gow-black-jpn`. Normal video reached
visible ship gameplay and passed all 11 smoke checks. Skipping video reached
visible combat, but the 150-second run needed forced termination on close.
This does not reproduce or fix the reported Intel HD 4400 black screen, and is
not a new FPS/support claim. Movie-transition audio deficits remain recorded.

Related external report: [i3-4170 / Intel HD 4400 analysis](research/chin-delivery-followup-2026-11-04.md).
This is a supplied-log review, not a locally tested or supported hardware tier.
The log does not establish 60 guest FPS; no new physical Intel validation occurred.

Xeon E5-2666 v3 / RX580 2048SP, driver 31.0.21924.61, separate
`C:/gow-p6667-clang` build. Patches 66/67 reached approximately 60 guest FPS
in bounded ship arrival comparisons, without a reliable general gain.
Experimental patches 72–74 passed synthetic real-GL differential color checks
and full verification (17 CTest groups plus VU1/task checks). Combined candidates
showed 59.994→59.832 FPS, 323.733→322.047% one-core CPU and
45.230→43.899% busiest GPU engine: short samples, inconclusive efficiency.
Defaults remain off. Longer displaced-scene comparisons and stale exit metadata
remain recorded as invalid/incomplete evidence. No weaker-hardware acceptance.
See [methods, artifacts and decisions](research/patch66-67-rx580-2026-11-04.md).


## 2026-11-05 ? system audit and shader/audio correctness

Xeon E5-2666 v3, approximately 16 GiB RAM, RX 580 2048SP driver
31.0.21924.61. [Full audit](research/system-audit-2026-11-05.md) records source
findings, official vendor-tool limits, patches 76/77, PGO/default corrections
and remaining acceptance work. No new FPS improvement is claimed.

Complete fetch/verify passed (18 CTest groups, guest-call/codegen and VU1
backend/self-loop/task checks). Release game and launcher built; old/new real-GL
fixtures matched all seven variants x 384 color frames. The available old PGO
profile was rejected, so this runner is unprofiled and cannot be compared as a
performance A/B with the preserved PGO executable. Reused-environment sync/build/
launcher took 706.974 s, not a cold installation result.

Two visible 150-second normal-boot, 2x/FXAA/early-FINISH/audio sessions passed
all 11 functional smoke gates, with private cards and graceful exit zero.
Menu and ship captures were inspected. Audio missing-frame observations remain:
7085 startup + 1646 transition with captures; 6605 + 1036 without captures.
The transition issue therefore persists without capture, and no audible-quality
or stable-60 acceptance is established. A later window reached only 57.18 guest
Hz (p99 35.263 ms) in the no-capture functional run. Do not attribute that result
to a patch without a controlled reference.

Regional registration/launcher ownership tests passed, but Japan/Europe overlay
source-baseline checks failed; their hashes were not weakened. Physical Intel,
NVIDIA, weak-PC sustained combat, subjective sound and clean-install <20-minute
validation remain open. Evidence: `data/experiments/audit-20261105/` and
`data/gow1/logs/session-game-20261105-{180405,180745}`. Candidate SHA-256:
`fb7c21ac35ebc7f1c1cecb073186a399bb4fe236a6e47addf731dc205064b045`.
The active build root was restored to `C:/gow-q59` after testing.

## 2026-11-05 - bounded audio trace follow-up

Same Xeon/RX 580 target. Patch 78 and its shutdown flush passed the full build and
verify (18 CTest groups, VU1 differential/replay checks). A 120-second visible
normal-boot session passed all 12 functional gates, including complete bounded
audio trace. Startup still lacked 6605 stereo frames; the transition lacked 1340.
The latter records continued but insufficient production, no reset, and <=1 us
acquisition in its deficit events. This is diagnostic evidence, not an improvement
in FPS or audible-quality acceptance. The earlier destructor-only trace failed
completeness and remains preserved. See [AUDIO-01 details](research/audio-transition-2026-11-05.md).

The regional overlay mismatch was traced to using newer USA sources: reconstructing
the exact historical pre-overlay baseline reproduced all stored hashes and both
overlays passed. No regional runner was rebuilt or gameplay revalidated. Strict
hash checks remain unchanged. Intel/NVIDIA and weaker machines remain untested.
