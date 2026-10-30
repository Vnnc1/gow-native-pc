# Saves: memory card copies for testing (F1 > Saves, launcher Saves tab)

Goal: play forward to an area once, keep that progress, and later start tests from there again (for example, the
frame rate after the ship) without replaying the game.

## What a save is (and is not)

- **No savestates.** This is a static recompilation: the guest threads run as host code on host stacks, so the state
  of the game at an exact moment (CPU registers inside recompiled functions, host stacks, GS/VU1/IOP worker threads)
  cannot be written out and loaded again. An emulator can do this; this runtime cannot.
- **A save is a copy of the memory card.** The game itself saves at its save altars into the memory card image
  (`Mcd001.ps2`, PCSX2 `.ps2` format, 8 MB raw, 528-byte pages). A copy of that file holds every save slot the game
  had written when the copy was made. Loading it means loading the game's own save from the game's menu.

So the workflow is: **save at an altar in the game → make a copy → later put the copy back → load in the game.**

## In game: F1 > Saves (runtime patch 26)

- F1 opens the runtime panel; its first tab is **Saves**.
- "Save a copy of the card" (optional label) copies the card to `GOW_SAVES_DIR/<yyyyMMdd-HHmmss>/`:
  - `Mcd001.ps2`: the card image, read again if the game wrote to it during the copy (size/time check, 5 tries);
  - `save.json`: `{label, time, source: "F1", card, bytes}`.
- It shows when the game last wrote the card ("N min ago"): if that is older than your last altar save, the game has
  not finished writing yet.
- The tab never changes the card the game is using: the running game keeps the card in memory
  (`ps2xIOP/src/emulator/core/memory_card.*`) and would overwrite a file replaced under it.
- `GOW_MC0` (the card path) and `GOW_SAVES_DIR` are set by the launcher. A runner started by hand needs both, else
  the tab says so. Code: `drawSavesTab` / `snapshotCard` in `PS2Recomp/ps2xRuntime/src/lib/ps2_debug_panel.cpp`.

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

- **Runtime snapshot:** the functions above `drawSavesTab` build on their own with a fake 8 MB card. They were tested
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
