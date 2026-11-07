"""Compile the production movie-tail wrapper with an observing scheduler/guest fixture."""
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
runtime_source = (a.runtime.parent.parent / "src/gow_overrides.cpp").read_text(encoding="utf-8")
body = m.extract(runtime_source, "void gowMovieTailAudio(")
if "runtime.replaceFunction(0x00189A88u, gowMovieTailAudio);" not in runtime_source:
    raise SystemExit("Movie-tail wrapper is not registered")
source = Path(__file__).with_name("movie-tail.cpp.in").read_text(encoding="utf-8").replace("@WRAPPER@", body)
a.output.mkdir(parents=True, exist_ok=True)
cpp, exe = a.output / "movie-tail.cpp", a.output / "movie-tail.exe"
cpp.write_text(source, encoding="utf-8", newline="\n")
env = os.environ.copy()
env["PATH"] = str(a.compiler.resolve().parent) + os.pathsep + env.get("PATH", "")
subprocess.run([str(a.compiler.resolve()), "-std=c++20", "-O2", "-static", str(cpp), "-o", str(exe)], env=env, check=True, timeout=120)
subprocess.run([str(exe.resolve())], env=env, check=True, timeout=30)
