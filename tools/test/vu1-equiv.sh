#!/bin/sh
# VU1 x86-64 JIT equivalence campaign (Linux, no game data). For each seed the JIT in every mode must print the digest of
# vu1n_gen.py's code built by clang (the "module" oracle): AVX, SSE4.1 only, helpers only, speculation off. Then, with
# Inf / NaN registers (GOW_FUZZ_SPECIAL=1), speculation on must equal speculation off.
# usage: tools/test/vu1-equiv.sh <runtime build dir with gow_vu1_x64_fuzz_test> <runtime checkout (engine/runtime)> [seeds...]
# Build: docs/research/vu1-x64-jit.md section 6. Exit code 1 on any mismatch.
B="$1"; R="$2"; shift 2
[ $# -gt 0 ] || set -- 1 4 7 11 23
FL="-O3 -DNDEBUG -std=gnu++20 -march=native -ffp-contract=off -fno-strict-aliasing -fwrapv -I$R/PS2Recomp/ps2xRuntime/include"
W=$(mktemp -d); fail=0
for seed in "$@"; do
  mod=$(GOW_FUZZ_SEED=$seed "$B/gow_vu1_x64_fuzz_test" module "$W/m$seed" "$R/tools/vu1/vu1n_gen.py" python3 clang++ "$FL" 4 6 2>&1 | grep digest)
  line="seed $seed module=${mod#digest }"
  for v in "x64:" "x64:GOW_VU1X_AVX=0" "x64-calls:" "x64:GOW_VU1X_SPECULATE=0"; do
    m=${v%%:*}; e=${v#*:}
    d=$(env $e GOW_FUZZ_SEED=$seed "$B/gow_vu1_x64_fuzz_test" $m 4 6 2>&1 | grep digest)
    line="$line $m${e:+($e)}=${d#digest }"
    [ -n "$mod" ] && [ "${d#digest }" = "${mod#digest }" ] || fail=1
  done
  a=$(GOW_FUZZ_SPECIAL=1 GOW_FUZZ_SEED=$seed "$B/gow_vu1_x64_fuzz_test" x64 4 6 2>&1 | grep digest)
  b=$(GOW_FUZZ_SPECIAL=1 GOW_VU1X_SPECULATE=0 GOW_FUZZ_SEED=$seed "$B/gow_vu1_x64_fuzz_test" x64 4 6 2>&1 | grep digest)
  [ -n "$a" ] && [ "$a" = "$b" ] || fail=1
  echo "$line special(spec=${a#digest } nospec=${b#digest })"
done
rm -rf "$W"
if [ $fail = 0 ]; then echo "EQUIVALENT"; else echo "MISMATCH"; exit 1; fi
