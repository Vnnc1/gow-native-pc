"""Replay local VU1 tasks across backends; preserve parity failures and rank isolated costs.

Times exclude result hashing/final flush and input reconstruction. They are not FPS
or unbiased gameplay profiles. Capture files contain game-derived data; keep them local.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("executable", type=Path)
    p.add_argument("corpus", type=Path)
    p.add_argument("--modes", nargs="+", choices=("hybrid", "jit", "helper", "sse", "exact"), default=["hybrid", "jit", "helper", "sse", "exact"])
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if not 1 <= a.repetitions <= 100: p.error("repetitions must be 1–100")
    exe, corpus = a.executable.resolve(), a.corpus.resolve()
    output = (a.output or corpus.parent / time.strftime("replay-%Y%m%d-%H%M%S")).resolve()
    output.mkdir(parents=True, exist_ok=False)
    def sha(file):
        with file.open("rb") as f: return hashlib.file_digest(f, "sha256").hexdigest()
    report = {"schema": 1, "executable_sha256": sha(exe), "corpus_sha256": sha(corpus),
              "scope": "Isolated MSCAL execution loops; excludes reconstruction/hashing/final flush, not FPS. Each backend must match its own captured baseline.", "modes": {}}
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
    failed = False
    for mode in a.modes:
        with (output / (mode + ".log")).open("wb") as log:
            r = subprocess.run([str(exe), "--replay", str(corpus), mode, str(a.repetitions)], env=env,
                               stdout=log, stderr=subprocess.STDOUT, timeout=600)
        text = (output / (mode + ".log")).read_text(errors="replace")
        records = []
        for line in text.splitlines():
            if "[gow-vu1-replay] record=" not in line: continue
            values = dict(re.findall(r"(\w+)=([\w.]+)", line))
            records.append({k: v if k == "code_hash" else float(v) if k.endswith("_us") else int(v) for k, v in values.items()})
        summary = re.search(r"records=(\d+) mismatches=(\d+) baseline_backend_differences=(\d+)", text)
        passed = r.returncode == 0 and bool(summary) and int(summary[1]) > 0 and int(summary[2]) == 0
        failed |= not passed
        report["modes"][mode] = {"passed": passed, "exit_code": r.returncode,
            "baseline_backend_differences": int(summary[3]) if summary else None,
            "records": records, "slowest_isolated_samples": sorted(records, key=lambda r: r["warm_median_us"], reverse=True)[:10],
            "interpreter_only_samples": sum(r["native_blocks"] == 0 for r in records)}
        (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(mode, "PASS" if passed else "FAIL", flush=True)
    print(output / "summary.json")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
