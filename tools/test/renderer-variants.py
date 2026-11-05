"""Real-OpenGL differential checks; explicit GPU run, not a headless CTest."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("executable", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
reference = None
results = []
for name, sampler, fast, bounds, fallback in (
    ("reference", 0, 0, 0, 0), ("sampler", 1, 0, 0, 0),
    ("fast", 0, 1, 0, 0), ("bounds", 0, 0, 1, 0),
    ("combined", 1, 1, 1, 0), ("fallback", 1, 1, 1, 1),
    ("reference-repeat", 0, 0, 0, 0),
):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
    env.update(GOW_GS_SAMPLER_CACHE=str(sampler), GOW_GS_FAST_SHADER=str(fast),
               GOW_GS_ALPHA_BOUNDS=str(bounds), GOW_GS_FAST_SHADER_FAIL=str(fallback),
               GOW_GS_ALPHA_PRUNE="1", GOW_GS_VARIANT_DIAG="1")
    run = subprocess.run([str(a.executable.resolve())], env=env, capture_output=True, text=True, timeout=120)
    (a.output / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
    if "GL error" in run.stderr:
        raise RuntimeError(f"{name}: OpenGL error; inspect its log")
    if run.returncode:
        raise RuntimeError(f"{name} exited {run.returncode}; inspect its log")
    cases = re.findall(r"^CASE (\d+) (\d+) ([0-9a-f]+)$", run.stdout, re.M)
    if len(cases) != 384 or len({(f, i) for f, i, h in cases}) != 384:
        raise RuntimeError(f"{name}: missing/duplicate cases")
    if len({h for f, i, h in cases}) < 16:
        raise RuntimeError(f"{name}: insufficient nonuniform pixel coverage")
    marker = f"[gs-fast-config] requested={fast} available={int(bool(fast and not fallback))}"
    if marker not in run.stderr:
        raise RuntimeError(f"{name}: shader path not exercised")
    coverage = re.search(r"\[gs-variant-end\] fast=(\d+) full=(\d+) avoided=(\d+) bounds=(\d+)", run.stderr)
    if not coverage or int(coverage[2]) == 0 or (fast and not fallback and int(coverage[1]) == 0) or (sampler and int(coverage[3]) == 0) or (bounds and int(coverage[4]) == 0):
        raise RuntimeError(f"{name}: missing intended variant/fallback coverage")
    if reference is None:
        reference = cases
    differences = sum(x != y for x, y in zip(reference, cases))
    results.append({"variant": name, "cases": len(cases), "differences": differences, "exit_code": run.returncode})
    (a.output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if differences:
        raise RuntimeError(f"{name}: {differences} frame digests differ")
    print(f"PASS {name}: 384 frames match the reference", flush=True)
