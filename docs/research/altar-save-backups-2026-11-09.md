# Automatic altar-save backups — 2026-11-09

## Result and scope

`fix-chore`, patch `zzz-309`: a successful USA altar save creates one dated card
backup in the existing launcher history. A seven-second host notification reports
success or backup failure. F1 manual copies use the same checked publisher.
The Saves page refreshes while visible during gameplay and labels `source: auto`
in all nine launcher languages. The in-game notice uses the menu's four languages.
Old backups are retained; restoring still requires the game to be closed.

The hook covers the USA executable and byte-identical-code translations. It is
not applied to Europe/Japan overlays. Existing compiled installations need a
rebuilt matching runner; no toggle or optimization stage enables the feature.

## Completion signal

Initial MCSERV RPC tracing produced no card events. Runtime documentation and
generated code confirmed that this game uses **EE libmc2 over DBCMAN/MC2_D**, not
generic MCSERV open/write/close. Low-level card writes are page-sized and cannot
serve as a completed-save signal.

An isolated trace of `sceMc2CheckAsync` (`0x27CF38`) during the supplied card's first
slot/altar route observed command 6 completing twice: **81,920 bytes of payload**,
then **68 bytes of slot-index data**. The game subsequently showed its translated
“Save complete” screen. The generated save state machine at `0x22FE30` calls the
same whole-file writer (`0x22E800`) from `0x2305C0` for the payload and `0x2306B8`
for the final index. The latter checks the completion return and game error before
advancing toward success; errors branch to the failure state.

The wrapper delegates to the original generated function and backs up only when:

- entry PC is `0x22E800`, caller return PC is `0x2306C0`, slot is 0 and size is 68;
- the original returns to that caller with completion result 1;
- game error at `0x2A1284` is zero and completed byte count at `0x2A128C` is 68.

Pending work, other callers, partial writes, errors, another card slot and resume
entries retain original behavior without copying. The state machine advances
after this successful return, so polling does not create duplicate backups.
Temporary tracing is not included in the patch. The owned override was synchronized
to the runner source before building and testing.

## Publishing and UI

`runtime/gow_save_backup.h` serializes runtime manual/automatic copies, bounds the
card size and checks read completion and modification time. It reserves a unique
dated directory atomically (including same-second collisions), writes/closes the
temporary card and metadata, and only then renames the card to `Mcd001.ps2`.
Both existing readers require that final name; incomplete copies stay invisible.
Failure cleanup touches only files in the directory reserved by that call.
Paths use UTF-8 conversion and local timestamps use the thread-safe platform API.

Only an atomic result crosses from EE to the host drawing thread. The notice does
not open the menu or steal controls. A failed backup leaves the active card alone
and reports failure; it never reports a successful copy before publication.
This also fixes the old manual helper's unchecked rename/metadata-write results.
Copying is synchronous at the completed save, not a background snapshot during
the next write. No frame-pacing or performance improvement is claimed.

## Validation and evidence

Windows, Xeon E5-2666 v3 / RX 580, Qt 6.8.3, pinned LLVM 20261020. Evidence remains
local under ignored `data/auto-save`; no cards/discs were packaged or uploaded.

- `altar-save-tests.py`: production wrapper and publisher passed pending/error/
  short-write/caller/slot/resume gates, register parity, byte-exact copies, UTF-8
  paths, unique history, metadata, manual copies and failure-result checks.
  The extracted production notice passed success/failure text in all four
  languages, one-time result consumption, expiry and a bounded 640-pixel layout.
  This suite is included in Windows `verify`.
- `save-history-ui.py`: real Saves QML page passed new-history refresh during play,
  automatic-source label, refresh on visibility, and no polling when hidden or
  after the game closes. Normal launcher build passed.
- `regional-play-ui.py` passed existing save/edition routing. The environment
  contract initially failed against the pre-PR26 local runtime; rerunning against
  the full-chain isolated runtime passed 64 play-map keys / 71 variables / 3 effects.
- Python pipeline suite: 17 passed. Linux pipeline suite: 7 tests, one skipped on
  Windows. Patch forward application in the local runtime and reverse checks in
  the built full-chain runtime passed; no unrelated runtime changes were copied.
- Real private-card save: `final-save/result.json` records exactly one backup,
  byte-identical to the completed active card, and normal collector/child exit 0.
  The game's “Save complete” screen was inspected in its internal capture.
- Real destination failure: making the backup destination a file prevented any
  history publication while the game still showed “Save complete” and wrote its
  active card. Normal exit 0; evidence is `failure/result.json`.
- Reloading an automatic backup reached the altar. The first cancellation probe
  used Circle, which this prompt ignored: it proved that opening the altar alone
  does not back up, but was not counted as a cancellation test. The corrected
  probe selected **No** and passed in `final-reload-cancel`: the restored card's
  hash stayed identical, zero backups were created, gameplay at the altar was
  inspected after cancellation, and collector/child exited normally with code 0.

Final runner SHA-256:
`a7746aec97845329e61a18748962af7f88672002945d3593237bf51c398caad6`.
The earlier save/failure/reload investigation used
`c6e57dc96674fbeb66cdf5d559ecd37008fe2fa36dbd68943430ca0dc2c11596`;
the final revision additionally uses thread-safe local-time conversion.

## Limits

The user's source card hashes were checked after the isolated runs. Formatting a
new card, all altar locations, regional hooks and Linux gameplay were not tested.
The four-language notification drawing logic was tested, but the Windows capture
helper timed out twice; internal GS screenshots exclude host overlays, and the
F12 attempt did not produce an image. Therefore no visual screenshot validation
of the actual overlay is claimed. The repeated-save route also moved Kratos away
from the altar after saving, so its second R2 press was not counted as a second
save; unique history was validated by the production publisher tests instead.
