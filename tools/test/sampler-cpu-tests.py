"""Windows integration: counter-only sampler distinguishes busy and sleeping threads."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--compiler', type=Path, required=True)
p.add_argument('--sampler', type=Path, required=True)
a = p.parse_args()
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'fixture.cpp'
    source.write_text('''#include <windows.h>
#include <atomic>
#include <thread>
#include <cstdio>
int main() {
    std::atomic<bool> stop{false};
    std::thread busy([&]{ SetThreadDescription(GetCurrentThread(), L"ProbeBusy");
        while (!stop.load(std::memory_order_relaxed)) {} });
    std::thread idle([&]{ SetThreadDescription(GetCurrentThread(), L"ProbeIdle");
        while (!stop.load(std::memory_order_relaxed)) Sleep(100); });
    Sleep(200); puts("ready"); fflush(stdout);
    Sleep(15000); stop.store(true); busy.join(); idle.join();
}
''', encoding='utf-8')
    exe = root / 'fixture.exe'
    subprocess.run([str(a.compiler.resolve()), '-O2', '-std=c++20', '-static', str(source), '-o', str(exe)], check=True)
    proc = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'ready'
        result = subprocess.run([str(a.sampler.resolve()), str(proc.pid), '3'],
            env={**os.environ, 'SAMPLER_CPU_ONLY': '1'}, capture_output=True, text=True, timeout=15, check=True)
        values = {}
        for name, samples, cpu, wall in re.findall(r'== (Probe\w+) \(\d+\): (\d+) samples\s+cpu_ms=([\d.]+) observed_ms=([\d.]+)', result.stdout):
            assert int(samples) == 0 and float(wall) >= 2900
            values[name] = float(cpu)
        assert values['ProbeBusy'] > 100 and values['ProbeIdle'] < 100, values
        print('PASS: CPU-only mode, zero instruction samples, busy/idle separation:', values)
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
