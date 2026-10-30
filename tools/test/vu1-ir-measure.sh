#!/bin/sh
# Instruction counts (valgrind callgrind) of the VU1 benchmark (tests/vu1_bench.cpp in the runtime): the cost of the
# native blocks in hybrid mode (AOT code compiled into the bench) and in JIT-only mode, split into JIT code, JIT helpers,
# AOT blocks and VU1NativeAccess::chain (shared bookkeeping). Wall time in a cloud VM is too noisy for small changes;
# instruction counts are stable. Build the bench with -march=haswell (or anything without AVX-512: valgrind cannot run it).
# Note: valgrind does not model the MXCSR rounding / flush modes, so digests under valgrind differ; counts are still fine.
# usage: tools/test/vu1-ir-measure.sh <gow_vu1_bench> [reps]
B="$1"; R="${2:-100}"; O=$(mktemp -d)
for m in hybrid jit; do
  valgrind --tool=callgrind --callgrind-out-file=$O/$m.out "$B" $m "$R" >/dev/null 2>&1
  callgrind_annotate --auto=no $O/$m.out 2>/dev/null | grep -v "=>" | awk -v m=$m '
    /PROGRAM TOTALS/ {gsub(",","",$1); tot=$1}
    /\?\?\?:0x/ {gsub(",","",$1); jit+=$1}
    /vu1x::/ {gsub(",","",$1); help+=$1}
    /[:]b[0-9a-f][0-9a-f][0-9a-f][0-9a-f]_[0-9a-f]+\(/ {gsub(",","",$1); aot+=$1}
    /VU1NativeAccess::chain\(/ {gsub(",","",$1); ch+=$1}
    END {printf "%-6s blocks=%.2fM  [jit code %.2fM, jit helpers %.2fM, aot %.2fM]  chain %.2fM  program %.2fM\n", m, (jit+help+aot)/1e6, jit/1e6, help/1e6, aot/1e6, ch/1e6, tot/1e6}'
done
rm -rf "$O"
