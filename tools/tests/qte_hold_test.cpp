// gow-native-pc: test of the "hold instead of mashing" logic (engine/patches/17-qte-hold-to-mash.patch, header
// engine/runtime/PS2Recomp/ps2xRuntime/include/runtime/gow_qte_hold.h). It needs the runtime fetched and patched
// (`build.cmd -Stages fetch`, or the launcher's Install tab).
//
//   clang++ -std=c++20 -I engine/runtime/PS2Recomp/ps2xRuntime/include tools/tests/qte_hold_test.cpp -o qte_hold_test
//   ./qte_hold_test          (prints one line per case; exit code 1 and "FAIL" when one does not hold)
//
// What it checks is what the assist promises: a short press reaches the game untouched, a held button becomes presses
// at the chosen rate, the game sees them whether it polls at 60 or at 30 fps, the button stays down most of the time
// (so a "Hold" prompt still charges), and a button the player did not list is never touched.
#include "runtime/gow_qte_hold.h"

#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>

namespace
{
    constexpr uint16_t kCircle = 0x2000u; // PAD_CIRCLE of ps2_pad.cpp
    constexpr uint16_t kCross = 0x4000u;
    constexpr uint16_t kAll = 0xFFFFu;    // nothing pressed (the bits are active low)

    int g_failures = 0;

    void check(bool ok, const std::string &what)
    {
        std::printf("%s  %s\n", ok ? "ok  " : "FAIL", what.c_str());
        if (!ok)
            ++g_failures;
    }

    struct Run
    {
        int presses = 0;   // presses the game would count (a poll that reads released, then one that reads pressed)
        int polls = 0;     // polls made
        int down = 0;      // polls that read the button as pressed
        bool otherEverUp = false; // a second held button ever read as released
    };

    // Holds `held` of the config's buttons for `seconds`, polled at `hz` as the game polls the pad once per frame.
    Run hold(const gow_qte::Config &config, uint16_t held, double seconds, double hz, uint16_t watch = 0u)
    {
        gow_qte::HoldToMash assist;
        Run run;
        bool wasDown = false;
        for (double t = 0.0; t <= seconds; t += 1.0 / hz)
        {
            const uint16_t out = assist.apply(config, static_cast<uint16_t>(kAll & ~held), t);
            const bool isDown = (out & config.buttons) != config.buttons; // any assisted button pressed
            if (isDown && !wasDown)
                ++run.presses;
            wasDown = isDown;
            ++run.polls;
            run.down += isDown ? 1 : 0;
            if (watch && (out & watch))
                run.otherEverUp = true;
        }
        return run;
    }
}

int main()
{
    gow_qte::Config config; // the launcher's defaults: circle, 10 presses/s, after 250 ms, 34 ms released
    config.buttons = kCircle;

    // A press the player could have made alone reaches the game as one press.
    const Run tap = hold(config, kCircle, 0.2, 60.0);
    check(tap.presses == 1 && tap.down == tap.polls, "a 200 ms press stays one press, never released");

    // Held: presses at the chosen rate. 2 s - 250 ms of assist at 10 /s = 17 gaps, plus the press itself.
    const Run held = hold(config, kCircle, 2.0, 60.0);
    check(held.presses >= 16 && held.presses <= 19,
          "2 s held at 60 fps = " + std::to_string(held.presses) + " presses (expected 18 +-2)");
    check(held.down * 100 / held.polls >= 60,
          "the button stays down " + std::to_string(held.down * 100 / held.polls) + " % of the time (expected >= 60)");

    // The game polling at 30 fps still sees every gap (34 ms covers a 33 ms frame).
    const Run slow = hold(config, kCircle, 2.0, 30.0);
    check(slow.presses >= 15, "2 s held at 30 fps = " + std::to_string(slow.presses) + " presses (expected >= 15)");

    // A button the player did not list is never touched, even held at the same time.
    const Run other = hold(config, static_cast<uint16_t>(kCircle | kCross), 2.0, 60.0, kCross);
    check(!other.otherEverUp, "a button outside the list is never released");

    // Letting go and pressing again starts over: the second short press is untouched.
    {
        gow_qte::HoldToMash assist;
        int presses = 0, releases = 0;
        bool wasDown = false;
        double t = 0.0;
        for (int i = 0; i < 60; ++i, t += 1.0 / 60.0) // held 1 s: the assist is running
            assist.apply(config, static_cast<uint16_t>(kAll & ~kCircle), t);
        for (int i = 0; i < 12; ++i, t += 1.0 / 60.0) // released for 200 ms
            assist.apply(config, kAll, t);
        for (int i = 0; i < 12; ++i, t += 1.0 / 60.0) // pressed again, 200 ms: shorter than the delay
        {
            const bool down = (assist.apply(config, static_cast<uint16_t>(kAll & ~kCircle), t) & kCircle) == 0u;
            if (down && !wasDown)
                ++presses;
            if (!down)
                ++releases;
            wasDown = down;
        }
        check(presses == 1 && releases == 0, "after letting go, a short press is one press again");
    }

    // Off by default: with no button chosen nothing changes.
    {
        gow_qte::HoldToMash assist;
        const gow_qte::Config off;
        bool changed = false;
        for (int i = 0; i < 120; ++i)
            changed |= assist.apply(off, static_cast<uint16_t>(kAll & ~kCircle), i / 60.0) != (kAll & ~kCircle);
        check(!changed, "with no button chosen the pad reaches the game unchanged");
    }

    // The fastest setting still works with the 60 fps poll (release clamped to half the period).
    {
        gow_qte::Config fast = config;
        fast.period = 1.0 / 20.0;
        const Run run = hold(fast, kCircle, 2.0, 60.0);
        check(run.presses >= 15, "20 presses/s gives " + std::to_string(run.presses) + " presses in 2 s (expected >= 15)");
    }

    std::printf(g_failures ? "\n%d case(s) failed\n" : "\nall cases passed\n", g_failures);
    return g_failures ? 1 : 0;
}
