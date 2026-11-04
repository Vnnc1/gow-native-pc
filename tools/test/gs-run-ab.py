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
    return bool(match and int(match[1]) / 1000 < warmup)


def scene_summary(log, warmup):
    samples = []
    for match in re.finditer(r"\[(\d+) ms\] \[gow-player\].*?pos=([-\d.]+),([-\d.]+),([-\d.]+).*?state=(\d+) movie=(\d+) zone=(\S+)", log):
        if int(match[1]) / 1000 >= warmup:
            samples.append({"position": [float(match[i]) for i in (2, 3, 4)],
                            "state": int(match[5]), "movie": int(match[6]), "zone": match[7]})
    return {"samples": len(samples), "zones": sorted({s["zone"] for s in samples}),
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runner", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--game", default="gow1")
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--warmup", type=int, default=60)
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--capture", action="store_true", help="Functional screenshots only; not a benchmark")
    p.add_argument("--timing", action="store_true", help="Intrusive section timing; not an FPS benchmark")
    p.add_argument("--compare", choices=("grouping", "alpha", "scaler", "scale", "countdown"), default="grouping")
    p.add_argument("--task-capture", action="store_true", help="Intrusive, bounded VU1 task recording for exact input replay; not an FPS benchmark")
    p.add_argument("--scene", help="Scene contract from the selected game's diagnostics.scenes profile")
    p.add_argument("--grouping", type=int, choices=(0, 1), default=0, help="Fixed grouping for alpha/scaler comparisons")
    p.add_argument("--gpu-samples", action="store_true", help="Optional Windows PDH engine busy-time samples every 2 s")
    p.add_argument("--hidden", action="store_true", help="Background sessions; no visible-play performance claim")
    a = p.parse_args()
    if a.capture and a.timing:
        p.error("Capture and timing must use separate sessions")
    if not 1 <= a.pairs <= 10 or not 30 <= a.warmup < a.seconds - 20 or a.seconds > 600:
        p.error("Require 1–10 pairs, at least 30 s warmup and >20 s measurement, at most 600 s/run")
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(subprocess.check_output([sys.executable, "-I", str(root / "tools/pipeline/profile.py"), a.game]))
    scene = profile.get("diagnostics", {}).get("scenes", {}).get(a.scene) if a.scene else None
    if a.scene and not scene:
        p.error("Unknown profile scene")
    elf = Path(json.loads((root / "data" / a.game / "languages.json").read_text(encoding="utf-8-sig"))["recompile_elf"]).resolve()
    helper = root / "launcher/build-clang/deploy/gow-session.exe"
    runner = a.runner.resolve()
    for path in (runner, elf, helper):
        if not path.is_file(): p.error(f"Missing {path}")
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = {"runner_sha256": worker.sha(runner), "elf_sha256": worker.sha(elf),
                "toc_sha256": worker.sha(elf.parent / profile["disc"]["toc"]), "helper_sha256": worker.sha(helper)}
    report = {"schema": 1, "identity": identity, "mode": "task-capture" if a.task_capture else "capture" if a.capture else "timing" if a.timing else "frames-only",
              "scope": "Audio enabled, private blank cards. Same binary, real-time input; scene bounds are checked when selected, animation is not a frame-identical replay. Percentiles are medians of complete-window percentiles, not pooled percentiles.",
              "visible": not a.hidden,
              "compare": a.compare, "gpu_samples": a.gpu_samples,
              "scene": a.scene, "scene_contract": scene,
              "seconds": a.seconds, "warmup": a.warmup, "runs": []}
    original_saves = save_inventory(root / "data" / a.game, elf.parent)
    (output / "saves-before.json").write_text(json.dumps(original_saves, indent=2), encoding="utf-8")
    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    save()
    for index, variant in enumerate(v for pair in range(a.pairs) for v in ((0, 1) if pair % 2 == 0 else (1, 0))):
        grouped = variant if a.compare == "grouping" else a.grouping
        if worker.sha(runner) != identity["runner_sha256"]: raise RuntimeError("Runner changed during comparison")
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
        if a.compare == "alpha":
            env["GOW_GS_ALPHA_PRUNE"] = str(variant)
        elif a.compare == "scaler":
            env.update(GOW_GS_ALPHA_PRUNE="0", GOW_SCALER="bilinear" if variant else "sharp")
        elif a.compare == "scale":
            env["GOW_GS_ALPHA_PRUNE"] = "0"
        if a.compare == "countdown":
            env.update(GOW_FINISH_COUNTDOWN=str(variant), GOW_GS_ALPHA_PRUNE="0")
        if scene:
            env.update(GOW_PAD_GUION=scene["pad_script"], GOW_PLAYER_TRACE="1")
            if scene.get("god_mode"):
                env["GOW_GOD_MODE"] = "1"
        if a.timing or a.compare == "alpha":
            # Existing bounded counters; no per-draw timers or GPU readbacks.
            env["GOW_GS_HW_STATS"] = "1"
        if a.task_capture:
            env.update(GOW_VU1_TASK_RECORD=str(run / "tasks.bin"), GOW_VU1_TASK_LIMIT="32",
                       GOW_VU1_TASK_STRIDE="256", GOW_VU1_TASK_DELAY=str(a.warmup))
        if a.capture:
            env.update(GOW_PAD_TEST_NO_CAPTURE="0", GOW_PAD_CAPTURAS=str(a.warmup + 10))
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
        stats = worker.summarize(rows, a.warmup) | frame_summary(rows, a.warmup) | host_cpu_summary(rows, a.warmup)
        stats["internal_scale"] = a.scale
        if scene:
            stats["scene"] = scene_summary(log, a.warmup)
        audio = [r["values"] for r in rows if r.get("tag") == "audio-stats" and r["elapsed_ms"] / 1000 - 5 >= a.warmup]
        gpu_rows = [r for r in samples if r.get("available") and r["interval_start_ms"] / 1000 >= a.warmup]
        system_cpu = [r["system_cpu_percent"] for r in gpu_rows if r.get("system_cpu_percent") is not None]
        stats.update(mean_system_cpu_percent=statistics.mean(system_cpu) if system_cpu else None,
                     peak_system_cpu_percent=max(system_cpu, default=None))
        stats.update(audio_requested=sum(r["requested"] for r in audio), audio_missing=sum(r["missing"] for r in audio),
                     audio_dropped=sum(r["dropped"] for r in audio),
                     gpu_valid_samples=len(gpu_rows),
                     mean_gpu_busiest_engine_percent=statistics.mean(r["child_busiest_engine_percent"] for r in gpu_rows) if gpu_rows else None,
                     max_gpu_busiest_engine_percent=max((r["child_busiest_engine_percent"] for r in gpu_rows), default=None))
        checks = {"exit_zero": meta.get("exit_code") == 0, "graceful": not any(e["type"] == "forced_termination" for e in events),
                  "gameplay_before_warmup": gameplay_before_warmup(log, a.warmup), "windows": stats["windows"] >= 3,
                  "frames": stats["frame_windows"] >= 3, "effective_setting": f"[gs-run-config] enabled={grouped}" in log,
                  "queue_healthy": "[gs-run] queue record issue:" not in log,
                  "player_saves_unchanged": save_inventory(root / "data" / a.game, elf.parent) == original_saves}
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
        if a.compare == "countdown":
            checks["effective_countdown"] = f"[gow-finish-wait] countdown={variant}" in log
        if scene:
            checks["same_scene"] = same_scene([r["scene"] for r in report["runs"]] + [stats["scene"]], scene["position_tolerance"], scene.get("zones"), scene.get("states", [11]))
        report["runs"].append({"directory": str(run), "variant": variant, "grouped": grouped, "checks": checks, **stats})
        save()
        print(json.dumps(report["runs"][-1]), flush=True)
        if not all(checks.values()): raise RuntimeError(f"Run failed validation: {checks}")
    report["completed"] = True
    if not (a.capture or a.timing):
        report["mean_run_guest_fps"] = {str(v): statistics.mean(r["guest_fps"] for r in report["runs"] if r["variant"] == v) for v in (0, 1)}
    save()
    print(output / "summary.json", flush=True)


if __name__ == "__main__":
    main()
