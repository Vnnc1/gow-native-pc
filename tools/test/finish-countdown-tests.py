"""Differential test of the production countdown body and scheduler batch helper.

No game data: compare architectural registers and checkpoint clocks with individual
MIPS countdown iterations. Full-checkpoint side effects are represented by a yield;
the integration/verify suites remain responsible for timers and IOP execution.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--runtime", required=True, type=Path)
p.add_argument("--compiler", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
spec = importlib.util.spec_from_file_location("extract", Path(__file__).with_name("render-delivery-tests.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
body = m.extract((a.runtime.parent.parent / "src/gow_overrides.cpp").read_text(encoding="utf-8"), "void gowFinishCountdown(")
batch = m.extract((a.runtime / "src/lib/Kernel/EeScheduler.cpp").read_text(encoding="utf-8"), "uint64_t EeScheduler::advanceQuietRepeated(")
source = Path(__file__).with_name("finish-countdown.cpp.in").read_text(encoding="utf-8").replace("@COUNTDOWN@", body).replace("@BATCH@", batch)
a.output.mkdir(parents=True, exist_ok=True)
cpp, exe = a.output / "countdown.cpp", a.output / "countdown.exe"
cpp.write_text(source, encoding="utf-8", newline="\n")
env = os.environ.copy()
env["PATH"] = str(a.compiler.resolve().parent) + os.pathsep + env.get("PATH", "")
subprocess.run([str(a.compiler.resolve()), "-std=c++20", "-O2", "-static", "-I", str(a.runtime.resolve() / "include"), str(cpp), "-o", str(exe)], env=env, check=True, timeout=120)
subprocess.run([str(exe.resolve())], env=env, check=True, timeout=30)
