#undef NDEBUG
// zzz-326: GSFrameLatency with fake fences. A fence is an id; `done` holds the ids the fake GPU has completed.
#include "runtime/gs/gs_frame_latency.h"
#include <cassert>
#include <set>
#include <vector>

namespace
{
    struct Gpu
    {
        int next = 1;
        bool failCreate = false;
        bool waitTimesOut = false;
        std::set<int> done, live;
        std::vector<int> waited;
        int create()
        {
            if (failCreate) return 0;
            live.insert(next);
            return next++;
        }
        bool poll(int f) const { return done.count(f) != 0; }
        bool wait(int f)
        {
            waited.push_back(f);
            if (waitTimesOut) return false;
            done.insert(f); // a client wait returns once the GPU reached the fence
            return true;
        }
        void destroy(int f)
        {
            assert(live.erase(f) == 1); // every fence deleted exactly once
        }
    };

    GSFrameLatency<int>::Result frame(GSFrameLatency<int> &l, Gpu &g, unsigned limit)
    {
        return l.endFrame(limit, [&] { return g.create(); }, [&](int f) { return g.poll(f); },
                          [&](int f) { return g.wait(f); }, [&](int f) { g.destroy(f); });
    }
}

int main()
{
    using L = GSFrameLatency<int>;
    assert(L::clampLimit(-3) == 0u && L::clampLimit(0) == 0u && L::clampLimit(2) == 2u);
    assert(L::clampLimit(100) == L::kMaxLimit);

    {   // GPU keeps up: completed fences retire by polling, never a wait
        L l; Gpu g;
        for (int i = 0; i < 100; ++i)
        {
            const auto r = frame(l, g, 2);
            assert(r.waits == 0 && l.pending() <= 2u);
            g.done.insert(g.next - 1); // the frame just queued completes before the next one ends
        }
        assert(g.waited.empty());
    }
    {   // GPU-bound: never more than `limit` frames in flight, the oldest is the one waited on
        L l; Gpu g;
        assert(frame(l, g, 2).waits == 0 && frame(l, g, 2).waits == 0);
        assert(l.pending() == 2u);
        const auto r = frame(l, g, 2);
        assert(r.waits == 1 && r.timeouts == 0 && g.waited == std::vector<int>{1} && l.pending() == 2u);
        for (int i = 0; i < 50; ++i)
        {
            assert(frame(l, g, 2).waits == 1 && l.pending() == 2u);
        }
        for (size_t i = 1; i < g.waited.size(); ++i) assert(g.waited[i] == g.waited[i - 1] + 1); // FIFO order
    }
    {   // timeouts never block further and never leak: the fence is dropped and the frame continues
        L l; Gpu g; g.waitTimesOut = true;
        for (int i = 0; i < 20; ++i)
        {
            const auto r = frame(l, g, 1);
            assert(l.pending() == 1u && r.waits == r.timeouts && r.waits <= 1u);
        }
        assert(g.live.size() == 1u);
    }
    {   // no fence (driver failure): no throttling, nothing queued
        L l; Gpu g; g.failCreate = true;
        assert(frame(l, g, 2).waits == 0 && l.pending() == 0u);
    }
    {   // lowering the limit drains to it; 0 disables and releases every fence
        L l; Gpu g;
        for (int i = 0; i < 3; ++i) frame(l, g, 7);
        assert(l.pending() == 3u);
        assert(frame(l, g, 1).waits == 3u && l.pending() == 1u);
        assert(frame(l, g, 0).waits == 0 && l.pending() == 0u && g.live.empty());
        // over-large limits are clamped below the ring capacity
        for (int i = 0; i < 40; ++i) frame(l, g, 1000);
        assert(l.pending() == L::kMaxLimit);
        l.clear([&](int f) { g.destroy(f); });
        assert(l.pending() == 0u && g.live.empty());
    }
    return 0;
}
