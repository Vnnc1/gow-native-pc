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

    def test_exit_metrics_redaction_and_export(self):
        self.start("import sys,time\nprint('[gow-perf] guest_flip_hz=59.5 host_hz=120.0 ee_ms=0',flush=True)\nprint('[audio-stats] requested=240000 missing=12 rate<=1.025 level=12-450',flush=True)\nprint('[vu1n] nativePairs=123 nativeBlocks=24 missBlocks=7 laneFails=0',flush=True)\nprint('[vu1x] compiled=12 unsupported=1 codeKB=20 avgCompileUs=4.0',flush=True)\nprint('error '+__file__+' person@example.com',flush=True)\ntime.sleep(5.6)\nsys.exit(7)\n").wait(timeout=20)
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
        audio = next(r["values"] for r in rows if r.get("tag") == "audio-stats")
        self.assertEqual((audio["missing"], audio["rate_max"], audio["level_min"], audio["level_max"]), (12, 1.025, 12, 450))
        native = next(r["values"] for r in rows if r.get("tag") == "vu1n")
        jit = next(r["values"] for r in rows if r.get("tag") == "vu1x")
        self.assertEqual((native["nativePairs"], native["missBlocks"], native["laneFails"]), (123, 7, 0))
        self.assertEqual((jit["compiled"], jit["unsupported"], jit["avgCompileUs"]), (12, 1, 4.0))
        self.assertTrue(any("cpu_percent_one_core" in r for r in rows))
        self.assertTrue(any(r.get("private_bytes", 0) > 0 for r in rows))
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
        self.start("import ctypes\nk=ctypes.windll.kernel32\nk.GetCurrentProcess.restype=ctypes.c_void_p\nk.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint]\nk.TerminateProcess(k.GetCurrentProcess(),0xC0000005)\n").wait(timeout=10)
        self.assertEqual(self.metadata()["state"], "crashed")
        self.assertEqual(self.metadata()["exit_code_hex"], "c0000005")

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
