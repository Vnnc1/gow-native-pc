#undef NDEBUG
#include "gs_alpha_bounds.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

int main()
{
    unsigned long long cases = 0;
    for (unsigned test = 0; test < 8; ++test)
    for (unsigned ref = 0; ref < 256; ++ref)
    {
        unsigned accepted[257]{};
        for (unsigned a = 0; a < 256; ++a)
        {
            const bool predicate[] = {false, true, a < ref, a <= ref, a == ref, a >= ref, a > ref, a != ref};
            accepted[a + 1] = accepted[a] + predicate[test];
        }
        for (unsigned lo = 0; lo < 256; ++lo)
        for (unsigned hi = lo; hi < 256; ++hi)
        {
            const auto plan = gsAlphaBounds(test, ref, lo, hi);
            const unsigned count = accepted[hi + 1] - accepted[lo];
            assert(plan.allPass == (count == hi - lo + 1));
            assert(plan.allFail == (count == 0));
            ++cases;
        }
    }
    for (const auto plan : {gsAlphaBounds(8, 0, 0, 255), gsAlphaBounds(0, 0, 10, 9), gsAlphaBounds(1, 256, 0, 255)})
        assert(!plan.allPass && !plan.allFail);
    std::printf("PASS: %llu alpha intervals match exhaustive fragment predicates\n", cases);
}
