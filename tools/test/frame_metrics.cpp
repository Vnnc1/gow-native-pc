#include "runtime/gow_frame_metrics.h"
#include <cstdio>
#include <limits>

int main()
{
    int failures = 0;
    auto check = [&](bool ok, const char *what) { if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); ++failures; } };
    gow_diagnostics::FrameWindow window;
    window.sort(); check(window.percentile(99) == 0, "empty window");
    window.add(-1); window.add(std::numeric_limits<double>::quiet_NaN()); window.add(std::numeric_limits<double>::infinity());
    check(window.count == 0, "invalid values ignored");
    for (int i = 100; i > 0; --i) window.add(i);
    window.sort();
    check(window.percentile(50) == 50 && window.percentile(95) == 95 && window.percentile(99) == 99, "nearest-rank percentiles");
    check(window.total == 5050 && window.maximum == 100 && window.over50 == 50 && window.over100 == 0, "totals and threshold boundaries");
    check(window.overBudget == 84 && window.over33 == 67, "frame budgets");
    window = {};
    for (int i = 0; i < 5000; ++i) window.add(10);
    window.add(500); window.sort();
    check(window.samples() == 4096 && window.count == 5001 && window.maximum == 500, "bounded window with complete totals");
    check(window.percentile(99) == 10 && window.over100 == 1, "sparse stall");
    window = {}; window.add(1000.0 / 60.0); window.sort();
    check(window.overBudget == 0 && window.percentile(99) == 1000.0 / 60.0, "exact boundary and single sample");
    if (!failures) std::puts("PASS: frame metrics (empty, invalid, percentile, budgets, overflow, sparse stall, reset)");
    return failures ? 1 : 0;
}
