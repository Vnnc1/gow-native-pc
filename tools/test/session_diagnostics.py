"""Integration checks for the deployed Qt session collector, without game files.

python -I tools/test/session_diagnostics.py <gow-session.exe>
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
import ctypes
from contextlib import contextmanager

HELPER = Path(sys.argv.pop(1)).resolve()


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gow-report-test-")
        self.root = Path(self.temp.name)
        self.session = self.root / "session"
        self.session.mkdir()
        (self.session / "session.json").write_text(json.dumps({"schema": 1, "id": "fixture", "state": "prepared"}))
        self.env = os.environ.copy()
        self.env["GOW_TEST_SECRET"] = "SECRET_MUST_NOT_APPEAR"
        self.env["GOW_PERF_DIAG"] = "frames"
        self.child = self.root / "child.py"
        self.process = None

    def test_qte_auto_environment_reported(self):
        self.env["GOW_QTE_AUTO"] = "1"
        self.start("pass\n")
        self.assertEqual(self.process.wait(timeout=20), 0)
        self.assertEqual(self.metadata()["runtime_environment"]["GOW_QTE_AUTO"], "1")

    def test_menu_audio_report_and_private_bridge(self):
        self.env.update(GOW_AUDIO_VOLUME="65", GOW_AUDIO_MUTE="1", GOW_MENU_SETTINGS=str(self.root/"PRIVATE_BRIDGE"))
        self.start("pass\n")
        self.assertEqual(self.process.wait(timeout=20), 0)
        env=self.metadata()["runtime_environment"]
        self.assertEqual(env["GOW_AUDIO_VOLUME"], "65")
        self.assertEqual(env["GOW_AUDIO_MUTE"], "1")
        self.assertNotIn("GOW_MENU_SETTINGS", env)

    def tearDown(self):
        if self.process and self.process.poll() is None:
            (self.session / "stop.request").write_text("stop")
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.temp.cleanup()

    def start(self, source, runner=None):
        self.child.write_text(source, encoding="utf-8")
        self.process = subprocess.Popen([str(HELPER), str(self.session), str(runner or sys.executable), str(self.child), str(self.root)], env=self.env)
        return self.process

    def metadata(self):
        # The collector replaces session.json atomically; on Windows a read during the rename is denied briefly.
        for attempt in range(50):
            try:
                return json.loads((self.session / "session.json").read_text(encoding="utf-8"))
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.02)

    @contextmanager
    def locked_final_metadata(self):
        self.start("from pathlib import Path\nimport time\nwhile not (Path(__file__).parent/'exit-now').exists(): time.sleep(.01)\n")
        deadline = time.monotonic() + 10
        while self.metadata().get('state') != 'running':
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.02)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        # Allow reading/writing but deny atomic replacement of this file.
        handle = kernel.CreateFileW(str(self.session / 'session.json'), 0x80000000, 3, None, 3, 128, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            (self.root / 'exit-now').touch()
            deadline = time.monotonic() + 10
            while '"process_exit"' not in (self.session / 'events.jsonl').read_text():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.02)
            yield
        finally:
            kernel.CloseHandle(handle)

    @unittest.skipUnless(os.name == 'nt', 'Windows atomic-replacement sharing violation')
    def test_final_metadata_retries_transient_lock(self):
        with self.locked_final_metadata():
            time.sleep(.2)
        self.process.wait(timeout=10)
        self.assertEqual(self.metadata()['state'], 'completed')
        self.assertEqual(self.metadata()['exit_code'], 0)
        self.assertTrue(self.metadata()['write_failure'])

    @unittest.skipUnless(os.name == 'nt', 'Windows atomic-replacement sharing violation')
    def test_final_metadata_persistent_lock_recovered_on_export(self):
        with self.locked_final_metadata():
            self.process.wait(timeout=10)
            self.assertEqual(self.metadata()['state'], 'running')
            summary = json.loads((self.session / 'summary.json').read_text())
            self.assertNotIn('session_not_completed', summary['flags'])
            self.assertIn('final_metadata_incomplete', summary['flags'])
        archive = self.root / 'recovered.zip'
        subprocess.run([str(HELPER), '--export', str(self.session), str(archive)], check=True, timeout=15)
        with zipfile.ZipFile(archive) as z:
            meta = json.loads(z.read('session.json'))
            self.assertEqual((meta['state'], meta['exit_code']), ('completed', 0))
            self.assertTrue(meta['final_metadata_incomplete'])
            self.assertIn('metadata_persist_failed', z.read('events.jsonl').decode())
        self.assertEqual(self.metadata()['state'], 'running')  # Preserve the original evidence.

    def test_recovered_exit_requires_valid_latest_terminal_event(self):
        terminal = {'type': 'process_exit', 'state': 'completed', 'code': 0,
                    'utc': '2026-11-09T16:07:01.113Z', 'elapsed_ms': 500}
        cases = [
            ('normal', [terminal], 'completed', 0),
            ('nonzero', [dict(terminal, state='nonzero_exit', code=7)], 'nonzero_exit', 7),
            ('crash', [dict(terminal, state='crashed', code=-1073741819)], 'crashed', -1073741819),
            ('failed-start', [dict(terminal, state='failed_to_start', code=-1)], 'failed_to_start', -1),
            ('new-start', [terminal, {'type': 'process_started'}], 'running', None),
            ('missing', [], 'running', None),
            ('wrong-code', [dict(terminal, code=7)], 'running', None),
            ('string-code', [dict(terminal, code='0')], 'running', None),
            ('fraction-code', [dict(terminal, code=.5)], 'running', None),
            ('missing-time', [dict(terminal, utc='')], 'running', None),
            ('negative-time', [dict(terminal, elapsed_ms=-1)], 'running', None),
            ('invalid-latest', [terminal, dict(terminal, state='unknown')], 'running', None),
        ]
        for name, events, state, code in cases:
            with self.subTest(name=name):
                (self.session / 'session.json').write_text(json.dumps({'schema': 1, 'state': 'running'}))
                (self.session / 'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
                archive = self.root / (name + '.zip')
                subprocess.run([str(HELPER), '--export', str(self.session), str(archive)], check=True, timeout=15)
                with zipfile.ZipFile(archive) as z:
                    meta = json.loads(z.read('session.json'))
                    summary = json.loads(z.read('summary.json'))
                    self.assertEqual(meta['state'], state)
                    self.assertEqual(summary['state'], state)
                    self.assertEqual(meta.get('exit_code'), code)
                    self.assertEqual(meta.get('final_metadata_incomplete', False), code is not None)
                    self.assertEqual('session_not_completed' in summary['flags'], state != 'completed')
                self.assertEqual(self.metadata()['state'], 'running')

    def test_exit_metrics_redaction_and_export(self):
        self.start("import sys,time\nprint('[gow-perf] guest_flip_hz=59.5 host_hz=120.0 ee_ms=0',flush=True)\nprint('[gow-present] window=5 polls=300 fresh=12 repeated=288 unavailable=0 blank=0 skipped=40 acquire_hz=2.4 max_hold_ms=900',flush=True)\nprint('[audio-stats] requested=240000 missing=12 rate<=1.025 level=12-450',flush=True)\nprint('[vu1n] nativePairs=123 nativeBlocks=24 missBlocks=7 laneFails=0',flush=True)\nprint('[vu1x] compiled=12 unsupported=1 codeKB=20 avgCompileUs=4.0',flush=True)\nprint('[gow-queue] queue=2 window=5 waits=3 wait_ms=12.5 max_ms=7 queued_peak=8 final=0',flush=True)\nprint('error '+__file__+' person@example.com',flush=True)\ntime.sleep(5.6)\nsys.exit(7)\n").wait(timeout=20)
        meta = self.metadata()
        self.assertEqual(meta["state"], "nonzero_exit")
        self.assertEqual(meta["exit_code"], 7)
        self.assertTrue(meta["runner_sha256"])
        self.assertEqual(meta["observations"]["guest_fps_min_window"], 59.5)
        self.assertEqual(meta["observations"]["audio_missing_frames"], 12)
        self.assertEqual(meta["observations"]["native_missBlocks_max_counter"], 7)
        rows = [json.loads(x) for x in (self.session / "metrics.jsonl").read_text().splitlines()]
        self.assertTrue(any(r.get("values", {}).get("guest_flip_hz") == 59.5 for r in rows))
        perf = next(r for r in rows if r.get("tag") == "gow-perf")
        self.assertFalse(perf["timing_scopes_enabled"])
        self.assertNotIn("ee_ms", perf["values"])
        queue = next(r["values"] for r in rows if r.get("tag") == "gow-queue")
        self.assertEqual((queue["queue"], queue["waits"], queue["wait_ms"], queue["max_ms"], queue["queued_peak"]), (2, 3, 12.5, 7, 8))
        present = next(r["values"] for r in rows if r.get("tag") == "gow-present")
        self.assertEqual((present["fresh"], present["repeated"], present["acquire_hz"], present["max_hold_ms"]), (12, 288, 2.4, 900))
        self.assertEqual(meta["observations"]["guest_fps_min_window"], 59.5)
        audio = next(r["values"] for r in rows if r.get("tag") == "audio-stats")
        self.assertEqual((audio["missing"], audio["rate_max"], audio["level_min"], audio["level_max"]), (12, 1.025, 12, 450))
        native = next(r["values"] for r in rows if r.get("tag") == "vu1n")
        jit = next(r["values"] for r in rows if r.get("tag") == "vu1x")
        self.assertEqual((native["nativePairs"], native["missBlocks"], native["laneFails"]), (123, 7, 0))
        self.assertEqual((jit["compiled"], jit["unsupported"], jit["avgCompileUs"]), (12, 1, 4.0))
        self.assertTrue(any("cpu_percent_one_core" in r for r in rows))
        memory_metric = "private_bytes" if os.name == 'nt' else "working_set_bytes"
        self.assertTrue(any(r.get(memory_metric, 0) > 0 for r in rows))
        (self.session / "private.ps2").write_text("SAVE_MUST_NOT_APPEAR")
        (self.session / "private.iso").write_text("ISO_MUST_NOT_APPEAR")
        archive = self.root / "report.zip"
        subprocess.run([str(HELPER), "--export", str(self.session), str(archive)], check=True, timeout=15)
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("README.txt", z.namelist())
            self.assertNotIn("private.ps2", z.namelist())
            text = b"\n".join(z.read(n) for n in z.namelist()).decode("utf-8")
        for secret in (str(self.root), "person@example.com", "SECRET_MUST_NOT_APPEAR", "SAVE_MUST_NOT_APPEAR", "ISO_MUST_NOT_APPEAR"):
            self.assertNotIn(secret, text)

    def test_sync_settings_and_metrics(self):
        self.env.update(GOW_SYNC_DIAG="1", GOW_VU1_EARLY_FINISH="0")
        self.start("print('[gow-sync-config] early_finish=0 worker=1 timing=1',flush=True)\nprint('[gow-sync] site=0 syncs=4 worker_waits=1 stage_waits=2 worker_ms=12.5 stage_ms=31.25 queue_peak=3 final=1',flush=True)\n").wait(timeout=15)
        self.assertEqual(self.metadata()["runtime_environment"]["GOW_VU1_EARLY_FINISH"], "0")
        rows = [json.loads(x) for x in (self.session / "metrics.jsonl").read_text().splitlines()]
        config = next(r["values"] for r in rows if r.get("tag") == "gow-sync-config")
        sync = next(r["values"] for r in rows if r.get("tag") == "gow-sync")
        self.assertEqual(config["early_finish"], 0)
        self.assertEqual((sync["worker_ms"], sync["stage_ms"], sync["stage_waits"]), (12.5, 31.25, 2))

    def test_marker_and_requested_stop(self):
        self.start("import time\nprint('started',flush=True)\ntime.sleep(60)\n")
        time.sleep(1)
        (self.session / "marker.request").write_text(json.dumps({"note": "freeze near ship", "requested_utc": "fixture"}))
        time.sleep(1)
        (self.session / "stop.request").write_text("stop")
        self.process.wait(timeout=15)
        meta = self.metadata()
        self.assertTrue(meta["stop_requested"])
        events = [json.loads(x) for x in (self.session / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any(e.get("type") == "player_marker" and e.get("note") == "freeze near ship" for e in events))
        self.assertTrue(any(e.get("type") == "process_exit" for e in events))

    def test_failed_start(self):
        self.start("", self.root / "missing.exe").wait(timeout=10)
        self.assertEqual(self.metadata()["state"], "failed_to_start")

    def test_crash_exit(self):
        if os.name == 'nt':
            child = "import ctypes\nk=ctypes.windll.kernel32\nk.GetCurrentProcess.restype=ctypes.c_void_p\nk.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint]\nk.TerminateProcess(k.GetCurrentProcess(),0xC0000005)\n"
        else:
            child = "import os,signal,resource\nresource.setrlimit(resource.RLIMIT_CORE,(0,0))\nos.kill(os.getpid(),signal.SIGSEGV)\n"
        self.start(child).wait(timeout=10)
        self.assertEqual(self.metadata()["state"], "crashed")
        self.assertEqual(self.metadata()["exit_code_hex"], "c0000005" if os.name == 'nt' else "b")

    def test_log_rotation_and_incomplete_lines(self):
        self.start("import sys\nfor i in range(16000): print('line '+str(i)+' '+('x'*1000))\nsys.stdout.write('tail-without-newline')\n").wait(timeout=30)
        self.assertEqual(self.metadata()["state"], "completed")
        self.assertGreaterEqual(self.metadata()["log_rotations"], 3)
        for name in ("runtime.log", "runtime.1.log", "runtime.2.log"):
            self.assertLessEqual((self.session / name).stat().st_size, 4 * 1024 * 1024)
        self.assertIn("tail-without-newline", (self.session / "runtime.log").read_text())

    def test_oversized_export_rejected(self):
        (self.session / "runtime.log").write_bytes(b"x" * (4 * 1024 * 1024 + 1))
        output = self.root / "bad.zip"
        result = subprocess.run([str(HELPER), "--export", str(self.session), str(output)], timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_summary_windows_missing_metrics_and_queue_totals(self):
        rows = [
            {"tag": "gow-perf", "elapsed_ms": end, "values": {"window": window, "guest_flip_hz": fps}}
            for end, window, fps in [(32000, 5, 99), (35000, 5, 60), (45000, 10, 30), (50000, 5, 0)]
        ]
        rows += [
            {"tag": "gow-queue", "values": {"queue": 1, "enabled": 1}},
            {"tag": "gow-queue", "values": {"queue": 1, "waits": 2, "wait_ms": 3, "max_ms": 2, "queued_peak": 4}},
            {"tag": "gow-queue", "values": {"queue": 1, "waits": 1, "wait_ms": 5, "max_ms": 5, "queued_peak": 2, "final": 1}},
            {"type": "host_process", "process_running": True, "elapsed_ms": 40000,
             "ac_line_status": 0, "system_available_ram_bytes": 1024, "cpu_percent_one_core": 150},
        ]
        (self.session / "metrics.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        archive = self.root / "summary.zip"
        subprocess.run([str(HELPER), "--export", str(self.session), str(archive)], check=True, timeout=15)
        with zipfile.ZipFile(archive) as z:
            summary = json.loads(z.read("summary.json"))
            human = z.read("RESUMO.txt").decode("utf-8")
        self.assertEqual(summary["guest_fps_mean"], 30)
        self.assertEqual(summary["guest_fps_min_window"], 0)
        self.assertEqual(summary["fps_windows"], 3)
        self.assertEqual(summary["measured_seconds"], 20)
        self.assertEqual(summary["queues_whole_session"]["1"], {"waits": 3, "wait_ms": 8, "max_ms": 5, "queued_peak": 4})
        self.assertEqual(summary["scoped_ms_after_warmup"], {})
        for key in ("native_miss_blocks", "jit_unsupported_max_counter", "audio_missing_frames", "guest_intervals_over_100ms"):
            self.assertNotIn(key, summary)
        self.assertIn("battery_power_observed", summary["flags"])
        self.assertIn("low_available_ram_observed", summary["flags"])
        self.assertIn("Uso na bateria detectado", human)
        self.assertIn("indisponível", human)

    def test_summary_renderer_and_counters(self):
        self.start("print('[gs-hw] render-target renderer ready, scale 1.00 (Test GPU)',flush=True)\nprint('[vu1n] missBlocks=3',flush=True)\nprint('[vu1n] missBlocks=2',flush=True)\nprint('[vu1x] unsupported=2',flush=True)\nprint('[vu1x] unsupported=4',flush=True)\n").wait(timeout=15)
        self.assertEqual(self.metadata()["gs_renderer"], "Test GPU")
        summary = json.loads((self.session / "summary.json").read_text())
        self.assertEqual(summary["native_miss_blocks"], 5)
        self.assertEqual(summary["jit_unsupported_max_counter"], 4)

    def test_texture_cache_metrics(self):
        self.env["GOW_GS_HW_STATS"] = "1"
        self.start("print('[gs-cache] bytes=67108864 budget=134217728 evictions=12 reuses=300',flush=True)\n").wait(timeout=15)
        self.assertEqual(self.metadata()["runtime_environment"]["GOW_GS_HW_STATS"], "1")
        rows = [json.loads(line) for line in (self.session / "metrics.jsonl").read_text().splitlines()]
        row = next(r for r in rows if r.get("tag") == "gs-cache")
        self.assertEqual(row["values"], {"bytes": 67108864, "budget": 134217728, "evictions": 12, "reuses": 300})

    def test_collector_survives_parent_exit(self):
        self.child.write_text("import time\nprint('detached start',flush=True)\ntime.sleep(1)\nprint('detached end',flush=True)\n")
        args = [str(HELPER), str(self.session), sys.executable, str(self.child), str(self.root)]
        subprocess.run([sys.executable, "-c", "import subprocess,sys,json; subprocess.Popen(json.loads(sys.argv[1]))", json.dumps(args)], check=True, timeout=5)
        for _ in range(100):
            if self.metadata().get("state") == "completed":
                break
            time.sleep(0.1)
        self.assertEqual(self.metadata()["state"], "completed")
        self.assertIn("detached end", (self.session / "runtime.log").read_text())


if __name__ == "__main__":
    unittest.main()
