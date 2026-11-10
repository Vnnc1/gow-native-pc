"""Compile the production USA logic-rate adapter against synthetic guest state.

Checks timestep/fallback/pacing contracts without a disc. Does not validate the
game's frame-counted actions, GPU presentation or scheduler timing in gameplay.
"""
import argparse
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--runtime", required=True, type=Path)
p.add_argument("--compiler", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
a = p.parse_args()
production = (a.runtime / "src/gow_overrides.cpp").read_text(encoding="utf-8")
begin = "// BEGIN experimental logic rate (also compiled by the isolated regression test)."
end = "// END experimental logic rate."
assert production.count(begin) == production.count(end) == 1
body = production.split(begin)[1].split(end)[0]
source = Path(__file__).with_name("logic-rate.cpp.in").read_text(encoding="utf-8").replace("@PRODUCTION@", body)
a.output.mkdir(parents=True, exist_ok=True)
cpp, exe = a.output / "logic-rate.cpp", a.output / "logic-rate.exe"
cpp.write_text(source, encoding="utf-8", newline="\n")
env = os.environ.copy()
env["PATH"] = str(a.compiler.resolve().parent) + os.pathsep + env.get("PATH", "")
subprocess.run([str(a.compiler.resolve()), "-std=c++20", "-O2", "-static", "-I",
               str(a.runtime.resolve() / "PS2Recomp/ps2xRuntime/include"), str(cpp), "-o", str(exe)],
               env=env, check=True, timeout=120)
subprocess.run([str(exe.resolve())], env=env, check=True, timeout=30)
