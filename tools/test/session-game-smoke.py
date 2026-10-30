"""Exercise the deployed report collector with a prepared game and a private memory card.

No source ISO, player saves, launcher preferences or boot profile are changed.
This is a functional smoke test, not a performance benchmark.
"""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--game", default="gow1")
parser.add_argument("--seconds", type=int, default=100)
parser.add_argument("--visible", action="store_true", help="Show gameplay with audio enabled")
parser.add_argument("--detailed", action="store_true", help="Enable intrusive per-call timing; not an FPS benchmark")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
profile = json.loads(subprocess.check_output([sys.executable, "-I", str(root / "tools/pipeline/profile.py"), args.game]))
data = root / "data" / args.game
runner = Path((root / "data/build-root.txt").read_text().strip() + "-clang") / "ps2xRuntime/ps2EntryRunner.exe"
elf = json.loads((data / "languages.json").read_text(encoding="utf-8"))["recompile_elf"]
helper = root / "launcher/build-clang/deploy/gow-session.exe"
output = data / "logs" / time.strftime("session-game-%Y%m%d-%H%M%S")
output.mkdir()
session = output / "session"
session.mkdir()
(session / "session.json").write_text(json.dumps({"schema": 1, "id": output.name, "state": "prepared", "settings": {
    "test": "scripted input, private card, audio enabled", "visible": args.visible,
    "diagnostics": "detailed" if args.detailed else "frames", "seconds": args.seconds}}))
env = {k: v for k, v in os.environ.items() if not k.startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
env.update(GOW_PAD_TEST="1", GOW_FAST_BOOT="1", GOW_SKIP_FMV="1", GOW_WINDOW_HIDDEN="0" if args.visible else "1",
           GOW_PAD_GUION=profile["optimize"]["pad_script"], GOW_PAD_TEST_NO_CAPTURE="1",
           GOW_MC0=str(output / "card.ps2"), GOW_VU1N_X64="1", GOW_VU1N_VERIFY="2000",
           GOW_PERF_DIAG="1" if args.detailed else "frames", GOW_FRAME_DIAG="1", GOW_PERF_FRAME_PC=profile["diagnostics"]["frame_pc"],
           GOW_AUDIO_STATS="1", GOW_IOP_DRIFT="1", GOW_VU1N_DIAG="1",
           GOW_VU1_SIN_COMPILAR="1", GOW_VU1_CAPTURE_MISSES="0", PS2X_GS_HW="1", PS2X_GS_WORKER="1",
           GOW_GS_FINISH_ASINCRONO="1", PS2X_GS_HW_SCALE="1", PS2X_GS_ESCALA="1", PS2X_GS_ESCALA_DINAMICA="0",
           TOBIICHI_ANCHO="1280", TOBIICHI_ALTO="720")
process = subprocess.Popen([str(helper), str(session), str(runner), elf, str(root)], cwd=output, env=env)
try:
    for elapsed in range(args.seconds):
        if process.poll() is not None:
            break
        if elapsed == 75:
            (session / "marker.request").write_text(json.dumps({"note": "Automated gameplay marker", "requested_utc": "test"}))
        time.sleep(1)
finally:
    if process.poll() is None:
        (session / "stop.request").write_text("stop")
        process.wait(timeout=20)
meta = json.loads((session / "session.json").read_text(encoding="utf-8"))
log = "\n".join(p.read_text(encoding="utf-8") for p in session.glob("*.log"))
metrics = [json.loads(line) for line in (session / "metrics.jsonl").read_text().splitlines()]
events = [json.loads(line) for line in (session / "events.jsonl").read_text().splitlines()]
archive = output / "report.zip"
subprocess.run([str(helper), "--export", str(session), str(archive)], check=True, timeout=20)
with zipfile.ZipFile(archive) as report:
    assert report.testzip() is None
    assert not any(name.endswith((".ps2", ".iso", ".ppm")) for name in report.namelist())
checks = {"exit_zero": meta["exit_code"] == 0, "gameplay": bool(re.search(r"state=11\b.*levelReady=1", log)),
          "vu1_parity": "2000 runs checked, 0 mismatches" in log,
          "frame_distribution": any(r.get("tag") == "gow-frame" and r.get("values", {}).get("p99_ms", 0) > 0 for r in metrics),
          "host_memory": any(r.get("private_bytes", 0) > 0 for r in metrics),
          "audio_metrics": any(r.get("tag") == "audio-stats" and "requested" in r.get("values", {}) for r in metrics),
          "iop_metrics": any(r.get("tag") == "iop-drift" and "advanced" in r.get("values", {}) for r in metrics),
          "native_metrics": any(r.get("tag") == "vu1n" and "missBlocks" in r.get("values", {}) for r in metrics),
          "jit_metrics": any(r.get("tag") == "vu1x" and "compiled" in r.get("values", {}) for r in metrics),
          "player_marker": any(r.get("type") == "player_marker" for r in events),
          "graceful_stop": not any(r.get("type") == "forced_termination" for r in events)}
(output / "checks.json").write_text(json.dumps(checks, indent=2))
print(json.dumps({"directory": str(output), "checks": checks}, indent=2))
assert all(checks.values()), "Session gameplay validation failed"
