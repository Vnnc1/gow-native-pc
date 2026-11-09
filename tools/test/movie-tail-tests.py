"""Compile production movie wrappers with observing scheduler/guest fixtures."""
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
a.output.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env["PATH"] = str(a.compiler.resolve().parent) + os.pathsep + env.get("PATH", "")
for name, symbol, address in (("movie-tail", "gowMovieTailAudio", "0x00189A88u"),
                              ("movie-reader", "gowMovieRead", "0x00188848u"),
                              ("movie-end", "gowMovieIsEnd", "0x00189B00u")):
    body = m.extract(runtime_source, f"void {symbol}(")
    if f"runtime.replaceFunction({address}, {symbol});" not in runtime_source:
        raise SystemExit(f"{name} wrapper is not registered")
    source = Path(__file__).with_name(f"{name}.cpp.in").read_text(encoding="utf-8").replace("@WRAPPER@", body)
    cpp, exe = a.output / f"{name}.cpp", a.output / f"{name}.exe"
    cpp.write_text(source, encoding="utf-8", newline="\n")
    subprocess.run([str(a.compiler.resolve()), "-std=c++20", "-O2", "-static", str(cpp), "-o", str(exe)], env=env, check=True, timeout=120)
    subprocess.run([str(exe.resolve())], env=env, check=True, timeout=30)
