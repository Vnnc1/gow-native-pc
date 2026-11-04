"""Compare two native runtimes on identical local VU1 tasks; timings are not FPS."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--reference", required=True, type=Path)
p.add_argument("--candidate", required=True, type=Path)
p.add_argument("--corpus", required=True, type=Path)
p.add_argument("--output", required=True, type=Path)
p.add_argument("--inline-chain", action="store_true", help="Use one binary, toggling the JIT candidate")
p.add_argument("--pairs", type=int, default=5)
p.add_argument("--repetitions", type=int, default=100)
a = p.parse_args()
if not 1 <= a.pairs <= 10 or not 1 <= a.repetitions <= 100: p.error("Require 1-10 pairs and 1-100 repetitions")
def sha(path):
    with path.open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()
reference, candidate, corpus = a.reference.resolve(), a.candidate.resolve(), a.corpus.resolve()
if a.inline_chain and sha(reference) != sha(candidate): p.error("Inline-chain A/B requires the same binary")
identity = {"reference":sha(reference),"candidate":sha(candidate),"corpus":sha(corpus)}
a.output.mkdir(parents=True,exist_ok=False)
report={"scope":"Identical VU1 tasks; sum of per-record warm medians, not frame time/FPS. Each backend must match its own captured baseline.","identity":identity,"repetitions":a.repetitions,"inline_chain":a.inline_chain,"runs":[]}
expected=None
for index, variant in enumerate(v for pair in range(a.pairs) for v in ((0,1) if pair%2==0 else (1,0))):
    exe=reference if variant==0 else candidate
    if sha(exe)!=identity["reference" if variant==0 else "candidate"] or sha(corpus)!=identity["corpus"]:
        raise RuntimeError("Input changed during comparison")
    output=a.output/f"{index+1:02d}-{variant}"
    subprocess.run([sys.executable,"-I",str(Path(__file__).with_name("vu1-task-replay.py")),str(exe),str(corpus),"--modes","jit","--repetitions",str(a.repetitions),"--output",str(output)] + (["--inline-chain"] if a.inline_chain and variant else []),check=True,timeout=600,stdout=subprocess.DEVNULL)
    data=json.loads((output/"summary.json").read_text(encoding="utf-8"))["modes"]["jit"]
    records=data["records"]
    signature=[(r["record"],r["pc"],r["code_hash"],r["native_blocks"],r["match"]) for r in records]
    if not data["passed"] or not records or any(r["match"]!=1 for r in records): raise RuntimeError("Replay parity failed")
    if expected is not None and signature!=expected: raise RuntimeError("Work or result accounting changed")
    expected=signature
    total=sum(r["warm_median_us"] for r in records)
    report["runs"].append({"variant":variant,"sum_warm_medians_us":total,"records":len(records),"passed":True})
    (a.output/"summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"{index+1}: variant={variant}, sum medians={total:.1f} us",flush=True)
report["median_run_us"]={str(v):statistics.median(r["sum_warm_medians_us"] for r in report["runs"] if r["variant"]==v) for v in (0,1)}
report["completed"]=True
(a.output/"summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(report["median_run_us"])
