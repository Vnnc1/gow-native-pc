# Individual native saves — 2026-11-10

Branch: `fix-chore`. Runtime patch: `zzz-323-native-save-slots.patch`.

## Implementation

- Read-only PS2 filesystem reader shared by the launcher and runtime. It follows allocated FAT chains with
  bounds/cycle checks and selects exactly the valid records in the game's 68-byte index. The rotating spare
  payload is not shown as another slot. Both supported card geometries produce identical slot metadata.
- `games/gow1/game.toml[saves]` owns the card directory, resource names and message base. Disc preparation and
  normal sync produce `.gow-save-slots` beside each compatible edition. Resources are read from that edition's
  TOC/PAKs, bounded to 16 MiB. Generated images are private game data, not repository assets.
- Native `0x1B7AA8` selects `TXR_SavePt%02d` from the location identifier; `R_SAVEPT.WAD` contains the 128×80
  PSMT8 images and palettes. Names are messages 601–641 in `R_PERM.WAD`'s `msgs_en.txt`. The tested Portuguese
  edition uses custom accent sequences, which are converted for the host UI. Other custom font encodings need
  separate validation. The WAD/TXR layout was cross-checked against the primary format reference
  [god_of_war_browser](https://github.com/mogaika/god_of_war_browser); no external tool is needed at runtime.
- The launcher sends an atomic, session-local slot request through `GOW_MENU_SETTINGS/load.request`.
  The in-game menu uses the same queue, closes and resumes the guest before loading. Confirmation warns that
  progress since the last altar is discarded. The queue is consumed on the EE thread, never from rendering.
- USA `0x21F3C8`'s gameplay entry delegates to the native `0x21D868` return-to-menu path. At the ready frontend
  (`0x21EBF8`, state 3), the native Load action is selected. `0x22F5E0` state **8** is the slot selection state,
  as verified in the ELF jump table at `0x2B8500`; the index/card/magic are validated before choosing the slot.
  Original routines retain asynchronous reads, deserialization and level loading. No host-file restore occurs.
- Historical full-card restore remains closed-game-only. Europe/Japan hooks are not generalized from USA.

## Evidence and regressions

- `save-slots.py --compiler ...`: 8 tests passed, including the actual C++ reader, data-only/spare-byte parity,
  malformed allocation chains, missing/duplicate payloads, index selection and native palette decoding.
- Read-only inspection of all five local cards succeeded. Their active index refers to data4/data1/data2/data3;
  data0 is an older spare. Real previews for all four occupied slots were inspected in the rendered menu.
- `native-load-tests.py`: production entry/state gates, native teardown, frontend selection, index validation,
  wrong-card cancellation, resume delegation and success/error publication passed.
- `game-menu.py`: production navigation, controller shortcut, save-load confirmation/cancellation, busy guard,
  menu unpause, graphics/audio/binding persistence and small layouts passed with a private card.
- `save-history-ui.py`: real QML history and individual slot refresh passed. `regional-play-ui.py` routing and
  existing settings persistence passed. `altar-save-tests.py` completion, backups and notification passed.
- `prepare_test.py`: 5 tests passed. Linux pipeline tests: 7 tests, one host-specific skip on Windows.
  General pipeline tests: 17 passed. These are not Linux GPU/gameplay acceptance.
- A private prototype loaded slot 3 (Temple of the Oracle) from ship gameplay, returned to gameplay and exited
  normally. A host screenshot confirmed the destination; source and private card hashes were unchanged.
- Integrated attempt 01 rejected CRLF bytes written by the test instead of the launcher's LF request protocol.
  The test now writes the exact QSaveFile bytes. No card change occurred.
- Integrated attempt 02 exposed a real repeat-load bug: the UI's transient dialog field could reset before the
  hook inspected it, leaving the native slot picker waiting. Selection now uses native loader state 8, and the
  unit fixture explicitly keeps the UI dialog field at zero. The failed run is retained under ignored data.
- The native load screen also exposed a date discrepancy. Card timestamps are Japan RTC time, not local time;
  both host interfaces now convert to local time, matching the tested native screen.

## Final integration

Integrated attempt 03 passed four native loads (slots 0, 2, 3, 0), including three returns from gameplay,
and exited normally with code 0. Source and private card hashes remained unchanged. The final runner SHA-256
is `7a66583fb073314a75a457486d08b2d6e6166f04ebc3b91ab383f2663b15bd29`.
The same eight reader/asset tests and production native-load wrapper tests passed under Ubuntu WSL with Clang.
These tests do not establish Linux gameplay or physical-controller acceptance.

Local evidence: `data/native-saves/`. Deployment protection manifest: `data/native-saves/deployment.json`.
