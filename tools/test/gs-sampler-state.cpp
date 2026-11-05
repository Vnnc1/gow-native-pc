#undef NDEBUG
#include "runtime/gs/gs_sampler_state.h"
#include <cassert>
#include <cstdio>

int main()
{
    GSSamplerState cache[3];
    std::array<int, 4> driver[3]{};
    unsigned calls = 0;
    for (unsigned step = 0; step < 300; ++step)
    {
        const unsigned texture = step % 3;
        const std::array<int, 4> desired{{int((step / 12) % 2), int((step / 12) % 2),
                                       int((step / 24) % 2), int((step / 48) % 2)}};
        if (step % 17 == 0)
        {
            // Upload or recycled GL name: external parameter writes invalidate the cache.
            driver[texture] = {{7, 7, 7, 7}};
            cache[texture] = {};
        }
        const unsigned changed = cache[texture].apply(desired, [&](unsigned slot, int value) {
            driver[texture][slot] = value;
            ++calls;
        });
        assert(changed <= 4 && driver[texture] == desired);
        assert(cache[texture].apply(desired, [](unsigned, int) { assert(false); }) == 0);
    }
    assert(calls > 0 && calls < 300 * 4);
    std::printf("PASS: 300 texture state transitions, uploads and recycled names; %u/1200 driver calls\n", calls);
}
