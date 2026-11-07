#!/usr/bin/env bash
# Render benchmark for a registered regional build.
#
# Usage:  bash tools/test/bench-render.sh [tag] [seconds] [repeats]
# Env:    SCALE=0.5   internal resolution multiplier (PS2X_GS_HW_SCALE)
#         FAST=1      GOW_VU1_FAST
#         WORKER=1    PS2X_GS_WORKER (VIF1/VU1/GIF on a worker, GS frontend pipelined)
#         DISCARD=1   PS2X_GS_DISCARD_DRAWS: measures the frontend floor (no GL draws)
#         NOBOOT=1    do not skip the intro movie / intro-completion query
#
# It reads runner and ELF from data/<game>/regional-builds.json, so nothing is hardcoded, and it
# reuses the same deterministic entry as the pipeline: GOW_SKIP_FMV=1 + GOW_FAST_BOOT=1.
#
# The number to report is guest_flip_hz from [gow-perf], never host_hz: the host blits at 60 Hz
# and can repeat the same guest frame. Each repeat prints its last three windows; the summary
# prints the median of the per-run means so a single warm-up window cannot decide the result.
set -u

TAG="${1:-bench}"; SECS="${2:-40}"; REPS="${3:-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REG="$ROOT/data/gow1/regional-builds.json"
OUT="$ROOT/data/_tmp"

[ -f "$REG" ] || { echo "no $REG: register a regional build first (tools/pipeline/register_region.py)"; exit 1; }
mkdir -p "$OUT"

mapfile -t SELECTED < <(python - "$REG" "${REGION:-}" <<'PY'
import json, sys
builds = json.load(open(sys.argv[1]))["builds"]
matches = [b for b in builds if not sys.argv[2] or b["region"] == sys.argv[2]]
if len(matches) != 1: raise SystemExit("Select REGION when more than one build is registered")
b = matches[0]
print(b["runner"].replace("\\", "/"))
print(b["elf"].replace("\\", "/"))
print(b["framePc"])
PY
)
[ "${#SELECTED[@]}" -eq 3 ] || exit 1
RUNNER="${SELECTED[0]}"; ELF="${SELECTED[1]}"; FRAME_PC="${SELECTED[2]}"
[ -x "$RUNNER" ] || [ -f "$RUNNER" ] || { echo "runner missing: $RUNNER"; exit 1; }
DISC="$(dirname "$ELF")"

runs=()
for i in $(seq 1 "$REPS"); do
    LOG="$OUT/bench-$TAG-$i.log"
    sleep 1
    : >"$LOG"
    (
        RUN_DIR=$(mktemp -d "$OUT/bench-$TAG-$i-XXXXXX")
        cd "$RUN_DIR" || exit 1
        export GOW_MC0="$RUN_DIR/card.ps2"
        export GOW_SAVES_DIR="$RUN_DIR/saves"
        export PS2X_GS_HW_SCALE="${SCALE:-0.5}"
        export GOW_VU1N_X64=1
        export GOW_VU1_FAST="${FAST:-1}"
        export GOW_PERF_DIAG=frames
        export GOW_PERF_FRAME_PC="$FRAME_PC"
        export GOW_FRAME_DIAG=1   # [gow-frame] p50/p95/p99 + counts of frames over 16.7/33.3/50/100 ms
        unset GOW_GS_HW_STATS
        [ "${STATS:-0}" = "1" ] && export GOW_GS_HW_STATS=1
        [ "${DISCARD:-0}" = "1" ] && export PS2X_GS_DISCARD_DRAWS=1
        if [ "${NOBOOT:-0}" != "1" ]; then
            export GOW_SKIP_FMV=1
            export GOW_FAST_BOOT=1
        fi
        [ -n "${WORKER:-}" ] && export PS2X_GS_WORKER="$WORKER"
        # EXTRA="VAR=value": one more setting for the run (e.g. GOW_GS_DEPTH_PER_ZBP=0 for an A/B)
        [ -n "${EXTRA:-}" ] && export "$EXTRA"
        "$RUNNER" "$ELF" >"$LOG" 2>&1 &
        PID=$!
        trap 'kill "$PID" 2>/dev/null || true' EXIT INT TERM
        sleep "$SECS"
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null
        trap - EXIT INT TERM
    )
    # mean of the last three 5 s windows; the first windows contain the load ramp
    MEAN=$(grep "\[gow-perf\]" "$LOG" | tail -3 | sed -E 's/.*guest_flip_hz=([0-9.]+).*/\1/' |
           awk '{s+=$1; n++} END {if (n) printf "%.2f", s/n}')
    echo "run $i: guest_flip_hz mean(last 3) = ${MEAN:-none}"
    # the stutter numbers matter more than the mean: p95/p99 and how many frames missed 33 ms
    grep "\[gow-frame\]" "$LOG" | tail -1 | sed -E 's/^\[gow-frame\] //' | sed 's/^/        /'
    grep "^\[gs-hw\] shuffles" "$LOG" | tail -1 | sed 's/^/        /'
    runs+=("${MEAN:-0}")
done

echo "--- $TAG (scale=${SCALE:-0.5} fast=${FAST:-1} worker=${WORKER:-0} discard=${DISCARD:-0} ${SECS}s x ${REPS}) ---"
printf '%s\n' "${runs[@]}" | sort -n | awk '
    {v[NR]=$1}
    END {
        if (NR == 0) { print "no samples"; exit }
        m = (NR % 2) ? v[(NR+1)/2] : (v[NR/2] + v[NR/2+1]) / 2
        printf "median %.2f   min %.2f   max %.2f\n", m, v[1], v[NR]
    }'
echo "logs: $OUT/bench-$TAG-*.log"
