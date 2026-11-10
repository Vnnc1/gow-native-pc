#include "runtime/gow_frame_metrics.h"
#include <cstdio>
#include <limits>

int main()
{
    int failures = 0;
    auto check = [&](bool ok, const char *what) { if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); ++failures; } };
    gow_diagnostics::FrameWindow window;
    check(window.analyze().p99 == 0, "empty window");
    window.add(-1); window.add(std::numeric_limits<double>::quiet_NaN()); window.add(std::numeric_limits<double>::infinity());
    check(window.count == 0, "invalid values ignored");
    for (int i = 100; i > 0; --i) window.add(i);

    check(window.analyze().p50 == 50 && window.analyze().p95 == 95 && window.analyze().p99 == 99, "nearest-rank percentiles");
    check(window.total == 5050 && window.maximum == 100 && window.over50 == 50 && window.over100 == 0, "totals and threshold boundaries");
    check(window.overBudget == 84 && window.over33 == 67, "frame budgets");
    window = {};
    for (int i = 0; i < 5000; ++i) window.add(10);
    window.add(500);
    check(window.samples() == 4096 && window.count == 5001 && window.maximum == 500, "bounded window with complete totals");
    check(window.analyze().p99 == 10 && window.over100 == 1, "sparse stall");
    window = {}; window.add(1000.0 / 60.0);
    check(window.overBudget == 0 && window.analyze().p99 == 1000.0 / 60.0, "exact boundary and single sample");
    window = {};
    for (int i = 0; i < 4095; ++i) window.add(10);
    window.add(50); window.add(50); // One chronological streak across storage boundary.
    check(window.analyze().longestRun == 2, "streak spans physical ring boundary");
    const auto before = window.intervals;
    window.analyze();
    check(window.intervals == before, "analysis preserves chronological samples");
    gow_diagnostics::SharedFrameWindow shared;
    shared.sample(0, false, 0);
    shared.sample(1, true, 10);
    shared.sample(2, false, 20);
    shared.sample(2, false, 40);
    shared.sample(5, false, 70);
    check(shared.counts.polls == 5 && shared.counts.fresh == 2 && shared.counts.repeated == 1 &&
          shared.counts.blank == 1 && shared.counts.unavailable == 1 && shared.counts.skipped == 2,
          "shared polls distinguish acquisition, reuse, blank, unavailable and skipped publications");
    check(shared.counts.maxHoldNs == 50, "hold includes the interval before a new acquisition");
    shared.clearCounts();
    shared.sample(5, false, 1000);
    check(shared.counts.fresh == 0 && shared.counts.repeated == 1 && shared.counts.maxHoldNs == 930,
          "reuse age survives report windows");
    shared.sample(1, false, 1010);
    check(shared.counts.fresh == 1 && shared.counts.skipped == 0, "sequence restart does not underflow skips");
    shared = {};
    shared.sample(1, false, 2000);
    check(shared.counts.fresh == 1 && shared.counts.maxHoldNs == 0, "host lifecycle resets acquisition state");
    shared.sample(0, false, 2010);
    shared.sample(1, false, 2020);
    check(shared.counts.fresh == 2, "unavailable output ends the previous visible hold");
    if (!failures) std::puts("PASS: guest frame and shared acquisition metrics");
    return failures ? 1 : 0;
}
