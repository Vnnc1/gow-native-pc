# Support the Asia SCAJ-97399 disc without a second build (`code` alias)

Paste-ready pull request description for `SCAJ-97399-support.patch`.
Apply first: `git apply SCAJ-97399-support.patch` from the repository root.

---

## Title

`disc: run the Asia SCAJ-97399 image on the Japan build (one profile field, no second build)`

## Summary

The supplied `SCAJ_973.99` image boots the **Japanese executable byte for byte**. It is not
USA-compatible and never will be, but it does not need a build of its own either: the Japan build
that already exists is the code it runs.

The profile could not express that. `[[regions]]` ties disc identity to build identity, so a
recognised serial with no build of its own is reported as `region_not_ported` and the launcher
refuses it, even when another region's validated build is byte-identical.

This adds the missing link and nothing else: a region may name the region whose executable it
carries, with `code = "<region id>"`. The bytes still decide — an alias is accepted only when the
disc's CRC **and** `.text` SHA-1 equal the named region's recorded values — and the disc keeps its
own data, cards and saves.

## Measurements (2026-11-03, supplied image)

| Value | SCAJ_973.99 (Asia) | SLPM_670.10 (Japan, recorded) | SCUS_973.99 (USA, recorded) |
| --- | --- | --- | --- |
| ELF CRC | `CA052D22` | `CA052D22` | `D6385328` |
| `.text` SHA-1 | `8ed48ca88c73e7e340be3a8e7ff16b07825cb96c` | same | `8c6e61a95e84e88b01a0cea25b3824cf6b2cbe00` |
| `.text` size | 1,690,724 | 1,690,724 | 1,686,436 |

Disc shape: `SYSTEM.CNF` (`VER = 1.01`, `VMODE = NTSC`), `PART1.PAK` 4,261,492,736 B and
`PART2.PAK` 4,252,477,440 B, 1663 TOC entries, layer1 at LSN 2082352. Text is English: the
profile's `language_hints` find `Press [XButton]` 18 times and `Beat the game to unlock` 10 times,
no other language matches, and there are no Shift-JIS kana runs in `R_PERM.WAD`.

No disc bytes or media are included here; only the measurements above.

## Changes

| File | What |
| --- | --- |
| `games/gow1/game.toml` | `asia-97399` region entry with the measurement, the language evidence and `code = "japan"`. |
| `tools/disc/identify.py` | `code` / `code_label` and `reason_code = "region_alias"` when the bytes match; a mismatch message when the serial does not match its recorded identity. `compatible` stays false, so the disc never enters the USA generation path. |
| `tools/disc/prepare.py` | Extracts and normalises a `code` disc, links its executable under the name the named build keys on (the runtime registers its overrides and gates the native integration by that file name), prints the `register_region.py` command, and keeps the disc out of `languages.json` — that manifest feeds the USA pipeline and the primary installation's Play list. |
| `tools/pipeline/register_region.py` | Registers the disc against the named region's overlay and measured identity, and records `code` in the registry entry. |
| `docs/disc-import.md` | Regional table row plus the rule: the bytes decide, never the serial. |
| `tools/disc/import_test.py`, `tools/disc/prepare_test.py` | Data-free regressions for the alias and its mismatch case. |

Renaming an ELF is still not a way around the code-signature check: the alias is verified against
the same CRC and `.text` hash the pipeline already trusts, and a disc whose bytes differ is reported
as `region_not_ported` with the measured values.

## Verification

On the supplied image, Windows, Python 3.13.16 (the launcher's portable interpreter):

- `python -I tools/disc/identify.py <iso>` → `game: gow1`, `edition: asia-97399`,
  `language: en`, `code: japan`, `reason_code: region_alias`, `compatible: false`.
- `python -I tools/disc/prepare.py --game gow1 --data <temporary directory> <iso>` → extracted in
  51 s, 16 files, `layer1 2082352`, `SCAJ_973.99 is also SLPM_670.10` (hard link, same inode and
  bytes), no `languages.json` written because only a regional disc was given.
- `python -I tools/pipeline/register_region.py --region asia-97399 --elf .../SCAJ_973.99` →
  `Regional ELF identity mismatch`; with the same bytes named `SLPM_670.10` → passes the overlay and
  identity checks and stops at the disc-folder check, as expected before a real build exists.
- `tools/disc/prepare_test.py`: 4 tests OK. `tools/disc/import_test.py`: 15 tests OK, 6 skipped
  (no `chdman`).

## Not verified

No Japanese-code build exists on the test machine, so nothing was played, the launcher was not
exercised end to end, and no registry entry was written. The launcher side may need one line to
hand `code` discs to the `discs` stage if it currently filters on `compatible`; that code is not in
this repository.

## How to test it

```bash
# once the Japan edition is built and registered
python -I tools/disc/prepare.py --game gow1 --data <its own data directory> "<asia iso>"
python -I tools/pipeline/register_region.py --region asia-97399 \
    --runner <japan runner> --elf "<that folder>/SLPM_670.10" \
    --data "<its own data directory>"
```

Then select the edition on Install. Regional cards and saves stay separate from the primary
installation.

---

## Suggested `docs/research` note

If you want the evidence trail in the repository, this is the note I would add as
`docs/research/asia-scaj-97399-2026-11-03.md` (not part of the patch, so the diff stays small):

```markdown
# Asia SCAJ-97399: the Japanese executable under another serial (2026-11-03)

## Result

The Asia SCAJ-97399 image is not a USA-compatible disc and not a new port: its boot executable is the
Japanese one byte for byte (CRC `CA052D22`, `.text` SHA-1 `8ed48ca8…`, 1,690,724 bytes). It runs the
Japan build. Support is a profile declaration (`code = "japan"`), not a build.

## Evidence

- `SYSTEM.CNF`: `BOOT2 = cdrom0:\SCAJ_973.99;1`, `VER = 1.01`, `VMODE = NTSC`.
- ELF: 1,905,500 bytes, CRC `CA052D22`, `.text` 1,690,724 bytes at file offset 0x1000.
- Identity equal to `games/gow1/game.toml` `[[regions]] id = "japan"` on both recorded values.
- Disc: `PART1.PAK` 4,261,492,736 B, `PART2.PAK` 4,252,477,440 B, 1663 TOC entries, layer1 LSN
  2082352; `prepare.py` extracts 16 files.
- Language: `language_hints` score only `en` (`Press [XButton]` 18, `Beat the game to unlock` 10);
  no Shift-JIS kana runs in `R_PERM.WAD` (21 apparent runs in `R_SHELL.WAD` are glyph-bitmap noise).

## Why the profile could not say it

`[[regions]]` was one-to-one with a build: an unknown serial is `unknown game`, a known serial
without its own build is `region_not_ported`, and the launcher matches discs to registered builds by
CRC and code hash. Two pressings sharing one executable had no way to say so.

## Falsified / rejected

- "Rename the ELF and it runs": rejected by policy and by the runtime gates, which are compiled on
  the `SLPM_670.10` file name in seven places. The alias here is verified by hash, not by name.
- "USA-compatible": `.text` sizes and hashes differ, and 13.75% instruction overlap at the same
  offsets is not equivalence (see `regional-port-2026-11-02.md`).
- "Needs its own regional build": unnecessary; the code is identical, so a second build would
  duplicate 4,000+ functions for no behavioural gain.

## Limits

No Japanese-code build existed on the test machine: identification, preparation and the registration
gate were exercised, gameplay was not. Launcher routing for `code` discs is unverified here.
```
