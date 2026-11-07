"""Compare builds, VIF1 barrier or GS stage spin with fixed graphics and private cards.

FPS, intrusive timing, and task capture are separate modes. Real-time scripted inputs
are repeatable inputs, not guaranteed identical guest-frame/scene trajectories.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def summarize(rows, warmup):
    # Collector elapsed time and runtime t have different origins. Select complete
    # post-warm-up windows using the collector clock; never filter on FPS value.
    def complete(r):
        return r["elapsed_ms"] / 1000 - r["values"].get("window", 0) >= warmup
    perf = [r["values"] for r in rows if r.get("tag") == "gow-perf" and complete(r)]
    frames = [r["values"] for r in rows if r.get("tag") == "gow-frame" and complete(r)]
    duration = sum(v.get("window", 0) for v in perf)
    sync = {}
    for r in rows:
        if r.get("tag") != "gow-sync":
            continue
        v = r["values"]
        e = sync.setdefault(str(int(v["site"])), {k: 0 for k in ("syncs", "worker_waits", "stage_waits", "worker_ms", "stage_ms")})
        for k in e:
            e[k] += v.get(k, 0)
    queues = {}
    for r in rows:
        if r.get("tag") != "gow-queue" or "waits" not in r["values"]:
            continue
        v = r["values"]
        e = queues.setdefault(str(int(v["queue"])), {"waits": 0, "wait_ms": 0, "max_ms": 0, "queued_peak": 0})
        for k in ("waits", "wait_ms"): e[k] += v[k]
        for k in ("max_ms", "queued_peak"): e[k] = max(e[k], v[k])
    return {
        "queue_whole_session": queues,
        "windows": len(perf), "measured_seconds": duration,
        "guest_fps": sum(v["guest_flip_hz"] * v["window"] for v in perf) / duration if duration else None,
        "min_window_fps": min((v["guest_flip_hz"] for v in perf), default=None),
        "max_window_fps": max((v["guest_flip_hz"] for v in perf), default=None),
        "median_window_p95_ms": statistics.median(v["p95_ms"] for v in frames) if frames else None,
        "over_100ms": sum(v.get("over_100", 0) for v in frames),
        "sync_whole_session": sync,
    }


def region_for_elf(profile, elf):
    # A regional executable has its own frame probe address and menu confirm button; the profile's global
    # diagnostics/optimize values describe the USA disc only (Japan/Asia use 0x183BB8 and Circle).
    name = Path(elf).name
    for region in profile.get("regions", []):
        if region.get("elf") == name:
            return region
    return None


def regional_pad_script(script, confirm):
    # Replace the USA "x" presses with the regional confirm button, keeping each entry's *N repeat count.
    if not confirm or confirm == "x":
        return script
    entries = []
    for entry in script.split(","):
        time, _, action = entry.partition(":")
        base, star, count = action.partition("*")
        if base.lower() == "x":
            action = f"{confirm}*{count}" if star else confirm
        entries.append(f"{time}:{action}")
    return ",".join(entries)


def environment(profile, run, args, early, frame_pc=None, pad_script=None):
    # USA defaults; regional runs pass their own frame probe and confirm-button script (region_for_elf).
    frame_pc = frame_pc or profile["diagnostics"]["frame_pc"]
    pad_script = pad_script or profile["optimize"]["pad_script"]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
    env.update(GOW_PERF_DIAG="1" if args.mode == "timing" else "frames", GOW_FRAME_DIAG="1",
        GOW_PERF_FRAME_PC=frame_pc, GOW_PAD_TEST="1", GOW_FAST_BOOT="1",
        GOW_SKIP_FMV="1", GOW_PAD_TEST_NO_CAPTURE="1", GOW_PAD_GUION=pad_script,
        GOW_MC0=str(run / "card.ps2"), GOW_SAVES_DIR=str(run / "saves"), GOW_AUDIO="1",
        GOW_VU1N_X64="1", GOW_VU1X_INLINE="1", GOW_VU1_SIN_COMPILAR="1", GOW_VU1_CAPTURE_MISSES="0",
        GOW_GS_FINISH_ASINCRONO="1", GOW_VU1_EARLY_FINISH=str(early), PS2X_GS_WORKER="1", PS2X_GS_HW="1",
        PS2X_GS_HW_SCALE=str(args.scale),        GOW_WINDOW_HIDDEN="1" if args.hidden else "0", TOBIICHI_ANCHO="1280", TOBIICHI_ALTO="720",
        TOBIICHI_FXAA="0", TOBIICHI_VSYNC="0", TOBIICHI_VENTANA_FPS="60", TOBIICHI_PANORAMICO="16:9")
    if getattr(args, "experiment", "barrier") in ("stage-spin", "build"):
        env.update(GOW_VU1_EARLY_FINISH="0", GOW_GS_EARLY_FINISH="1",
                   GOW_GS_STAGE_SPIN_US="0" if args.experiment == "stage-spin" and not early else "50")
    if args.mode == "timing":
        env.update(GOW_SYNC_DIAG="1", GOW_VU1N_DIAG="1", GOW_AUDIO_STATS="1", GOW_IOP_DRIFT="1")
        if getattr(args, "experiment", "barrier") == "stage-spin":
            env["GOW_GS_HW_STATS"] = "1"
    if args.mode == "capture":
        env.update(GOW_VU1_TASK_RECORD=str(run / "tasks.bin"), GOW_VU1_TASK_LIMIT="128",
                   GOW_VU1_TASK_STRIDE="256", GOW_VU1_TASK_DELAY=str(args.warmup),
                   GOW_PAD_TEST_NO_CAPTURE="0", GOW_PAD_CAPTURAS=str(args.warmup + 10))
    return env


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--game", default="gow1")
    p.add_argument("--experiment", choices=("barrier", "stage-spin", "build"), default="barrier",
                   help="stage-spin compares 50 us vs immediate sleep, with early GS FINISH fixed on")
    p.add_argument("--runner", type=Path)
    p.add_argument("--baseline-runner", type=Path, help="Required for build comparison: variant 0; --runner is variant 1")
    p.add_argument("--elf", type=Path)
    p.add_argument("--helper", type=Path)
    p.add_argument("--card", type=Path, help="Read-only initial card; copied separately for every run")
    p.add_argument("--mode", choices=("fps", "timing", "capture"), default="fps")
    p.add_argument("--seconds", type=int, default=120)
    p.add_argument("--warmup", type=int, default=60)
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--scale", type=int, choices=(1, 2), default=1)
    p.add_argument("--hidden", action="store_true", help="Functional checks only; no visible-gameplay claim")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if (a.experiment == "build") != bool(a.baseline_runner):
        p.error("Use --baseline-runner only with --experiment build")
    if not 1 <= a.pairs <= 10 or not 0 <= a.warmup < a.seconds - 15 or a.seconds > 600:
        p.error("Require 1–10 pairs and at least 15 seconds after warm-up, maximum 600 seconds/run")
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(subprocess.check_output([sys.executable, "-I", str(root / "tools/pipeline/profile.py"), a.game]))
    data = root / "data" / a.game
    runner = (a.runner or Path((root / "data/build-root.txt").read_text().strip() + "-clang") / "ps2xRuntime/ps2EntryRunner.exe").resolve()
    elf = (a.elf or Path(json.loads((data / "languages.json").read_text(encoding="utf-8-sig"))["recompile_elf"])).resolve()
    helper = (a.helper or root / "launcher/build-clang/deploy/gow-session.exe").resolve()
    baseline = a.baseline_runner.resolve() if a.baseline_runner else runner
    for f in (runner, baseline, elf, helper):
        if not f.is_file():
            p.error(f"Required file missing: {f}")
    region = region_for_elf(profile, elf)
    frame_pc = (region or {}).get("experimental_frame_pc") or profile["diagnostics"]["frame_pc"]
    confirm = (region or {}).get("experimental_menu_confirm") or "x"
    pad_script = regional_pad_script(profile["optimize"]["pad_script"], confirm)
    output = (a.output or data / "logs" / time.strftime("worker-ab-%Y%m%d-%H%M%S")).resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = {"runner_sha256": sha(runner), "elf_sha256": sha(elf), "helper_sha256": sha(helper),
                "card_sha256": sha(a.card) if a.card else None,
                "region": region.get("id") if region else "usa", "frame_pc": frame_pc, "menu_confirm": confirm}
    identity["baseline_runner_sha256"] = sha(baseline)
    report = {"schema": 1, "mode": a.mode, "identity": identity, "settings": vars(a) | {"root": str(root)},
              "scope": "Alternating real-time scripted route; scene alignment is not guaranteed. Timing/capture are not FPS benchmarks.",
              "runs": []}
    def save():
        (output / "summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    save()
    sequence = [1] if a.mode == "capture" else [v for i in range(a.pairs) for v in ((1, 0) if i % 2 == 0 else (0, 1))]
    for index, early in enumerate(sequence):
        if sha(runner) != identity["runner_sha256"] or sha(elf) != identity["elf_sha256"] or sha(baseline) != identity["baseline_runner_sha256"]:
            raise RuntimeError("Runner/ELF changed during comparison")
        label = "early" if a.experiment == "barrier" else a.experiment
        run = output / f"{index + 1:02d}-{label}-{early}"
        session = run / "session"
        session.mkdir(parents=True)
        if a.card:
            if sha(a.card) != identity["card_sha256"]: raise RuntimeError("Initial card changed")
            shutil.copyfile(a.card, run / "card.ps2")
            if sha(run / "card.ps2") != identity["card_sha256"]: raise RuntimeError("Initial card changed while copying")
        effective_early = early if a.experiment == "barrier" else 0
        settings = {"experiment": a.experiment, "variant": early, "early_finish": effective_early, "mode": a.mode,
                    "warmup_seconds": a.warmup, "visible": not a.hidden, "scale": a.scale, "dynamic_scale": False,
                    "input_script": pad_script, "frame_pc": frame_pc, "region": identity["region"]}
        (session / "session.json").write_text(json.dumps({"schema": 1, "id": run.name, "state": "prepared", "settings": settings}))
        env = environment(profile, run, a, early, frame_pc, pad_script)
        print(f"Run {index + 1}/{len(sequence)}: {a.experiment} variant={early}, mode={a.mode}, {a.seconds}s", flush=True)
        selected_runner = baseline if a.experiment == "build" and not early else runner
        proc = subprocess.Popen([str(helper), str(session), str(selected_runner), str(elf), str(root)], cwd=run, env=env)
        try:
            deadline = time.monotonic() + a.seconds
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                (session / "stop.request").write_text("stop")
                proc.wait(timeout=20)
        meta = json.loads((session / "session.json").read_text())
        rows = [json.loads(x) for x in (session / "metrics.jsonl").read_text().splitlines()]
        events = [json.loads(x) for x in (session / "events.jsonl").read_text().splitlines()]
        log = "\n".join(f.read_text(errors="replace") for f in sorted(session.glob("runtime*.log")))
        stats = summarize(rows, a.warmup)
        checks = {"exit_zero": meta.get("exit_code") == 0, "graceful": not any(e["type"] == "forced_termination" for e in events),
            "gameplay": bool(re.search(r"state=11\b.*levelReady=1", log)), "windows": stats["windows"] >= 3,
            "effective_setting": any(r.get("tag") == "gow-sync-config" and r["values"].get("early_finish") == effective_early
                                     and r["values"].get("timing") == int(a.mode == "timing") for r in rows)}
        if a.mode == "timing":
            if a.experiment in ("stage-spin", "build"):
                checks["queue_metrics"] = {int(r["values"]["queue"]) for r in rows
                    if r.get("tag") == "gow-queue" and r["values"].get("enabled") == 1} == {1, 2}
            else:
                checks["sync_metrics"] = bool(stats["sync_whole_session"])
        if a.experiment == "stage-spin":
            checks["stage_spin_environment"] = meta.get("runtime_environment", {}).get("GOW_GS_STAGE_SPIN_US") == ("50" if early else "0")
            if a.mode == "timing":
                checks["stage_spin_effective"] = any(r.get("tag") == "gow-queue" and r["values"].get("queue") == 1
                    and r["values"].get("spin_us") == (50 if early else 0) for r in rows)
        if a.mode == "capture": checks["task_corpus"] = (run / "tasks.bin").is_file() and (run / "tasks.bin").stat().st_size > 0
        report["runs"].append({"directory": str(run), "early_finish": effective_early, "variant": early, "checks": checks, **stats})
        save()
        if not all(checks.values()): raise RuntimeError(f"Run failed validation: {checks}; evidence: {output}")
    if a.mode == "fps":
        report["mean_run_guest_fps"] = {str(mode): statistics.mean(r["guest_fps"] for r in report["runs"] if r["variant"] == mode) for mode in (0, 1)}
    report["completed"] = True
    save()
    print(output / "summary.json")


if __name__ == "__main__":
    main()
