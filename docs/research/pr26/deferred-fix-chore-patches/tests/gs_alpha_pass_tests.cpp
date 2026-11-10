#include "gs_alpha_pass.h"
#include <array>
#include <cstdio>

// Independent fragment oracle: each bit represents a color/depth component
// written by the shader's passing or failing draw. Keep draw order observable.
static bool accepts(unsigned test, unsigned alpha, unsigned ref)
{
    switch (test) {
    case 0: return false;
    case 1: return true;
    case 2: return alpha < ref;
    case 3: return alpha <= ref;
    case 4: return alpha == ref;
    case 5: return alpha >= ref;
    case 6: return alpha > ref;
    default: return alpha != ref;
    }
}

int main()
{
    unsigned long long cases = 0;
    for (unsigned ate = 0; ate < 2; ++ate)
    for (unsigned test = 0; test < 8; ++test)
    for (unsigned fail = 0; fail < 4; ++fail)
    for (unsigned noTest = 0; noTest < 2; ++noTest)
    for (unsigned noFail = 0; noFail < 2; ++noFail)
    {
        const auto plan = gsAlphaPassPlan(ate, test, fail, noTest, noFail, true);
        const auto reference = gsAlphaPassPlan(ate, test, fail, noTest, noFail, false);
        if (!reference.passing || reference.failing != (ate && fail && !noFail)) return 1;
        if (plan.passing != !(ate && !noTest && test == 0)) return 2;
        if (plan.failing != (ate && fail && !noFail && test != 1)) return 3;
        for (unsigned alpha = 0; alpha < 256; ++alpha)
        for (unsigned ref = 0; ref < 256; ++ref)
        {
            const bool pass = !ate || accepts(test, alpha, ref);
            // AFAIL: KEEP, FB_ONLY, ZB_ONLY, RGB_ONLY. Frame/depth masks
            // can only remove writes from these identical sequences.
            constexpr unsigned failMasks[] = {0, 15, 16, 7};
            const std::array<unsigned, 2> oldWrites = {
                noTest || pass ? 31u : 0u,
                ate && fail && !noFail && !pass ? failMasks[fail] : 0u};
            const std::array<unsigned, 2> newWrites = {
                plan.passing && (noTest || pass) ? 31u : 0u,
                plan.failing && !pass ? failMasks[fail] : 0u};
            if (oldWrites != newWrites) return 4;
            ++cases;
        }
    }
    std::printf("PASS: %llu alpha/reference/control combinations preserve ordered fragment writes\n", cases);
}
