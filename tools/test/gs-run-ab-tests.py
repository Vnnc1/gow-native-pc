"""Protect measurement boundaries and keep player cards out of benchmark disc roots."""
import importlib.util
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location("gs_run_ab", Path(__file__).with_name("gs-run-ab.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rows = [{"tag": "gow-frame", "elapsed_ms": t, "values": {
    "window": 5, "intervals": 100, "p50_ms": 10, "p95_ms": 20, "p99_ms": 30,
    "max_ms": 120, "over_33_33": 5, "over_50": 3, "over_100": 1}} for t in (62000, 65000, 70000)]
s = m.frame_summary(rows, 60)
assert s["frame_windows"] == 2 and s["intervals"] == 200 and s["over_100_per_1000"] == 10
assert s["median_window_p99_ms"] == 30
assert m.frame_summary([], 60)["median_window_p99_ms"] is None
assert m.gameplay_before_warmup("[24347 ms] [gow-pad2:test] gameplay start at 20.20 s", 60)
assert not m.gameplay_before_warmup("[64347 ms] [gow-pad2:test] gameplay start at 60.20 s", 60)
assert not m.gameplay_before_warmup("[20000 ms] menu", 60)
hosts = [{"type": "host_process", "elapsed_ms": t, "process_running": live,
          "process_counters_available": True, "cpu_percent_one_core": cpu}
         for t, live, cpu in [(58000, True, 999), (63000, True, 999), (68000, True, 100),
                             (70000, True, 200), (71000, False, 999)]]
assert m.host_cpu_summary(hosts, 60) == {"mean_cpu_percent_one_core": 900 / 7, "cpu_measured_seconds": 7}
assert m.host_cpu_summary([], 60)["mean_cpu_percent_one_core"] is None
gpu_spec = importlib.util.spec_from_file_location("gpu_sample", Path(__file__).with_name("windows_gpu_sample.py"))
gpu = importlib.util.module_from_spec(gpu_spec)
gpu_spec.loader.exec_module(gpu)
engine = "luid_0x0_0x1_phys_0_eng_0_engtype_3D"
copy = "luid_0x0_0x1_phys_0_eng_1_engtype_Copy"
result = gpu.summarize_engines([(f"pid_10_{engine}", 0, 80), (f"pid_10_{copy}", 1, 70),
                              (f"pid_100_{engine}", 0, 5), (f"pid_10_{engine}", 2, 100),
                              (f"pid_10_{copy}", 0, float("nan")), ("invalid", 0, 100)], 10)
assert result["available"] and result["child_busiest_engine_percent"] == 80
assert result["system_busiest_engine_percent"] == 85
assert result["child_engines_percent"][copy] == 70
assert gpu.summarize_engines([], 10)["child_busiest_engine_percent"] is None
assert gpu.summarize_engines([(f"pid_10_{engine}", 0, 0)], 10)["available"]
with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    source = root / "source"
    source.mkdir()
    for filename, content in (("disc.pak", b"asset"), ("ELF", b"elf"), ("TOC", b"toc"), ("Mcd001.ps2", b"never copy")):
        (source / filename).write_bytes(content)
    (source / "mc0").mkdir()
    (source / "mc0/save").write_bytes(b"never copy")
    (source / "mods").mkdir()
    (source / "mods/module.irx").write_bytes(b"module")
    profile = {"executable": {"name": "ELF"}, "disc": {"paks": ["disc.pak"], "toc": "TOC", "iop_modules_dir": "mods"}}
    before = m.save_inventory(root, source)
    target = root / "private"
    m.private_disc(source, target, profile)
    assert not (target / "Mcd001.ps2").exists() and not list((target / "mc0").iterdir())
    assert (target / "ELF").read_bytes() == b"elf" and (target / "mods/module.irx").is_file()
    assert m.save_inventory(root, source) == before
print("PASS: frame windows, GPU engine accounting/unavailability, private disc excludes player cards/directories")

# Reject different arenas, menus, missing samples and displacement across runs.
log = "\n".join(f"[{t} ms] [gow-player] t=1 g=1 obj=1 pos={x},2,3 hp=100 state=11 movie=0 zone=ship" for t,x in [(59000,999),(60000,1),(61000,2),(62000,3)])
scene = m.scene_summary(log, 60)
assert scene["samples"] == 3 and scene["position_min"] == [1,2,3]
assert m.same_scene([scene, scene], 2, ["ship"])
assert not m.same_scene([scene], 1, ["ship"])
assert not m.same_scene([scene], 2, ["other"])
assert not m.same_scene([m.scene_summary(log.replace("state=11", "state=10"),60)], 2, ["ship"])
assert not m.same_scene([m.scene_summary(log.replace("movie=0", "movie=1"),60)], 2, ["ship"])
assert not m.same_scene([m.scene_summary(log,61)], 2, ["ship"])
assert not m.same_scene([m.scene_summary("",60)], 2, ["ship"])
assert not m.same_scene([scene, {**scene, "position_min":[10,2,3], "position_max":[12,2,3]}], 2, ["ship"])
print("PASS: scene sample, state, movie, zone and cross-run position gates")

paused = m.scene_summary(log.replace("state=11", "state=13"),60)
assert not m.same_scene([paused], 2, ["ship"])
assert m.same_scene([paused], 2, ["ship"], [13])
assert not m.same_scene([scene, paused], 2, ["ship"], [13])
print("PASS: paused scenes require an explicit state contract")

markers = "[20000 ms] [gow-scene] phase=begin frame=240 t=17.500000\n[40000 ms] [gow-scene] phase=end frame=840 t=37.500000"
w = m.frame_window(markers,{"frame_begin":240,"frame_end":840})
assert w["guest_frames"] == 600 and w["guest_fps"] == 30
for bad in ["",markers.splitlines()[0],markers.replace("frame=240","frame=241"),markers.replace("37.500000","16.000000"),markers+"\n"+markers]:
    try: m.frame_window(bad,{"frame_begin":240,"frame_end":840})
    except ValueError: pass
    else: raise AssertionError("Invalid frame boundary accepted")
t={"samples":3,"gameplay_only":True,"zones":["ship"],"trajectory":{"240":[0,0,0],"300":[100,0,0],"360":[200,0,0]}}
assert m.same_trajectory([t,t],1,["ship"])
assert not m.same_trajectory([t,{**t,"trajectory":{**t["trajectory"],"300":[102,0,0]}}],1,["ship"])
assert not m.same_trajectory([t,{**t,"trajectory":{"240":[0,0,0]}}],1,["ship"])
print("PASS: exact frame boundaries and frame-matched trajectories")

a="[gow-scene-frame] intervals=360 skipped=0 p50_ms=16.0 p95_ms=20.0 p99_ms=30.0 max_ms=40.0 over_100=0\n[gow-scene-audio] requested=48000 missing=10"
assert m.aligned_metrics(a,360)["audio_missing"] == 10
for bad in [a.replace("skipped=0","skipped=1"), a.replace("intervals=360","intervals=359"),a.replace("requested=48000","requested=0"), ""]:
    try: m.aligned_metrics(bad,360)
    except ValueError: pass
    else: raise AssertionError("Incomplete aligned metrics accepted")
print("PASS: aligned frame/audio availability and skipped-frame rejection")

for mode in (*m.EFFICIENCY_FLAGS, "efficiency", "grouping"):
    off, on = m.efficiency_environment(mode, 0), m.efficiency_environment(mode, 1)
    assert all(v == "0" for v in off.values())
    assert sum(v == "1" for v in on.values()) == (3 if mode == "efficiency" else 0 if mode == "grouping" else 1)
events = [{"type":"process_exit", "code":0, "state":"completed"}]
assert m.completed_child({"state":"running"}, events, 0)
assert not m.completed_child({"exit_code":1}, events, 0)
assert not m.completed_child({}, events, 1)
assert not m.completed_child({}, [], 0)
assert not m.completed_child({}, events * 2, 0)
assert not m.completed_child({}, [{"type":"process_exit","code":1,"state":"completed"}], 0)
print("PASS: efficiency switches isolated; stale exit metadata requires unique successful event and helper exit")

assert gpu.cpu_rate(((10,1), 100, 0), ((10,1), 1000000100, 10000000)) == 100
assert gpu.cpu_rate(((10,1), 100, 0), ((10,1), 1000000100, 20000000)) == 200
assert gpu.cpu_rate(None, ((10,1), 100, 0)) is None
assert gpu.cpu_rate(((10,1), 100, 1), ((10,2), 200, 2)) is None
assert gpu.cpu_rate(((10,1), 100, 2), ((10,1), 200, 1)) is None
assert gpu.cpu_rate(((10,1), 100, 1), ((10,1), 100, 2)) is None
print("PASS: process CPU counter units, multicore time, unavailable/reset/reused PID handling")
