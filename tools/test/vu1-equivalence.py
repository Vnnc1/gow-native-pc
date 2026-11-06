"""Compare generated DLL and x64 VU1 backends, including self-loop exit accounting."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("python", type=Path)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seeds", nargs="+", default=[1, 4, 7, 11, 23], type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vu1-equiv-", dir=args.output))
    flags = ('-O3 -DNDEBUG -std=c++20 -march=x86-64-v2 -ffp-contract=off '
             '-fno-strict-aliasing -fwrapv '
             f'-I"{args.runtime / "PS2Recomp/ps2xRuntime/include"}"')
    base_env = {k: v for k, v in os.environ.items()
                if not k.startswith(("GOW_VU1", "GOW_FUZZ", "PS2X_GS", "GOW_GS"))}
    base_env["PATH"] = str(args.compiler.parent) + os.pathsep + base_env.get("PATH", "")

    def run(label, mode, extra):
        cmd = [str(args.executable), mode]
        if mode == "module":
            cmd += [str(work / label), str(args.runtime / "tools/vu1/vu1n_gen.py"),
                    str(args.python), str(args.compiler), flags]
        cmd += ["1", "3"]
        result = subprocess.run(cmd, env=base_env | extra, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=240)
        (work / f"{label}.log").write_bytes(result.stdout)
        output = result.stdout.decode(errors="replace").replace("\r\n", "\n")
        digest = re.search(r"^digest ([0-9a-f]+)$", output, re.M)
        blocks = re.search(r"(\d+) native blocks run", output)
        if result.returncode or not digest or not blocks or int(blocks[1]) == 0:
            raise RuntimeError(f"{label} failed; inspect {work / (label + '.log')}")
        print(f"{label}: {digest[1]}, {blocks[1]} native blocks", flush=True)
        return digest[1], int(blocks[1])

    for seed in args.seeds:
        env = {"GOW_FUZZ_SEED": str(seed)}
        reference = run(f"seed-{seed}-module", "module", env)
        for mode, switch in [("x64", {}), ("x64-calls", {}),
                             ("x64-sse", {"GOW_VU1X_AVX": "0"}),
                             ("x64-no-spec", {"GOW_VU1X_SPECULATE": "0"})]:
            got = run(f"seed-{seed}-{mode}", "x64-calls" if mode == "x64-calls" else "x64", env | switch)
            if got[0] != reference[0]:
                raise RuntimeError(f"seed {seed}: {mode} differs from generated code")
        special = env | {"GOW_FUZZ_SPECIAL": "1"}
        if run(f"seed-{seed}-special", "x64", special)[0] != run(
                f"seed-{seed}-special-no-spec", "x64", special | {"GOW_VU1X_SPECULATE": "0"})[0]:
            raise RuntimeError("Special-value speculation mismatch")

    for cycles in (7, 20000):
        env = {"GOW_FUZZ_SEED": "1", "GOW_FUZZ_SELFLOOP": "1", "GOW_FUZZ_CYCLES": str(cycles)}
        reference = run(f"loop-{cycles}-module", "module", env)
        for label, mode, switch in [("unchained", "module", {"GOW_VU1N_CHAIN": "0"}),
                                    ("x64", "x64", {}), ("x64-calls", "x64-calls", {})]:
            if run(f"loop-{cycles}-{label}", mode, env | switch) != reference:
                raise RuntimeError(f"Self-loop {cycles}: state or block-accounting mismatch ({label})")
    print(f"PASS: VU1 backend equivalence and self-loop budget/depth exits; logs: {work}")


if __name__ == "__main__":
    main()
