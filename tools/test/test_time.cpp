#include "runtime/gow_test_time.h"
#include <cstdio>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"line %d failed\n",__LINE__); return 1; } } while (0)
int main() {
    using namespace gow_test_time;
    CHECK(parse("12.5") == 12.5);
    CHECK(parse("g12.5") == gameplay + 12.5);
    CHECK(parse("f240") == frame + 240);
    CHECK(!reached(parse("f0"), 100, -1, 0));
    CHECK(reached(parse("f0"), 20, 20, 0));
    CHECK(!reached(parse("f240"), 100, 20, 239));
    CHECK(reached(parse("f240"), 30, 20, 240));
    CHECK(reached(parse("f240"), 100, 20, 240));
    CHECK(!reached(parse("f240") + 60, 100, 20, 299));
    CHECK(reached(parse("f240") + 60, 30, 20, 300));
    CHECK(!reached(parse("g10"), 100, -1, 999));
    CHECK(!reached(parse("g10"), 29, 20, 999));
    CHECK(reached(parse("g10"), 30, 20, 0));
    CHECK(reached(parse("10"), 10, -1, 0));
    GowTestFrameProbe probe;
    probe.begin(60, 1.0);
    probe.observe(60, 1.001);
    CHECK(probe.intervals.count == 0);
    probe.observe(61, 1.010);
    probe.observe(62, 1.030);
    CHECK(probe.intervals.count == 2 && probe.skipped == 0);
    probe.observe(64, 1.050);
    CHECK(probe.skipped == 1);
    const auto window = probe.intervals.analyze(); // patch 93 FrameWindow API
    CHECK(window.p95 > 19.9 && window.p95 < 20.1);
    std::puts("PASS: independent wall/gameplay/frame clocks and hold boundaries");
}
