# Spartan-style R2 prompt — 2026-11-10

The maintainer reported a large distorted CTRL behind the new prompt and identified native slot 3.
Patch `zzz-325` fixes recognition of shared Greek R2 animation leaves.

## Cause and correction

The scanner collects the leaves of named Flash symbols. Membership in `R2ButtonPress` was treated as sufficient
to replace every appearance of a leaf. The live slot-3 scene demonstrated otherwise: shapes 115, 117, 118 and 119
were classified as R2 while their current instance was not the named R2 button. Shape 116 had the verified
`R2ButtonPress` instance. Replacing the other layers interfered with the composite drawing and produced a pale
silhouette and an incorrectly placed/oversized CTRL. The UI also has a separate ordinary R2 label near the altar.

Greek R2 replacement now requires the bounded USA instance-ancestry check to identify `R2ButtonPress` at the
actual draw. Other uses of those leaves retain their original rendering. Ordinary text labels, other buttons,
controller mappings and original direction diagrams retain their paths. Existing ready/capacity guards remain.
Diagnostic mode records bounded leaf/instance identities; normal play does not enable this trace.

## Evidence

- Private copy of the player's card, slot index 2 (third slot), Temple of the Oracle, translated USA edition.
- Attempt 01 accidentally opened the test menu immediately and never loaded; retained as invalid evidence.
- Attempt 02 loaded without the player's graphics/mapping overrides; insufficient to reproduce the report.
- Attempt 03 used the player's mapped CTRL, 2x/AF16/FXAA and texture pack and reproduced the pale silhouette.
- Attempts 04–06 used the candidate. Capture 06 shows the animated CTRL with its normal rectangular artwork,
  without the pale distorted layer; capture 05 confirms the transient prompt can disappear normally. Captures
  are host-frame samples, not an animation-frame-aligned performance comparison.
- Source and private card hashes remained unchanged; successful probes loaded once and exited with code 0.
- Final runner (including Linux header compatibility changes) repeated the slot-3 load/capture and exited 0,
  with both cards unchanged. SHA-256: `1bc8b7d1d4aaebd1d7325904a8a73476193848a7ea4e75a530ed0807aca0cc09`.
- Production prompt tests passed labels/remaps, QTE assists, original draw fallback, world-hook contracts and
  bounded instance traversal. New regression retains shared leaves outside the R2 instance, rejects another
  symbol and replaces a verified R2 instance. Real physical controller/combat acceptance remains broader work.

Local private evidence: `data/native-saves/slot3-prompt-03..06`, `prompt-regression.log`.
No game textures, screenshots or RAM dumps are distributed in the source release.
