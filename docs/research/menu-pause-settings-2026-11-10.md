# Menu pause, persistent settings and texture packs — 2026-11-10

Status: pause, persistence, unified texture-pack entry and accessibility notice implemented on fix-chore. **Native individual save-slot browsing/quick loading with native names and previews is NOT implemented.** The existing whole-card backup/restore contract remains in force.

## Runtime and launcher

- zzz-320 pauses the EE scheduler at an execution boundary. The host continues rendering/polling; queued work can finish. On resume, scheduled wall-clock deadlines move by the actual paused duration. Guest cycles do not catch up to elapsed wall time. Stop wakes the wait, so closing while paused remains normal shutdown.
- The common SPU2 callback outputs silence while paused without draining the producer queue or advancing played/produced/missing counters. Volume and mute initialize after boot-environment restoration, and apply after diagnostic PCM capture.
- Each menu edit publishes a bounded JSON transaction via close + same-directory rename. The launcher-owned `GOW_MENU_SETTINGS` path is unique per launch under app data/menu-settings; it is excluded from the reusable boot and diagnostic export. No registry edits occur in the runtime.
- `launcher/src/menu_settings.h` validates keys, types, ranges and input codes, then imports only changed fields into the existing `ajustes` QSettings group. It acknowledges after sync. The UI polls every 500 ms; if closed, pending transactions are imported when reopened. Unrelated preferences are preserved. Runtime failures are shown in the menu. Each launch is bounded to 4096 transactions of at most 32 KiB.
- Graphics, master audio, bindings (including Delete/reset), cheats and automatic QTE persist. Launcher changes apply to the next launch; this is not a live bidirectional settings editor. Renderer options that previously required restart retain that requirement.
- Texture folder selection/toggle moved from Accessibility to Mods / Textures. Existing package/profile, effect/code/VFS capabilities remain intact. The in-game category lists selected manager mods and the legacy texture-pack folder; selection does not prove replacement hits, and pack changes require restarting the game.
- Startup shows a timed side panel with active automatic/held-button/stick assists and animation cancellation. Hold buttons include keyboard and pad labels. The RatOne source artwork is unchanged.
- zzz-322 preserves modifier-alias semantics in exported keyboard maps, bypasses obsolete default migration for those explicit maps, and retains wholly unbound controller maps through launcher serialization. Six production input modes cover default/classic/custom/automatic/explicit/empty.
- zzz-321 corrects persisted Delete, recognizes GOW_QTE_HOLD=1 as circle and excludes 0. `GOW_MENU_TEST_RESUME_AT` is accepted only with GOW_PAD_TEST=1 and a bounded time; it exercises the production close/resume path without requiring desktop input.

## Validation

Evidence is in ignored `data/menu-state/`, not in a player package.

- Normal fetch/configure/sync/build with the full ordinal chain: passed. First attempt failed because the new patch lacked the PS2Recomp path prefix; corrected before deployment. No recompilation of unchanged generated EE code was needed.
- Launcher Release build: passed. A real-QML test caught a local SectionTitle moved outside its scope; replaced by the matching styled Text and retested.
- `menu-state.py`: production settings publisher/importer, invalid transactions, isolated QSettings, repeated imports, unrelated preference preservation, pause/resume/stop and volume passed. Extracted production audio callback: pause preserves queue/sample counters and resumes gain/silence-tail behavior.
- `game-menu.py`: production menu navigation, pad slot 3 shortcut, release guards, remapping, graphics/audio/QTE and durable event publication passed; 640/320 layouts and startup notice rendered.
- `control-prompts.py`: production keyboard/classic/custom/automatic/explicit/empty prompt modes, mapping export, four QTE modes, visibility/world/scanner checks passed.
- `altar-save-tests.py`: all completion/error/resume/slot gates, metadata, card copy and host notification checks passed.
- `regional-play-ui.py`: actual Main.qml routes editions/cards correctly and carries imported bindings/graphics/audio into the next play map. Mods selftest and launcher environment reader contract passed.
- Session collector: 16 tests passed, including audio settings in reports and omission of the private menu bridge.
- Private-card 180-second game smoke: 26 measurement windows with zero guest flips and a responsive host; close while paused exited 0. Original and private cards were unchanged.
- Private-card 85-second resume smoke: two fully paused windows; trace gap 18,138 ms, only 8 guest frames between the last pre-pause and first post-resume sample (the sampling boundary accounts for these). Another 1,361 guest frames followed. Four later audio windows had missing=0 and dropped=0; normal exit 0; both cards unchanged.
- Desktop automation screenshot capture timed out and initial key attempts were rejected after detected user input. After the user left the window untouched, accepted key events still did not demonstrate resume. Therefore the end-to-end resume evidence is the gated scripted close path plus the production-menu keyboard unit test, not proof of a physical controller or successful desktop F1 injection.

These are correctness checks, not performance A/B results. Pause windows deliberately show zero guest FPS and must not be used as a performance benchmark. The player trace `g` is elapsed host time since gameplay start, not the game's simulation clock.

## Native saves investigation — pending

Read-only examination used a private copy of the existing USA translated-edition memory card. The card has a PS2 filesystem, a 68-byte game index and 81,920-byte dataN.bin files. The tested index has records referencing data4, data1, data2 and data3, plus an additional word; data0 also exists. Thus listing filenames as save slots would be incorrect. The first word must not be interpreted as a simple count without completing the native format analysis.

The payloads expose zone identifiers (Athn01D, Athn01EE, Athn06A, Athn06C). These are internal codes, not verified localized location names. The examined data0 payload has mostly zero padding after its first block; no embedded preview was identified. A claim that arbitrary backup screenshots reproduce the native load-screen preview would be unsupported.

The native update path reaches 0x22FE30 from 0x21FB28, with initialization through 0x22FDE0. This is a stateful save/load flow, not a proven callable quick-load API. No speculative guest-state write or live card replacement was added. The IOP caches the card; overwriting its host file during play is not a safe load operation.

Remaining acceptance: validate index mapping on all private cards, map names/previews from game resources, identify and test a normal native load transition from gameplay, preserve the active card and create rollback backups, then expose matching individual slots in both interfaces. Current launcher restores still require the game closed. This portion of the user's request remains open.

## Deployment

The launcher-owned build at `C:/gow-build-clang` was rebuilt from the installed source checkout in `C:/Users/dzvini/Documents/gow-test`; updated launcher/collector binaries are installed beside its existing Qt DLLs. Protected card/history files and QSettings registry exports are compared before/after. Backup and exact binary hashes are recorded in `data/menu-state/deployment/manifest.json`. The 180/85-second gameplay evidence used patches through 320/321 respectively; the final 322 change affects only binding serialization and is covered by production input/real-QML round-trip tests. No saves or configuration defaults were reset, and no commit or release was published.
