# PR 26 material kept for reference

These files came with [PR 26](https://github.com/Vnnc1/gow-native-pc/pull/26). They were moved out of the
repository root during the integration ([../pr26-integration.md](../pr26-integration.md)). None of them is applied
or run by the pipeline.

- `bug-audit-2026-11-05.md`: the contributor's audit notes.
- `*.zh-CN.md`: the contributor's design write-ups (static recompilation, the launcher effect switches).
- `low-spec-renderer-retired.md`: the retired "low-spec tier" launcher patch. Its replacements (scale below 1x,
  effect switches) are in the launcher.
- `scaj-97399/`: Asia SCAJ-97399 disc support through the Japan build. Not integrated: it targets the contributor's
  own regional snapshot. `play-asia.cmd.example` contains the contributor's local paths (`C:\gow-jpn-data`,
  `C:\gow-build-jpn`) and is an example only.
- `deferred-fix-chore-patches/`: fix-chore opt-in candidates (67, 71, 72 sampler, 73 shader, 74, 75) and their
  tests. They are not in the chain because they conflict with the PR's renderer. To port one, rebase it, put its
  test back in `tools/test/guest-calls.cmake` and `verify`, and give it a `zzz-` name after the patches it
  depends on.
