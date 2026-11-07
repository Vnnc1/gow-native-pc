"""Guest-frame-locked screenshot A/B for two runners (or one runner twice).

Runs each binary with GOW_PAD_TIME_FRAMES=1, so scripted input and captures count guest
flips (ps2_perf::guestFlips) instead of wall seconds: both runs act on the same guest
frame even when one build is slower. Captures are the PPM files GOW_PAD_CAPTURAS asks
GOW_PAD_TEST to write. The comparison (SHA-256 of the file, then a pixel diff on
mismatch) happens in this one process; the runners are separate processes because a
runner cannot load two builds at once.

Exit status is 0 only when every capture is byte-identical.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

CAPTURE = re.compile(r"gow_pad_test_(\d+)\.ppm$")


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_ppm(path):
    """Return (width, height, pixel bytes) for a binary P6 PPM."""
    data = Path(path).read_bytes()
    parts = data.split(b"\n", 3)
    if len(parts) < 4 or parts[0] != b"P6":
        raise ValueError(f"{path}: not a binary P6 PPM")
    width, height = (int(v) for v in parts[1].split())
    if int(parts[2]) != 255:
        raise ValueError(f"{path}: only 8-bit PPM is supported")
    return width, height, parts[3]


def pixel_report(base, final):
    """Describe the first pixel that differs and how many differ."""
    bw, bh, bp = read_ppm(base)
    fw, fh, fp = read_ppm(final)
    if (bw, bh) != (fw, fh):
        return f"size {bw}x{bh} vs {fw}x{fh}"
    differing = 0
    first = None
    for i in range(0, min(len(bp), len(fp)) - 2, 3):
        if bp[i:i + 3] != fp[i:i + 3]:
            differing += 1
            if first is None:
                pixel = i // 3
                first = (pixel % bw, pixel // bw, tuple(bp[i:i + 3]), tuple(fp[i:i + 3]))
    if first is None and len(bp) != len(fp):
        return f"payload {len(bp)} vs {len(fp)} bytes"
    if first is None:
        return "no pixel differs"
    return (f"{differing} pixels differ; first ({first[0]},{first[1]}) "
            f"{first[2]} vs {first[3]}")


def environment(args, run_dir):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
    env.update(
        GOW_PERF_DIAG="frames", GOW_PERF_FRAME_PC=args.frame_pc, GOW_PAD_TEST="1", GOW_PAD_TIME_FRAMES="1",
        GOW_PAD_GUION=args.pad_script, GOW_PAD_CAPTURAS=args.frames,
        GOW_FAST_BOOT="1", GOW_SKIP_FMV="1", GOW_AUDIO="0", GOW_WINDOW_HIDDEN="1",
        PS2X_GS_WORKER="1", PS2X_GS_HW="1", PS2X_GS_HW_SCALE=str(args.scale),
        TOBIICHI_ANCHO="1280", TOBIICHI_ALTO="720", TOBIICHI_VSYNC="0", TOBIICHI_FXAA="0",
    )
    card = args.disc / "Mcd001.ps2"
    if card.is_file():
        shutil.copyfile(card, run_dir / "Mcd001.ps2")
    env["GOW_MC0"] = str(run_dir / "Mcd001.ps2")
    env["GOW_SAVES_DIR"] = str(run_dir / "saves")
    env.pop("GOW_PAD_TEST_NO_CAPTURE", None)
    return env


def run_one(label, runner, args, out_dir):
    run_dir = out_dir / label
    run_dir.mkdir(exist_ok=False)
    log = out_dir / f"{label}.log"
    started = time.monotonic()
    with log.open("wb") as stderr:
        process = subprocess.Popen(
            [str(runner), str((args.disc / args.elf).resolve())], cwd=run_dir, env=environment(args, run_dir),
            stdout=subprocess.DEVNULL, stderr=stderr)
        wanted = len(args.frames.split(","))
        deadline = started + args.timeout
        while time.monotonic() < deadline and process.poll() is None:
            if len(list(run_dir.glob("gow_pad_test_*.ppm"))) >= wanted:
                break
            time.sleep(0.25)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    elapsed = time.monotonic() - started
    captures = sorted(run_dir.glob("gow_pad_test_*.ppm"),
                      key=lambda p: int(CAPTURE.search(p.name).group(1)))
    kept = []
    for i, capture in enumerate(captures):
        target = out_dir / f"{label}_{i}.ppm"
        shutil.move(str(capture), target)
        kept.append(target)
    anomalies = sum(1 for line in log.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if any(word in line for word in ("Assertion", "assert", "unhandled", "deadlock", "terminate called")))
    return kept, elapsed, anomalies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-runner", type=Path, required=True, help="reference binary")
    parser.add_argument("--final-runner", type=Path, help="candidate binary; defaults to the base runner (self-check)")
    parser.add_argument("--elf", help="ELF name inside --disc")
    parser.add_argument("--disc", type=Path, required=True, help="disc directory the runner boots from")
    parser.add_argument("--pad-script", help="guest-frame input script (default follows the selected region)")
    parser.add_argument("--frame-pc", help="regional builds must supply their own frame probe")
    parser.add_argument("--profile", type=Path, default=Path(__file__).resolve().parents[2] / "games/gow1/game.toml")
    parser.add_argument("--frames", default="241,273,296", help="guest-flip capture list (g = after gameplay start)")
    parser.add_argument("--timeout", type=float, default=150.0, help="wall seconds per run")
    parser.add_argument("--scale", type=float, default=0.5, help="PS2X_GS_HW_SCALE (same for both runs)")
    parser.add_argument("--out", type=Path, help="artifact directory (default: a temporary directory)")
    args = parser.parse_args()
    profile = tomllib.loads(args.profile.read_text(encoding="utf-8"))
    args.elf = args.elf or profile["executable"]["name"]
    if not args.frame_pc and args.elf != profile["executable"]["name"]:
        parser.error("regional --elf requires --frame-pc")
    args.frame_pc = args.frame_pc or str(profile["diagnostics"]["frame_pc"])
    region = next((r for r in profile.get("regions", []) if r.get("elf") == args.elf), {})
    confirm = region.get("experimental_menu_confirm", "x")
    args.pad_script = args.pad_script or "6:start," + ",".join(f"{frame}:{confirm}" for frame in (70,130,190,220))
    if not args.frames or any(not re.fullmatch(r"[0-9]+g?", value) for value in args.frames.split(",")):
        parser.error("--frames must list capture frames")
    out_dir = args.out or Path(tempfile.mkdtemp(prefix="gow-frame-eq-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    final_runner = args.final_runner or args.base_runner

    failures = 0
    base_files, base_seconds, base_anomalies = run_one("base", args.base_runner.resolve(), args, out_dir)
    print(f"[frame-eq] base  {args.base_runner.name}: {len(base_files)} captures in {base_seconds:.1f} s, "
          f"anomalies={base_anomalies}")
    final_files, final_seconds, final_anomalies = run_one("final", final_runner.resolve(), args, out_dir)
    print(f"[frame-eq] final {final_runner.name}: {len(final_files)} captures in {final_seconds:.1f} s, "
          f"anomalies={final_anomalies}")
    wanted = len(args.frames.split(","))
    if len(base_files) != wanted or len(final_files) != wanted:
        print(f"[frame-eq] FAIL: expected {wanted} captures from EACH independent run")
        failures += 1

    if not base_files:
        print("[frame-eq] FAIL: no capture was written (the run did not reach the requested guest frames)")
        failures += 1
    if len(base_files) != len(final_files):
        print(f"[frame-eq] FAIL: {len(base_files)} vs {len(final_files)} captures (did a run not reach the frames?)")
        failures += 1
    for i, (base, final) in enumerate(zip(base_files, final_files)):
        base_hash, final_hash = sha256(base), sha256(final)
        if base_hash == final_hash:
            print(f"[frame-eq] capture {i}: identical sha256={base_hash[:16]}")
        else:
            print(f"[frame-eq] capture {i}: DIFF {base_hash[:16]} vs {final_hash[:16]}; {pixel_report(base, final)}")
            failures += 1
    if base_anomalies or final_anomalies:
        print("[frame-eq] FAIL: runner log contains an assertion/deadlock marker")
        failures += 1
    print(f"[frame-eq] {'PASS' if failures == 0 else 'FAIL'} ({failures} problem(s)); artifacts: {out_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
