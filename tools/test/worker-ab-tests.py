"""Check benchmark window boundaries and instrumentation separation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("worker_ab", Path(__file__).with_name("worker-ab.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rows = [{"tag": "gow-perf", "elapsed_ms": t, "values": {"window": w, "guest_flip_hz": fps}}
        for t, w, fps in ((62000, 5, 60), (65000, 5, 0), (75000, 10, 30))]
result = m.summarize(rows, 60)
assert result["windows"] == 2 and result["guest_fps"] == 20 and result["min_window_fps"] == 0
profile = {"diagnostics": {"frame_pc": "0x123"}, "optimize": {"pad_script": "1:x"}}
for mode in ("fps", "timing", "capture"):
    args = SimpleNamespace(mode=mode, scale=1, hidden=False, warmup=60)
    e = m.environment(profile, Path("private-run"), args, 0)
    assert e["GOW_VU1_EARLY_FINISH"] == "0" and e["PS2X_GS_ESCALA_DINAMICA"] == "0"
    assert ("GOW_SYNC_DIAG" in e) == (mode == "timing")
    assert ("GOW_VU1_TASK_RECORD" in e) == (mode == "capture")
    assert "GOW_VU1N_VERIFY" not in e
    assert e["GOW_PERF_DIAG"] == ("1" if mode == "timing" else "frames")
print("PASS: complete warm windows, zero FPS retained, modes isolated, fixed graphics, private card")
