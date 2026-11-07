"""Compare runtime candidates or internal resolution with private disc/card roots.

Uses the existing worker comparison's clean environment and complete-window rules.
Real-time input is repeatable, but animated scenes are not frame-identical replays.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location("worker_ab", Path(__file__).with_name("worker-ab.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def private_disc(source, target, profile):
    """Copy executable/index/modules; only known, read-only PAK inputs are hardlinked."""
    target.mkdir()
    paks = set(profile["disc"]["paks"])
    for path in source.iterdir():
        if path.name in paks and path.is_file():
            os.link(path, target / path.name)
        elif path.is_file() and (path.suffix.lower() in (".irx", ".img") or
                path.name in (profile["executable"]["name"], profile["disc"]["toc"], "SYSTEM.CNF", ".disc_layout", ".disc_meta")):
            shutil.copyfile(path, target / path.name)
        elif path.name == profile["disc"]["iop_modules_dir"] and path.is_dir() and not path.is_symlink() and not path.is_junction():
            shutil.copytree(path, target / path.name)
    for name in ("mc0", "mc1", "saves"):
        (target / name).mkdir()


def frame_summary(rows, warmup):
    frames = [r["values"] for r in rows if r.get("tag") == "gow-frame" and
              r["elapsed_ms"] / 1000 - r["values"].get("window", 0) >= warmup]
    result = {"frame_windows": len(frames), "intervals": sum(r["intervals"] for r in frames)}
    for name in ("p50_ms", "p95_ms", "p99_ms"):
        result["median_window_" + name] = statistics.median(r[name] for r in frames) if frames else None
    result["max_interval_ms"] = max((r["max_ms"] for r in frames), default=None)
    for name in ("over_33_33", "over_50", "over_100"):
        result[name] = sum(r[name] for r in frames)
        result[name + "_per_1000"] = result[name] * 1000 / result["intervals"] if result["intervals"] else None
    return result


def save_inventory(data, disc):
    files = {disc / "Mcd001.ps2"}
    for directory in (data / "mc0", data / "saves", disc / "mc0", disc / "mc1"):
        if directory.is_dir(): files.update(p for p in directory.rglob("*") if p.is_file())
    return {str(p): {"sha256": worker.sha(p), "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
            for p in sorted(files) if p.is_file()}


def host_cpu_summary(rows, warmup):
    # The helper samples every five seconds; its final sample can be shorter.
    # Weight complete intervals, excluding startup overlap and process teardown.
    previous, weighted, duration = None, 0.0, 0.0
    for row in rows:
        if row.get("type") != "host_process":
            continue
        end = row["elapsed_ms"] / 1000
        if (previous is not None and previous >= warmup and end > previous and
                row.get("process_counters_available") and row.get("process_running") and
                "cpu_percent_one_core" in row):
            weighted += row["cpu_percent_one_core"] * (end - previous)
            duration += end - previous
        previous = end
    return {"mean_cpu_percent_one_core": weighted / duration if duration else None,
            "cpu_measured_seconds": duration}


def gameplay_before_warmup(log, warmup):
    # This production marker is emitted on guest state=11, pending=0. Unlike the
    # levelReady snapshot, it is also present when screenshots are disabled.
    match = re.search(r"\[(\d+) ms\] \[gow-pad2:test\] gameplay start at [0-9.]+ s", log)
    return bool(match and int(match[1]) / 1000 <= warmup)


def logic_speed_summary(log, warmup):
    """Whole post-warmup speed windows; timestep totals do not prove action parity."""
    windows = []
    for match in re.finditer(r"\[(\d+) ms\] \[gow-speed\] ([^\r\n]+)", log):
        values = {k: float(v) for k, v in re.findall(r"(\w+)=([-\d.]+)", match[2])}
        if values.get("wall", 0) > 0 and int(match[1]) / 1000 - values["wall"] >= warmup:
            windows.append(values)
    wall = sum(v["wall"] for v in windows)
    return {"windows": len(windows), "wall_seconds": wall,
            "game_seconds": sum(v["game"] for v in windows),
            "game_seconds_per_wall_second": sum(v["game"] for v in windows) / wall if wall else None,
            "min_window_speed": min((v["speed"] for v in windows), default=None),
            "max_window_speed": max((v["speed"] for v in windows), default=None)}


def scene_summary(log, warmup, end=float("inf"), frame_range=None):
    samples = []
    for match in re.finditer(r"\[(\d+) ms\] \[gow-player\].*?pos=([-\d.]+),([-\d.]+),([-\d.]+).*?state=(\d+) movie=(\d+) zone=(\S+)", log):
        if warmup <= int(match[1]) / 1000 <= end:
            samples.append({"position": [float(match[i]) for i in (2, 3, 4)],
                            "state": int(match[5]), "movie": int(match[6]), "zone": match[7]})
    trajectory = {}
    for m in re.finditer(r"\[(\d+) ms\] \[gow-player\].*?pos=([-\d.]+),([-\d.]+),([-\d.]+).*? frame=(\d+)", log):
        if (frame_range[0] <= int(m[5]) < frame_range[1]) if frame_range else (warmup <= int(m[1]) / 1000 <= end):
            trajectory[m[5]] = [float(m[i]) for i in (2,3,4)]
    return {"trajectory": trajectory, "samples": len(samples), "zones": sorted({s["zone"] for s in samples}),
            "states": sorted({s["state"] for s in samples}),
            "no_movie": bool(samples) and all(s["movie"] == 0 for s in samples),
            "gameplay_only": bool(samples) and all(s["state"] == 11 and s["movie"] == 0 for s in samples),
            "position_min": [min(s["position"][i] for s in samples) for i in range(3)] if samples else None,
            "position_max": [max(s["position"][i] for s in samples) for i in range(3)] if samples else None}


def same_scene(scenes, tolerance, zones=None, states=(11,)):
    allowed = set(zones) if zones else set(scenes[0]["zones"]) if scenes else set()
    if not scenes or not allowed or any(s["samples"] < 3 or not s["no_movie"] or not set(s["states"]) <= set(states) or not s["zones"] or not set(s["zones"]) <= allowed for s in scenes):
        return False
    return all(max(s["position_max"][i] for s in scenes) - min(s["position_min"][i] for s in scenes) <= tolerance for i in range(3))


def same_trajectory(scenes, tolerance, zones):
    if not scenes or any(s["samples"] < 3 or not s["gameplay_only"] or not s["zones"] or not set(s["zones"]) <= set(zones) for s in scenes):
        return False
    first = scenes[0]["trajectory"]
    if len(first) < 3 or any(set(s["trajectory"]) != set(first) for s in scenes):
        return False
    return all(abs(s["trajectory"][f][i] - first[f][i]) <= tolerance for s in scenes for f in first for i in range(3))


def frame_window(log, scene):
    found = {}
    for m in re.finditer(r"\[(\d+) ms\] \[gow-scene\] phase=(begin|end) frame=(\d+) t=([\d.]+)", log):
        if m[2] in found:
            raise ValueError("Duplicate scene boundary")
        found[m[2]] = (int(m[1]) / 1000, int(m[3]), float(m[4]))
    if set(found) != {"begin", "end"}:
        raise ValueError("Missing frame-aligned scene boundaries (timeout or frame probe disabled)")
    begin, end = found["begin"], found["end"]
    if begin[1] != scene["frame_begin"] or end[1] != scene["frame_end"] or end[0] <= begin[0] or end[2] <= begin[2]:
        raise ValueError("Scene boundaries skipped or out of order")
    return {"begin_seconds": begin[0], "end_seconds": end[0], "guest_frames": end[1] - begin[1],
            "wall_seconds": end[2] - begin[2], "guest_fps": (end[1] - begin[1]) / (end[2] - begin[2])}


def aligned_metrics(log, frames):
    f = re.search(r"\[gow-scene-frame\] intervals=(\d+) skipped=(\d+) p50_ms=([\d.]+) p95_ms=([\d.]+) p99_ms=([\d.]+) max_ms=([\d.]+) over_100=(\d+)", log)
    a = re.search(r"\[gow-scene-audio\] requested=(\d+) missing=(\d+)", log)
    if not f or not a or int(f[1]) != frames or int(f[2]) != 0 or int(a[1]) <= 0 or int(a[2]) > int(a[1]):
        raise ValueError("Incomplete aligned frame/audio observation")
    return {"scope": "pad-observed consecutive guest-frame intervals; audio callback boundary snapshots",
            "intervals":int(f[1]),"p50_ms":float(f[3]),"p95_ms":float(f[4]),"p99_ms":float(f[5]),
            "max_ms":float(f[6]),"over_100":int(f[7]),"audio_requested":int(a[1]),"audio_missing":int(a[2])}



EFFICIENCY_FLAGS = {"sampler": "GOW_GS_SAMPLER_CACHE", "shader": "GOW_GS_FAST_SHADER", "alpha-bounds": "GOW_GS_ALPHA_BOUNDS"}

def efficiency_environment(mode, variant):
    return {flag: str(variant if mode in (name, "efficiency") else 0) for name, flag in EFFICIENCY_FLAGS.items()}

# PR 26 renderer switches. All are on by default in the shipped build (the runtime only checks for "0"), so a
# single-switch comparison keeps the others at their shipped value and toggles one; "pr26" turns all of them,
# plus primitive grouping, off (variant 0) or on (variant 1): "does the PR help this machine?".
PR26_FLAGS = {"ring": "GOW_GS_HW_RING", "texreuse": "GOW_GS_TEXREUSE", "depth-zbp": "GOW_GS_DEPTH_PER_ZBP",
              "state-cache": "GOW_GS_STATE_CACHE", "run-state": "PS2X_GS_RUN_STATE_FAST", "warm-shaders": "GOW_GS_WARM_SHADERS"}

def pr26_environment(mode, variant):
    if mode != "pr26" and mode not in PR26_FLAGS:
        return {}
    return {flag: str(variant if mode in (name, "pr26") else 1) for name, flag in PR26_FLAGS.items()}

def grouping_for(mode, variant, fixed):
    if mode in ("grouping", "pr26"):
        return variant
    return 1 if mode in PR26_FLAGS else fixed  # PR 26 comparisons keep the shipped grouping default

def completed_child(meta, events, helper_code):
    exits = [e for e in events if e.get("type") == "process_exit"]
    return (helper_code == 0 and meta.get("exit_code", 0) == 0 and len(exits) == 1 and
            exits[0].get("state") == "completed" and exits[0].get("code") == 0)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runner", required=True, type=Path)
    p.add_argument("--reference-runner", type=Path, help="Reference binary for --compare vu1; all other settings stay fixed")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--game", default="gow1")
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--warmup", type=int, default=60)
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--capture", action="store_true", help="Functional screenshots only; not a benchmark")
    p.add_argument("--timing", action="store_true", help="Intrusive section timing; not an FPS benchmark")
    p.add_argument("--compare", choices=("grouping", "alpha", "scaler", "scale", "countdown", "vu1", "vu1-inline", "logic-rate", "sampler", "shader", "alpha-bounds", "efficiency",
                                            "pr26", *PR26_FLAGS, "vu1-fast"), default="grouping",
                   help="vu1 compares binaries; vu1-inline uses one binary and forces JIT-only in both variants")
    p.add_argument("--logic-fps", type=int, choices=(120, 240), default=120, help="Experimental candidate for --compare logic-rate; reference is original 60 Hz")
    p.add_argument("--task-capture", action="store_true", help="Intrusive, bounded VU1 task recording for exact input replay; not an FPS benchmark")
    p.add_argument("--scene", help="Scene contract from the selected game's diagnostics.scenes profile")
    p.add_argument("--grouping", type=int, choices=(0, 1), default=0, help="Fixed grouping for alpha/scaler comparisons")
    p.add_argument("--gpu-samples", action="store_true", help="Optional Windows PDH engine busy-time samples every 2 s")
    p.add_argument("--hidden", action="store_true", help="Background sessions; no visible-play performance claim")
    a = p.parse_args()
    if (a.compare == "vu1") != bool(a.reference_runner):
        p.error("--compare vu1 requires --reference-runner, which is exclusive to that comparison")
    if a.capture and a.timing:
        p.error("Capture and timing must use separate sessions")
    if not 1 <= a.pairs <= 10 or not 30 <= a.warmup < a.seconds - 20 or a.seconds > 600:
        p.error("Require 1-10 pairs, at least 30 s warmup and >20 s measurement, at most 600 s/run")
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(subprocess.check_output([sys.executable, "-I", str(root / "tools/pipeline/profile.py"), a.game]))
    scene = profile.get("diagnostics", {}).get("scenes", {}).get(a.scene) if a.scene else None
    if a.scene and not scene:
        p.error("Unknown profile scene")
    if a.compare == "logic-rate" and scene and "frame_begin" in scene:
        p.error("Logic-rate comparisons require real-time input/windows, not equal frame numbers")
    if scene and "frame_begin" in scene:
        begin, end = scene["frame_begin"], scene.get("frame_end", 0)
        if not (0 <= begin < end <= 1000000 and end - begin <= 4096):
            p.error("Frame scene requires 1-4096 intervals and ordered boundaries up to 1000000")
    elf = Path(json.loads((root / "data" / a.game / "languages.json").read_text(encoding="utf-8-sig"))["recompile_elf"]).resolve()
    helper = root / "launcher/build-clang/deploy/gow-session.exe"
    candidate = a.runner.resolve()
    reference = a.reference_runner.resolve() if a.reference_runner else candidate
    runner = candidate
    for path in (runner, reference, elf, helper):
        if not path.is_file(): p.error(f"Missing {path}")
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = {"runner_sha256": worker.sha(runner), "reference_sha256": worker.sha(reference), "elf_sha256": worker.sha(elf),
                "toc_sha256": worker.sha(elf.parent / profile["disc"]["toc"]), "helper_sha256": worker.sha(helper)}
    report = {"schema": 1, "identity": identity, "mode": "task-capture" if a.task_capture else "capture" if a.capture else "timing" if a.timing else "frames-only",
              "scope": "Audio enabled, private blank cards. Recorded binary identities, profile input; scene bounds are checked when selected, animation is not a frame-identical replay. Percentiles are medians of complete-window percentiles, not pooled percentiles.",
              "visible": not a.hidden,
              "compare": a.compare, "gpu_samples": a.gpu_samples, "jit_only": a.compare == "vu1-inline",
              "logic_fps": a.logic_fps if a.compare == "logic-rate" else None,
              "scene": a.scene, "scene_contract": scene,
              "seconds": a.seconds, "warmup": a.warmup, "runs": []}
    original_saves = save_inventory(root / "data" / a.game, elf.parent)
    (output / "saves-before.json").write_text(json.dumps(original_saves, indent=2), encoding="utf-8")
    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    save()
    for index, variant in enumerate(v for pair in range(a.pairs) for v in ((0, 1) if pair % 2 == 0 else (1, 0))):
        grouped = grouping_for(a.compare, variant, a.grouping)
        runner = reference if a.compare == "vu1" and variant == 0 else candidate
        expected_hash = identity["reference_sha256"] if runner == reference else identity["runner_sha256"]
        if worker.sha(runner) != expected_hash: raise RuntimeError("Runner changed during comparison")
        run = output / f"{index + 1:02d}-{a.compare}-{variant}"
        run.mkdir()
        disc = run / "disc"
        private_disc(elf.parent, disc, profile)
        private_elf = disc / elf.name
        if worker.sha(private_elf) != identity["elf_sha256"]: raise RuntimeError("ELF identity changed")
        if worker.sha(disc / profile["disc"]["toc"]) != identity["toc_sha256"]: raise RuntimeError("TOC identity changed")
        session = run / "session"
        session.mkdir()
        a.mode, a.scale = "timing" if a.timing else "fps", (variant + 1 if a.compare == "scale" else 1)
        (session / "session.json").write_text(json.dumps({"schema": 1, "id": run.name, "state": "prepared", "settings": {"primitive_grouping": grouped, "visible": not a.hidden, "audio": True, "scale": a.scale, "private_cards": True}}))
        env = worker.environment(profile, run, a, 0)
        env.update(PS2X_GS_RUN=str(grouped), GOW_GS_EARLY_FINISH="1", GOW_GS_HW_RING="0", GOW_GS_TEXREUSE="0",
                   GOW_VU1_FAST="0", GOW_MC0=str(disc / "Mcd001.ps2"), GOW_SAVES_DIR=str(disc / "saves"),
                   TOBIICHI_PANTALLA="ventana", GOW_AUDIO_STATS="1")
        env.update(efficiency_environment(a.compare, variant))
        env.update(pr26_environment(a.compare, variant))
        if a.compare == "vu1-fast":
            env["GOW_VU1_FAST"] = str(variant)  # launcher "fast VU" option; changes VU1 float semantics
        if a.compare == "alpha":
            env["GOW_GS_ALPHA_PRUNE"] = str(variant)
        elif a.compare == "scaler":
            env.update(GOW_GS_ALPHA_PRUNE="0", GOW_SCALER="bilinear" if variant else "sharp")
        elif a.compare == "scale":
            env["GOW_GS_ALPHA_PRUNE"] = "0"
        if a.compare == "countdown":
            env.update(GOW_FINISH_COUNTDOWN=str(variant), GOW_GS_ALPHA_PRUNE="0")
        if a.compare == "vu1":
            env.update(GOW_GS_ALPHA_PRUNE="0", GOW_FINISH_COUNTDOWN="0")
        if a.compare == "vu1-inline":
            # Isolate the JIT adapter in both variants; hybrid arrival may use only AOT.
            # This comparison is not the shipped hybrid configuration.
            env.update(GOW_VU1X_CHAIN_INLINE=str(variant), GOW_VU1X_ONLY="1", GOW_GS_ALPHA_PRUNE="0", GOW_FINISH_COUNTDOWN="0")
        if a.compare == "logic-rate":
            env.update(GOW_EXPERIMENTAL_LOGIC_FPS=str(a.logic_fps if variant else 60),
                       GOW_DELTA_DIAG="1", TOBIICHI_VENTANA_FPS=str(a.logic_fps),
                       GOW_GS_ALPHA_PRUNE="0", GOW_FINISH_COUNTDOWN="0")
        if scene:
            if "frame_begin" in scene:
                env.update(GOW_TEST_FRAME_BEGIN=str(scene["frame_begin"]), GOW_TEST_FRAME_END=str(scene["frame_end"]))
            env.update(GOW_PAD_GUION=scene["pad_script"], GOW_PLAYER_TRACE="1")
            if scene.get("god_mode"):
                env["GOW_GOD_MODE"] = "1"
        if a.timing or a.compare in ("alpha", "sampler", "shader", "alpha-bounds", "efficiency"):
            # Existing bounded counters; no per-draw timers or GPU readbacks.
            env["GOW_GS_HW_STATS"] = "1"
        if a.task_capture:
            env.update(GOW_VU1_TASK_RECORD=str(run / "tasks.bin"), GOW_VU1_TASK_LIMIT="32",
                       GOW_VU1_TASK_STRIDE="256", GOW_VU1_TASK_DELAY=str(a.warmup))
        if a.capture:
            env.update(GOW_PAD_TEST_NO_CAPTURE="0", GOW_PAD_CAPTURAS=(f"f{(scene['frame_begin'] + scene['frame_end']) // 2}" if scene and "frame_begin" in scene else str(a.warmup + 10)))
        (run / "settings.json").write_text(json.dumps({k: v for k, v in env.items() if k.startswith(("GOW_", "PS2X_", "TOBIICHI_"))}, indent=2))
        print(f"Run {index + 1}/{a.pairs * 2}: {a.compare}={variant}, grouping={grouped}, visible={not a.hidden}, audio enabled, {a.seconds}s", flush=True)
        proc = subprocess.Popen([str(helper), str(session), str(runner), str(private_elf), str(run)], cwd=run, env=env)
        gpu, gpu_module, pid, samples, previous_sample_ms = None, None, None, [], 0
        try:
            start = time.monotonic()
            deadline, next_sample = start + a.seconds, start + 2
            if a.gpu_samples:
                spec = importlib.util.spec_from_file_location("windows_gpu_sample", Path(__file__).with_name("windows_gpu_sample.py"))
                gpu_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gpu_module)
                try:
                    gpu = gpu_module.GpuSampler()
                except OSError as error:
                    samples.append({"available": False, "reason": str(error), "elapsed_ms": 0})
            while proc.poll() is None and time.monotonic() < deadline:
                if scene and "frame_begin" in scene:
                    runtime_log = session / "runtime.log"
                    if runtime_log.is_file() and "[gow-scene] phase=end " in runtime_log.read_text(encoding="utf-8", errors="replace"):
                        break
                if gpu and time.monotonic() >= next_sample:
                    next_sample = time.monotonic() + 2
                    pid = pid or gpu_module.child_pid(proc.pid, runner.name)
                    if pid:
                        sample_start = time.monotonic()
                        sample = gpu.sample(pid)
                        sample.update(elapsed_ms=int((time.monotonic() - start) * 1000),
                                      interval_start_ms=previous_sample_ms,
                                      sampling_ms=(time.monotonic() - sample_start) * 1000)
                        previous_sample_ms = sample["elapsed_ms"]
                        samples.append(sample)
                time.sleep(0.5)
        finally:
            try:
                if proc.poll() is None:
                    (session / "stop.request").write_text("stop")
                    proc.wait(timeout=30)
            finally:
                if gpu:
                    gpu.close()
                if a.gpu_samples:
                    (run / "gpu.jsonl").write_text("".join(json.dumps(s) + "\n" for s in samples), encoding="utf-8")
        meta = json.loads((session / "session.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in (session / "metrics.jsonl").read_text(encoding="utf-8").splitlines()]
        events = [json.loads(line) for line in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        log = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in sorted(session.glob("runtime*.log")))
        window = frame_window(log, scene) if scene and "frame_begin" in scene else None
        warmup = window["begin_seconds"] if window else a.warmup
        end = window["end_seconds"] if window else float("inf")
        rows = [r for r in rows if r["elapsed_ms"] / 1000 <= end]
        samples = [r for r in samples if r["elapsed_ms"] / 1000 <= end]
        stats = worker.summarize(rows, warmup) | frame_summary(rows, warmup) | host_cpu_summary(rows, warmup)
        stats["runner_sha256"] = expected_hash
        if window:
            stats.update(aligned_window=window, guest_fps=window["guest_fps"],
                         aligned_metrics=aligned_metrics(log, window["guest_frames"]))

        stats["internal_scale"] = a.scale
        if scene:
            stats["scene"] = scene_summary(log, warmup, end, (scene["frame_begin"], scene["frame_end"]) if window else None)
        audio = [r["values"] for r in rows if r.get("tag") == "audio-stats" and r["elapsed_ms"] / 1000 - 5 >= warmup]
        gpu_rows = [r for r in samples if r.get("available") and r["interval_start_ms"] / 1000 >= warmup]
        cpu_rows = [r for r in gpu_rows if r.get("child_cpu_percent_one_core") is not None and r.get("child_cpu_interval_seconds", 0)]
        cpu_duration = sum(r["child_cpu_interval_seconds"] for r in cpu_rows)
        stats["sampled_cpu_percent_one_core"] = sum(r["child_cpu_percent_one_core"] * r["child_cpu_interval_seconds"] for r in cpu_rows) / cpu_duration if cpu_duration else None
        stats["sampled_cpu_seconds"] = cpu_duration
        system_cpu = [r["system_cpu_percent"] for r in gpu_rows if r.get("system_cpu_percent") is not None]
        stats.update(mean_system_cpu_percent=statistics.mean(system_cpu) if system_cpu else None,
                     peak_system_cpu_percent=max(system_cpu, default=None))
        stats.update(audio_requested=sum(r["requested"] for r in audio), audio_missing=sum(r["missing"] for r in audio),
                     audio_dropped=sum(r["dropped"] for r in audio),
                     gpu_valid_samples=len(gpu_rows),
                     mean_gpu_busiest_engine_percent=statistics.mean(r["child_busiest_engine_percent"] for r in gpu_rows) if gpu_rows else None,
                     max_gpu_busiest_engine_percent=max((r["child_busiest_engine_percent"] for r in gpu_rows), default=None))
        checks = {"exit_zero": completed_child(meta, events, proc.returncode), "graceful": not any(e["type"] == "forced_termination" for e in events),
                  "gameplay_before_warmup": gameplay_before_warmup(log, warmup), "windows": stats["windows"] >= (1 if window else 3),
                  "frames": stats["frame_windows"] >= (1 if window else 3), "effective_setting": f"[gs-run-config] enabled={grouped}" in log,
                  "queue_healthy": "[gs-run] queue record issue:" not in log,
                  "player_saves_unchanged": save_inventory(root / "data" / a.game, elf.parent) == original_saves}
        stats["helper_exit_code"] = proc.returncode
        stats["exit_metadata_recovered"] = "exit_code" not in meta and checks["exit_zero"]
        if a.compare in (*EFFICIENCY_FLAGS, "efficiency"):
            configured = efficiency_environment(a.compare, variant)
            checks["effective_efficiency_settings"] = all(marker in log for marker in (
                f"[gs-sampler-config] cache={configured['GOW_GS_SAMPLER_CACHE']}",
                f"[gs-alpha-bounds-config] enabled={configured['GOW_GS_ALPHA_BOUNDS']}",
                f"[gs-fast-config] requested={configured['GOW_GS_FAST_SHADER']} available={configured['GOW_GS_FAST_SHADER']}"))
        if window:
            checks["windows"] = checks["frames"] = stats["aligned_metrics"]["intervals"] == window["guest_frames"]
            stats["audio_requested"] = stats["aligned_metrics"]["audio_requested"]
            stats["audio_missing"] = stats["aligned_metrics"]["audio_missing"]
            stats["windowed_audio_dropped"] = stats["audio_dropped"] if audio else None
            stats["audio_dropped"] = None # no cumulative drop counter at the exact scene boundaries
        if a.compare == "alpha":
            checks["effective_alpha_setting"] = f"[gs-alpha-config] prune={variant}" in log
        elif a.compare == "scaler":
            checks["reference_alpha"] = "[gs-alpha-config] prune=0" in log
            checks["scaler_no_reported_failure"] = "[gs-present] scaler shader failed" not in log
        if a.task_capture:
            corpus = run / "tasks.bin"
            stats["task_capture_bytes"] = corpus.stat().st_size if corpus.is_file() else 0
            checks["bounded_tasks_recorded"] = stats["task_capture_bytes"] > 0 and "[gow-vu1-task] recorded=32 " in log and "[gow-vu1-task] write_error=1" not in log
        checks["effective_scale"] = f"render-target renderer ready, scale {a.scale:.2f}" in log
        if a.compare == "vu1-inline":
            checks["effective_inline_chain"] = f"[vu1-chain] inline={variant}" in log
            checks["effective_jit_only"] = "[vu1x] JIT-only validation: AOT registry cleared" in log
        if a.compare == "countdown":
            checks["effective_countdown"] = f"[gow-finish-wait] countdown={variant}" in log
        if a.compare == "logic-rate":
            stats["logic_fps"] = a.logic_fps if variant else 60
            stats["simulation_speed"] = logic_speed_summary(log, warmup)
            checks["effective_logic_rate"] = f"[gow-logic-config] fps={stats['logic_fps']} experimental={variant} vblank=60" in log
            checks["speed_windows"] = stats["simulation_speed"]["windows"] >= 3
        if scene:
            checks["same_scene"] = same_scene([r["scene"] for r in report["runs"]] + [stats["scene"]], scene["position_tolerance"], scene.get("zones"), scene.get("states", [11]))
        if scene and "trajectory_tolerance" in scene:
            checks["same_scene"] = same_trajectory([r["scene"] for r in report["runs"]] + [stats["scene"]], scene["trajectory_tolerance"], scene["zones"])
        report["runs"].append({"directory": str(run), "variant": variant, "grouped": grouped, "checks": checks, **stats})
        save()
        print(json.dumps(report["runs"][-1]), flush=True)
        if not all(checks.values()): raise RuntimeError(f"Run failed validation: {checks}")
    report["completed"] = True
    if not (a.capture or a.timing or a.task_capture):
        report["mean_run_guest_fps"] = {str(v): statistics.mean(r["guest_fps"] for r in report["runs"] if r["variant"] == v) for v in (0, 1)}
    save()
    print(output / "summary.json", flush=True)


if __name__ == "__main__":
    main()
