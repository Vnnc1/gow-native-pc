# Aphrodite dialogue and keyboard QTE guide — 2026-11-09

## Report and decision

The player completed a 29-minute test with the full fix-chore runner
`c78eebddefa9ab45486f685e8ecbd47db6c3af6d8718bf9e5b496044239cfc41`.
After obtaining Medusa's head, Aphrodite's dialogue was missing while music,
effects and gameplay continued. The other issue was visual: keyboard input
worked but stick QTEs still displayed the controller diagram without key labels.

The player subsequently accepted manual validation of the Aphrodite scene and
has no save immediately before it. No audio correction is claimed or shipped:
the evidence below does not establish a runtime defect or prove an ISO defect.
The WASD build was held until these audio checks completed and that manual-test
handoff was accepted. Player discs, cards and preferences are never modified.

## Original versus translated audio

Read-only sources were the original USA prepared disc under
`D:/gow-pr26-test-data/gow1/discs/usa` and the installed PT-BR translation under
`C:/Users/dzvini/Documents/gow-test/data/gow1/discs/translation-pt-br-97464644`.
`ATHN02D.WAD` contains `HeadTalkPostMedusa`, `HeadRemindMedusa`,
`HeadTalkPostMinos` and their SoundController scripts. The compared script
records are byte-identical across these discs. `SEM_HeadTalk` references
`SND_MI_A02MI99`.

| File | Original bytes / rate | Translated bytes / rate |
|---|---|---|
| A02MI03.VAG | 66,576 / 22,050 Hz | 118,864 / 44,100 Hz |
| A02MI04.VAG | 54,144 / 22,050 Hz | 114,656 / 44,100 Hz |
| A02MI98.VAG | 72,400 / 22,050 Hz | 144,080 / 44,100 Hz |
| A02MI99.VAG | 72,048 / 22,050 Hz | 144,080 / 44,100 Hz |

The translated payloads are nonempty. Their termination blocks lie beyond the
header's declared sample extent, unlike the original assets. This difference
alone is not proof of the silence or authorization to rewrite their headers.
No original dialogue was substituted for the translated files.

A standalone diagnostic compiled the installed production `sound_engine.cpp`,
loaded each VAG's declared ADPCM payload, configured its sample-rate-derived
pitch and both master volumes, and drained output throughout playback. All eight
produced substantial nonzero PCM. Original/translated A02MI99 yielded RMS
11,021.51 / 13,198.39 and peaks 32,500 / 32,012. `GOW_SND_VERIFY=1` repeated the
comparison without batch/per-frame mismatch. This validates decoding/mixing,
not guest sound loading, dialogue triggers or listening to the actual scene.
An initial diagnostic omitted core 1 master gain and produced silence even for
the original; it was corrected before drawing conclusions.

The existing sound regression also passed: trace/reset accounting, resampler
reset parity, 2–48-voice saturation and envelope release to silence. The player's
session reported 7,917 missing frames only at startup and no dropped frames;
that cannot diagnose a particular later dialogue voice.

A private-card `GOW_WARP=ATHN02D` probe reached the scene but led to death before
the requested dialogue. Its CD trace contains no reads intersecting the four
voice assets above. It exited normally, but is NOT accepted as reproduction or
validation of the reported failure. The recent backup's first slot was separately
loaded and confirmed to be the ship. Its source and copied card hashes remained
equal, with no save written.

## Keyboard correction: zzz-314

Recognized Greek stick diagrams now publish a four-key movement guide below the
original direction animation. Labels use the existing `li_arriba`, `li_izq`,
`li_abajo`, `li_der` mappings; the installed boot map is W/A/S/D. The host draws
these supplemental keys only for the keyboard, following last-active-device
selection. Controller diagrams retain their existing appearance. Direction
arrows and rotation/shake information are preserved; no gestures are automated.

Composite diagram leaves share one guide per guest frame. Publication is bounded
and requires room for all four keys. This currently supports one guide per frame;
simultaneous independent diagrams would need symbol identities. Real combat
placement remains a manual acceptance gate.

Production tests cover default WASD, custom I/J/K/D labels, direction layout,
composite deduplication, capacity fallback, existing pad/QTE inputs and world
projection. The hidden GPU preview was inspected with WASD. The earlier I/J/K/D
preview deliberately illustrated remapping, not the player's settings.

A draft patch export mistakenly contained a test fixture instead of production
source; target-source tests rejected it before any runner build. The draft was
reversed and regenerated from the correct baseline. All three final production
source hashes match, and the corrected patch is 57 lines.

Local evidence: `data/aphrodite-keyboard/`, including `audio-assets/comparison.json`,
`mixer-results.log`, `mixer-verify.log`, `regression.log`, `warp-cd-reads.json`,
`voice-warp-pt/`, `locate-save/`, `final-tests.log`, `wasd-preview/` and
`build-final.log`. Extracted game audio and captures remain ignored local evidence.

## Deployment result

Release runner rebuilt in the installed, owned `C:/gow-build-clang` tree:
`147a45e3e45bf726d1ae144d18be3aecc6c99cb4d750dc87ad70f81fac682eb8`. The 25-second private-card keyboard startup capture and normal
shutdown passed; collector state is `completed`, exit 0. This is not a combat
QTE test. All 9 protected card/history files and launcher registry settings stayed
byte-identical. The previous executable and registry export are retained under
`data/aphrodite-keyboard/before-build/`. No game process was left running.
