# Disc import and regional compatibility

The launcher accepts ISO and CHD in Install > Add ISO / CHD. Conversion does not
change which game executables the native runtime supports. ZIP is not a disc
format: extract the ISO first. Demos are excluded.

## CHD

Supported inputs are standalone CHDv5 DVDs and legacy single-track MODE1/2048
CD containers without gaps. Mixed/audio tracks, raw 2352-byte tracks, parent
dependent CHDs and older CHD versions are rejected with a reason. Images without
successful raw and overall SHA-1 verification are rejected as well.

On Windows, the first CHD import downloads the pinned official MAME archive and
7-Zip extractor, checks their SHA-256 hashes, and extracts only the tool/license.
The cached executable is checked against its pinned SHA-256 on subsequent use.
Pins live in `tools/pipeline/toolchains.json` under `disc_import`. There are no
administrator privileges, PATH changes or automatic uploads. The MAME archive
download is about 84 MiB. On Linux install `chdman` from MAME tools; it must support
`extractdvd`. `GOW_CHDMAN` can select an explicitly installed executable on either
platform. An override is user-managed rather than the pinned Windows binary.

The source image is read-only. Conversion uses a private temporary directory,
checks available space and verifies integrity before publishing the ISO. The
cache lives under `data/imports/chd`; expect space for the uncompressed ISO in
addition to the CHD and the installed game files. CLI `prepare.py --data <dir>`
uses `<dir>/imports/chd`. Imports sharing a cache entry or tool installation are
locked; another writer receives an error rather than sharing partial files.

Cache keys include absolute source path, size, mtime and ctime. Reuse checks the
extracted ISO size and SHA-256. This still reads the ISO, but avoids decompression.
A source modified during conversion is rejected. A source modified while
deliberately preserving all identity metadata requires deleting its cache entry
and reimporting. Cache images are game-derived data: never commit or package them.
The cache can be deleted while no import/install is running; the next import will
recreate it. It is not an installation or a backup of the original CHD.

`chdman verify` in MAME 0.289 can return zero after reporting a hash mismatch.
The importer requires both raw and overall success messages, not just exit status.
See [MAME's chdman documentation](https://docs.mamedev.org/tools/chdman.html).

## Regional status

| Edition | Boot executable | Native playback |
| --- | --- | --- |
| USA | SCUS_973.99 | Existing supported code signature |
| Japan | SLPM_670.10 | Recognized; runtime port still required |
| Supplied Asia ISO | SCUS_973.99 | Built and tested in opening gameplay; executable identical to USA |
| Other Asia serial | SCAJ_300.10 | Recognized; this serial has not been validated |
| Europe / Australia | SCES_531.33 | Inspected; experimental code generation only, runtime port incomplete |
| Europe alternate serial | SCES_515.33 | Recognized; no local disc/runtime validation |
| USA / Europe demos | SCUS_974.67 / SCED_534.31 | Explicitly excluded |

Serial recognition comes from the [PCSX2 game database](https://github.com/PCSX2/pcsx2/blob/master/bin/resources/GameIndex.yaml).
The `regions` table is a recognition catalog, not an allowlist for gameplay.
Unknown serials are also blocked. Code-compatible translations of the USA
executable retain their existing validation. Renaming an ELF or selecting another
file extension does not bypass the code-signature check.

The supplied Japan disc was inspected on 2026-11-02:

- ELF CRC: `CA052D22`; `.text` SHA-1: `8ed48ca88c73e7e340be3a8e7ff16b07825cb96c`.
- Japan `.text`: 1,690,724 bytes; USA `.text`: 1,686,436 bytes.
- About 13.75% of instructions match at the same offset across the shared range.
- Only 4 of 56 direct override/binding addresses have the same first 32 bytes.

These are preliminary difference measurements, not function-equivalence proof.
They rule out simply enabling the USA mapping. A real regional port needs its own
function map, recompiler configuration, verified override and global-data addresses,
diagnostic PCs, VU1 entry points, save isolation and visible gameplay/audio tests.
No regional code or media was copied into the repository. The supplied Asia ISO was subsequently built and tested because its executable
is byte-identical to USA. Japan and Europe gameplay support remains incomplete.
See [regional investigation](research/regional-port-2026-11-02.md).

## Checks

`python -I tools/disc/import_test.py` runs data-independent import checks. Add
`--chdman <executable>` for real DVD and legacy CD CHD round trips created from a
synthetic ISO. Tests cover equality of extracted bytes, cache reuse/repair,
concurrent writers, integrity failure, interrupted extraction, space checks,
source changes, unsupported tracks, per-file errors, regional gates and demos.
`tools/disc/prepare_test.py` covers disc normalization. Linux CI runs the real
synthetic round trips; Windows `verify` runs tests that need no downloaded tool.

The synthetic tests do not establish whole-game behavior or Linux/Steam Deck
runtime compatibility. Japan and Europe were identified from actual ISOs but were not run. The supplied
Asia ISO reached opening gameplay using the USA-compatible executable.
