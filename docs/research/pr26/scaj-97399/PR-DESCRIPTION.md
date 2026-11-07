support the Asia SCAJ-97399 disc through one `code` field, without a second build

The SCAJ-97399 image boots the Japanese executable byte for byte: ELF CRC CA052D22,
`.text` SHA-1 8ed48ca88c73e7e340be3a8e7ff16b07825cb96c (1,690,724 bytes), the exact
values the profile already records for Japan. The disc is not USA-compatible and never
will be, and it does not need a build of its own either: the Japan build is the code it
runs. Its shell is Chinese - the first boot rendered "新游戏" / "确定" over the Japanese
logo - so the localization lives in the disc data while the executable stays Japanese.
The profile's language_hints only see the Japanese build's internal English strings and
return "en", which is why the region records `language = "zh"` by hand.

The profile could not say any of that. `[[regions]]` tied disc identity to build
identity, so a recognised serial without a build of its own was reported as
"region_not_ported" and the launcher refused it, even when another region's validated
build was byte-identical. Renaming the ELF is not a way out and is not what this does:
the bytes decide.

Second, a regional disc whose build is already registered stayed unsupported as well:
identify.py never emitted `playable`, and that is the field the launcher's Install page
reads to offer an edition, so the disc kept its "not registered" line after the build was
registered. This patch makes identify.py look up the machine-local registry
(data/<game>/regional-builds.json, written by register_region.py) and report
playable/regional_installed only for a build whose runner and prepared executable still
exist and whose measured CRC and .text match. The USA `compatible` flag is untouched: a
regional disc never enters the USA generation path.

The changes:
- games/gow1/game.toml: the asia-97399 entry with the measurement and the Chinese shell.
- tools/disc/identify.py: `code`/`code_label`; reason_code "region_alias" when the bytes
  match another region's recorded identity but no build is registered, a mismatch message
  when a serial does not match its recorded identity; playable/regional_installed/
  reason_code "regional_installed"/regional_build when a registered build matches. A
  registry entry whose files are gone is not offered: it records files, not promises.
- tools/disc/prepare.py: extract and normalise a `code` disc, link its executable under
  the name the named build keys on (the runtime registers its overrides and gates the
  native integration by that file name), print the register_region.py command, and keep
  the disc out of languages.json - that manifest feeds the USA pipeline and the primary
  installation's Play list.
- tools/pipeline/register_region.py: register the disc against the named region's
  overlay and measured identity, and record `code` in the registry.
- docs/disc-import.md: the regional table row and the rule.
- tools/disc/import_test.py, tools/disc/prepare_test.py: data-free regressions, including
  a registered build that makes the disc playable and one whose runner is gone.

Verified on the real image (tested Windows machine, 2026-11-03), which means the Japan
edition was built here to run it:

- Japan build: isolated snapshot of the pinned runtime with regions/japan/runtime.patch,
  regional codegen (6416 functions, 6340 recompiled, 0 decode failures, 0 unhandled
  instructions, 0 errors), clang + Ninja Release, portable x86-64-v2, no LTCG, no PGO.
- register_region.py registered that build for this region and wrote the registry entry.
- The disc boots to its own title screen: the display-buffer dump shows the Chinese shell
  over the Japanese logo, the log has no "no exact recompiled function" and no GL error.
- identify.py with that registry present: playable true, regional_installed true,
  reason_code regional_installed, regional_build asia-97399, label "God of War (Asia,
  SCAJ-97399, Chinese)", language zh, compatible false. Without the registry (or with the
  runner removed) the same disc reports reason_code region_alias and offers nothing.
- Frame rate there, i3-4170 + HD 4400, in-process VU1 JIT, no recorded VU1/IOP native
  code and no PGO: 8.4 guest fps at 1x internal scale, 24.5 at 0.5x (GS-bound).
- prepare.py with its own --data: 16 files, layer1 2082352, SCAJ_973.99 also present as
  SLPM_670.10 (hard link, same inode and bytes), no languages.json written.
- register_region.py with the disc's own name: "Regional ELF identity mismatch"; with the
  build's name: passes the overlay and identity checks and writes the entry.
- tools/disc/prepare_test.py: 4 tests OK. tools/disc/import_test.py: 16 tests OK
  (6 skipped, no chdman).

Not verified, and deliberately not claimed: the launcher UI was not clicked through (the
fields above are exactly what its Install page reads); gameplay past the title screen;
AOT VU1/IOP capture and PGO are not in this build, and regional automatic AOT/PGO is
disabled by design; Windows only.

Usage, once the Japan edition is built and registered:

  python -I tools/disc/prepare.py --game gow1 --data <its own data directory> <iso>
  python -I tools/pipeline/register_region.py --region asia-97399 \
      --runner <japan runner> --elf <that folder>/SLPM_670.10 \
      --data <its own data directory>
