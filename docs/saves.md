# Saves: automatic altar backups and launcher history

Goal: play forward to an area once, keep that progress, and later start tests from there again (for example, the
frame rate after the ship) without replaying the game.

## What a save is (and is not)

- **No savestates.** This is a static recompilation: the guest threads run as host code on host stacks, so the state
  of the game at an exact moment (CPU registers inside recompiled functions, host stacks, GS/VU1/IOP worker threads)
  cannot be written out and loaded again. An emulator can do this; this runtime cannot.
- **A save is a copy of the memory card.** The game itself saves at its save altars into the memory card image
  (`Mcd001.ps2`, PCSX2 `.ps2` format, 8 MB raw, 528-byte pages). A copy of that file holds every save slot the game
  had written when the copy was made. Loading it means loading the game's own save from the game's menu.

For the USA edition and compatible translations, the workflow is: **save at an altar → automatic backup →
later restore a copy with the game closed → load from the game's menu.** Existing builds need an updated runner.

## Automatic history (runtime patch zzz-309)

- The backup starts only after the altar's final index write succeeds, after the save payload has been written.
  Opening an altar, cancelling, loading, pending writes and failed writes do not create a backup.
- A successful copy shows an in-game notification for seven seconds and appears as an automatic backup in the
  launcher's Saves page. The visible page refreshes every two seconds while playing and on return to the page.
- Each backup has its own dated folder and `save.json` with `source: "auto"`. Old copies are kept until the player
  deletes them; each raw card occupies about 8.25 MiB. There is no automatic upload or pruning.
- If the destination cannot be written, the game save remains on the active card and the notification reports the
  backup failure. No incomplete card copy is added to the history. Fix the folder/disk problem and make a manual copy
  with F1 or save again at an altar.
- Regional Europe/Japan runners do not yet have the corresponding completion hook; their manual copies remain
  available. The hook is specific to the validated USA executable, including compatible translations.

## In game: F1 > Saves (runtime patch 26)

- F1 opens the in-game menu; choose **Save**. Ctrl+F1 opens the debugger's **Saves** tab.
- "Save a copy of the card" (optional label) copies the card to `GOW_SAVES_DIR/<yyyyMMdd-HHmmss>/`:
  - `Mcd001.ps2`: the card image; size/time changes during reading cause an error instead of publishing a partial copy;
  - `save.json`: `{label, time, source: "F1", card, bytes}`.
- It shows when the game last wrote the card ("N min ago"): if that is older than your last altar save, the game has
  not finished writing yet.
- The tab never changes the card the game is using: the running game keeps the card in memory
  (`ps2xIOP/src/emulator/core/memory_card.*`) and would overwrite a file replaced under it.
- `GOW_MC0` (the card path) and `GOW_SAVES_DIR` are set by the launcher. A runner started by hand needs both, else
  the tab says so. Manual and automatic runtime copies share `runtime/gow_save_backup.h`; data and metadata are
  closed successfully before the final card name makes the copy visible to readers.

## In the launcher: Saves tab

- `launcher/qml/PaginaPartidas.qml`, logic in `Lanzador` (`launcher/src/lanzador.cpp`):
  - `partidas`: the list, newest first;
  - `guardarPartida`: a copy with the game closed;
  - `importarPartida`: a `.ps2` card from elsewhere; only files of exactly 8,650,752 bytes are accepted;
  - `restaurarPartida`: "Use";
  - `borrarPartida`: delete.
- **Use** (restore) refuses while the game runs. It first stores the current card as a `backup` copy ("before
  <name>"), unless the two are identical, and then writes the chosen copy over the card atomically (`QSaveFile`).
- The folder is `data/<id>/saves` (git-ignored with the rest of `data/`; it holds the user's save data, so never
  publish it).
- The card is `GOW_MC0` when set in the environment, else `Mcd001.ps2` next to the ELF of the chosen language: the
  same file the runtime uses (`iop_emulator.cpp` path provider). Each prepared disc folder (language) therefore has
  its own card; a copy made with one language is restored into the card of the language chosen in Other > Game text.

## Testing it without the game

`tools/test/altar-save-tests.py` compiles the production completion wrapper, backup publisher and notification
code with observing guest/render fixtures. `tools/test/save-history-ui.py` exercises the real Saves QML page.
`tools/test/altar-save-smoke.py` exercises save/load/cancel/destination-failure with a private card and normal
collector shutdown. See [the implementation and measured results](research/altar-save-backups-2026-11-09.md).

- **Earlier manual snapshot tests:** the functions above `drawSavesTab` built on their own with a fake 8 MB card. They were tested
  for:
  - no env: message;
  - no card: message;
  - a copy that is byte-identical (`cmp`);
  - labels stripped of quotes and backslashes;
  - two copies in the same second getting `-2`.
- **Launcher:** a small harness linking `lanzador.o` was tested for:
  - card path;
  - copy;
  - path-traversal names refused;
  - restore with an automatic backup;
  - import size check;
  - list order and fields;
  - delete.
