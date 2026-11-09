# Collector final-state persistence and recovery

Branch: `fix-chore`, after `84ccd80`. This fixes report state, not game timing.

## Failure and reproduction

The earlier `window-fix-visible` control closed its window and emitted
`process_exit` with code 0, but `session.json` still said `running`. The collector
called `QSaveFile::commit()` only once for its final metadata. Failure set an
in-memory flag, then the process exited. `writeSummary` re-read the stale file,
so the human summary, exports and diagnostic frontend could retain the old state.

A Windows file handle permitting reads/writes but denying deletion reproduces
the atomic-replacement failure. The child waits for a test signal; the test locks
`session.json`, releases the child, observes the exit event, and then either
releases the lock after 200 ms or keeps it until the collector exits. Both tests
fail against the deployed baseline for the expected stale-state assertions.
This identifies a real persistence defect; the particular process that prevented
the original write was not recorded and is not attributed to antivirus or another
application without evidence.

## Change

- Final metadata persistence retries at 50 ms intervals, at most 20 retries
  after the first attempt (about one second). This occurs only after child exit;
  gameplay collection does not acquire a new delay. A successful retry retains
  `write_failure=true` to disclose that a write failed.
- If persistence still fails, the bounded event log records
  `metadata_persist_failed`. The collector preserves the actual child exit result.
- A shared metadata reader recovers a terminal state only from a valid recorded
  `process_exit` for the latest process start, with a supported state, integer
  code, valid timestamp and nonnegative elapsed time. It reads at most 1 MiB
  per input file and rejects symlink inputs. A later start invalidates an older
  exit; silence or an old heartbeat never becomes a successful exit.
- Summaries, the normal launcher's exit handling, the private diagnostic UI and
  ZIP exports use that reader. JSON summaries now expose state and, when known,
  exit code. Export uses one metadata snapshot for both summary and session data.
- Recovery sets `final_metadata_incomplete=true` and adds an explicit summary
  warning. Original local metadata is retained; a recovered ZIP contains the
  reconciled metadata plus original events. Retention still uses raw metadata,
  so an incomplete original report is not newly eligible for automatic pruning.

Permanent access failure cannot make a locked file writable. In that case the
on-disk original may still say `running`, but the UI, summary and export recover
the recorded outcome and disclose the incomplete metadata. Missing, malformed
or oversized exit evidence remains unresolved rather than inventing completion.

## Validation

Windows, pinned Qt 6.8.3 / LLVM 20261020. Evidence and build logs are retained
under ignored `data/issue-triage/collector-final`.

- Deployed collector suite: **14 tests passed**, including transient/persistent
  replacement denial and 12 recovery cases covering normal/nonzero/crash/failed
  startup, a subsequent process start, missing exit, invalid codes/times and an
  invalid last exit. Existing rotation, limits, redaction, metric parsing,
  requested stop and detached lifetime tests remain in the suite.
- The original stale report was copied to a private fixture and exported:
  metadata and summary both report `completed`/0, incomplete metadata is flagged,
  and the original fixture's `session.json` hash remains unchanged.
- Normal launcher, collector and private diagnostic frontend rebuilt. Initial
  build invocations missing Qt runtime DLLs on PATH and an installer configure
  invocation with unnormalized backslashes failed; corrected invocations use
  the pinned tools. These are retained environment/setup failures, not passing
  checks. Initial test-harness attempts with missing DLLs/a wrong signal-file
  directory were corrected before the valid baseline failure comparison.
- Packaged diagnostic UI and real-game smoke passed. The game reached
  `state=11 levelReady=1`, closed without forced termination, and both metadata
  and summary reported `completed`/0. Export passed its content checks; cards,
  discs and captures were absent. The original card hash and previous diagnostic
  game selection were preserved. This was a functional run, not an FPS benchmark.
- Final packaged UI smoke with the historical stale report regenerated its old
  human/JSON summary as `completed`/0, kept the recovery warning, and left the
  original metadata unchanged. The test restored the previous latest-report
  pointer and removed only its own temporary fixture.
- Final diagnostic setup payload verification passed: 1,413 files, 10 LZMS
  blocks, 162,008,885 unpacked bytes, all matching staging. No installation or
  uninstallation was performed. Setup SHA-256:
  `0aa4555947d3e24775fbd417170c09b5e6d120e924b2914710a610bf0f15ccc1`.

Collector baseline SHA-256:
`21691e72be3cb52885d96ffc53a09178adb30d860a3a264fb9fac4d06659bd7d`.
Corrected collector SHA-256:
`6cba14495c4946b804ccecc1e786de5dbc5fbc39e4adb1ad4b782a16fa63647c`.

No public package was published, installed player files/cards were not replaced,
and no frame-rate or graphics-driver improvement is claimed. Linux and full
pipeline verify were not run; the exercised platform was Windows. Permanent
loss of both metadata writes and exit evidence cannot be reconstructed reliably.
