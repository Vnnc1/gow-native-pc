"""Isolated checks of actual delivery function bodies; no game data or GL context.

These are review gates, not renderer integration, GPU validation or FPS measurements.
Run against the original delivery and then a scratch copy with the review patches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def extract(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    # The reviewed functions have no braces in string literals or comments.
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[start:end]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path, help="PS2Recomp/ps2xRuntime directory")
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--suite", choices=("all", "submit_run", "ring"), default="all")
    args = parser.parse_args()
    runtime, compiler, output = args.runtime.resolve(), args.compiler.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(compiler.parent), str(compiler.parent.parent / "x86_64-w64-mingw32/bin"), env.get("PATH", "")])
    env["ASAN_OPTIONS"] = "detect_leaks=0:halt_on_error=1"
    templates = Path(__file__).with_name("render-delivery")
    suites = [
        ("submit_run", "src/lib/gs/gs_threaded_backend.cpp", ["void fillRunPrimitive(", "void GSThreadedBackend::SubmitRun("], ["0", "1", "2", "3", "255"]),
        ("ring", "src/lib/gs/gpu/gs_hw_backend.cpp", ["void waitRingSegment(", "uint32_t ringAppend("],
         ["nowrap", "normal", "already", "timeout", "failed", "null", "subdata"]),
    ]
    result = {"runtime": str(runtime), "compiler": str(compiler), "scope": "extracted source, ASan, mock GL; not gameplay", "sources": {}, "tests": []}
    for name, relative, signature, cases in suites:
        if args.suite != "all" and name != args.suite:
            continue
        raw = (runtime / relative).read_bytes()
        result["sources"][relative] = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8-sig")
        signatures = signature if isinstance(signature, (list, tuple)) else [signature]
        implementation = "\n\n".join(extract(text, item) for item in signatures)
        template = (templates / f"{name}.cpp.in").read_text(encoding="utf-8")
        source, exe = output / f"{name}.cpp", output / f"{name}.exe"
        source.write_text(template.replace("@IMPLEMENTATION@", implementation), encoding="utf-8")
        command = [str(compiler), "-std=c++20", "-O1", "-g", "-fsanitize=address", "-fno-omit-frame-pointer", "-I", str(runtime / "include"), str(source), "-o", str(exe)]
        build = subprocess.run(command, env=env, capture_output=True, text=True, errors="replace", timeout=120)
        (output / f"{name}-build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
        if build.returncode:
            raise RuntimeError(f"Build failed: {output / (name + '-build.log')}")
        for case in cases:
            run = subprocess.run([str(exe), case], env=env, capture_output=True, text=True, errors="replace", timeout=20)
            log = output / f"{name}-{case}.log"
            log.write_text(run.stdout + run.stderr, encoding="utf-8")
            result["tests"].append({"name": f"{name}/{case}", "exit_code": run.returncode, "log": str(log)})
            print(f"{'PASS' if run.returncode == 0 else 'FAIL'} {name}/{case} (exit {run.returncode})", flush=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return int(any(t["exit_code"] for t in result["tests"]))


if __name__ == "__main__":
    raise SystemExit(main())
