"""Run isolated regression processes against the real patched runtime/recompiler.

Configure the runtime with -DCMAKE_PROJECT_PS2RetroX_INCLUDE=<absolute guest-calls.cmake>,
build gow_guest_calls, then run this script with its executable and an output folder.
No ISO or generated game code is required. Logs and JSON stay in the chosen output folder.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in os.environ.items()
             if not k.startswith(("GOW_", "PS2X_", "TOBIICHI_"))}
    cases = [(mode, mode, {}) for mode in ("parity", "full", "watch", "trace")]
    cases.append(("trace-clock", "trace-clock", {"PS2X_GS_WORKER_TRACE": "0"}))
    cases.append(("instances", "instances", {"GOW_DISPATCH_FULL": "1"}))
    for codegen in ("classic", "locals"):
        for dispatch in ("lean", "dispatch"):
            cases.append((f"codegen-{codegen}-{dispatch}", "codegen",
                          {"PS2X_CODEGEN": codegen, "PS2X_STATIC_CALLS": dispatch}))
    results = []
    for name, mode, extra in cases:
        try:
            run = subprocess.run([str(args.executable.resolve()), mode], env=clean | extra,
                                 capture_output=True, text=True, errors="replace", timeout=120)
            log = run.stdout + run.stderr
            ok = run.returncode == 0 and (mode != "trace-clock" or "[gsw-trace]" not in run.stderr)
            if mode == "trace":
                ok = ok and "[gsw-trace]" in run.stderr
            result = {"name": name, "passed": ok, "exitCode": run.returncode,
                      "summary": run.stdout.strip()}
        except subprocess.TimeoutExpired:
            log = "Timed out after 120 seconds.\n"
            result = {"name": name, "passed": False, "timeout": True}
        (args.output / f"{name}.log").write_text(log, encoding="utf-8")
        results.append(result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} {name}", flush=True)
    (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
