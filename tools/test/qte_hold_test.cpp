// gow-native-pc: test of the "hold instead of mashing" logic (engine/patches/53-qte-hold-to-mash.patch, header
// engine/runtime/PS2Recomp/ps2xRuntime/include/runtime/gow_qte_hold.h). It needs the runtime fetched and patched
// (`build.cmd -Stages fetch`, or the launcher's Install tab).
//
//   clang++ -std=c++20 -I engine/runtime/PS2Recomp/ps2xRuntime/include tools/test/qte_hold_test.cpp -o qte_hold_test
//   ./qte_hold_test          (prints one line per case; exit code 1 and "FAIL" when one does not hold)
//
// What it checks is what the assist promises: a short press reaches the game untouched, a held button becomes presses
// at the chosen rate, the game sees them whether it polls at 60 or at 30 fps, the button stays down most of the time
// (so a "Hold" prompt still charges), and a button the player did not list is never touched.
#include "runtime/gow_qte_hold.h"
#include "runtime/gow_qte_prompt.h"

#include <cmath>

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

    // Protect every face/shoulder pair, including a face button repeated with R2.
    {
        gow_qte::Config all = config;
        all.buttons = 0xff00u;
        bool preserved = true;
        for (int first = 8; first < 16; ++first)
            for (int second = first + 1; second < 16; ++second)
            {
                const uint16_t buttons = static_cast<uint16_t>(~((1u << first) | (1u << second)));
                preserved &= gow_qte::forInput(all, buttons, false).buttons == 0;
            }
        check(preserved, "all face/shoulder combinations disable repetition");
        check(gow_qte::forInput(all, static_cast<uint16_t>(~kCircle), false).buttons == all.buttons,
              "a face button held alone still repeats");
        check(gow_qte::forInput(all, static_cast<uint16_t>(~kCircle), true).buttons == 0xf000u,
              "movement protects shoulders without disabling single face-button QTEs");
    }

    // Shoulder options use the same active-low bits as the game, independently.
    for (uint16_t shoulder : {0x0100u, 0x0200u, 0x0400u, 0x0800u})
    {
        gow_qte::Config selected = config;
        selected.buttons = shoulder;
        const Run run = hold(selected, shoulder | kCircle, 2.0, 60.0, kCircle);
        check(run.presses >= 16 && !run.otherEverUp, "selected shoulder repeats without touching circle");
        check(hold(selected, shoulder, 0.2, 60.0).presses == 1, "shoulder tap stays a single press");
    }
    for (double hz : {30.0, 60.0})
    {
        for (auto mode : {gow_qte::StickMode::Shake, gow_qte::StickMode::Rotate})
        {
            gow_qte::StickGesture gesture;
            bool left = false, right = false, up = false, down = false;
            bool active = true, stable = true;
            for (int i = 0; i < static_cast<int>(hz); ++i)
            {
                uint8_t x = 128, y = 128;
                active &= gesture.apply(mode, true, i / hz, x, y);
                left |= x < 32; right |= x > 224; up |= y < 32; down |= y > 224;
                uint8_t repeatX = 0, repeatY = 0;
                gesture.apply(mode, true, i / hz, repeatX, repeatY);
                stable &= x == repeatX && y == repeatY;
            }
            check(active && stable, "held gesture is active and same-time reads keep its phase");
            check(left && right, "gesture reaches both horizontal directions at 30/60 Hz");
            check(mode == gow_qte::StickMode::Rotate ? up && down : !up && !down,
                  "rotation covers vertical directions; shake stays horizontal");
            uint8_t x = 45, y = 200;
            check(!gesture.apply(mode, false, 2.0, x, y) && x == 45 && y == 200,
                  "release immediately preserves normal movement");
            gesture.apply(mode, true, 3.0, x, y);
            check(y == 128 && x == (mode == gow_qte::StickMode::Shake ? 1 : 255),
                  "a new hold resets the gesture phase");
            x = 45; y = 200;
            check(!gesture.apply(gow_qte::StickMode::Off, true, 4.0, x, y) && x == 45 && y == 200,
                  "disabled assistance leaves axes untouched");
        }
    }

    // zzz-329: the gesture follows a displayed guide; its defaults keep the original clockwise samples.
    {
        gow_qte::StickGesture original, guided;
        bool same = true;
        for (int i = 0; i < 40; ++i)
        {
            const double t = i / 60.0, angle = std::fmod(t, 0.5) * 12.566370614359172;
            uint8_t x = 0, y = 0;
            original.apply(gow_qte::StickMode::Rotate, true, t, x, y);
            same &= x == std::lround(128.0 + 127.0 * std::cos(angle)) && y == std::lround(128.0 + 127.0 * std::sin(angle));
        }
        check(same, "default rotation keeps the original clockwise samples");
        uint8_t x = 0, y = 0;
        guided.apply(gow_qte::StickMode::Rotate, true, 10.0, x, y, -1, 180.0);
        check(x == 128 && y == 255, "guided rotation starts at the guide's first key (down)");
        guided.apply(gow_qte::StickMode::Rotate, true, 10.0 + 0.0625, x, y, -1, 180.0);
        check(x > 200 && y > 200, "counter-clockwise from down passes down-right first");
        guided.apply(gow_qte::StickMode::Rotate, true, 10.125, x, y, -1, 180.0);
        check(x == 255 && y == 128, "a quarter turn later it is right, the guide's second key");
    }

    // zzz-329: keyboard sweep along a rotation guide.
    {
        using gow_qte_prompt::KeyboardSweep;
        using gow_qte_prompt::turnOf;
        check(turnOf({{2, 1, 0}, 3}) == -1 && turnOf({{0, 1, 2, 3, 0}, 5}) == 1 && turnOf({{0, 3, 2}, 3}) == -1 &&
                  turnOf({}) == 0 && turnOf({{0, 2, 0}, 3}) == 0,
              "guide direction from its first two keys");
        check(turnOf({{3, 1}, 2, 1}) == 1 && turnOf({{3, 1}, 2, -1}) == -1 && turnOf({{0, 2, 0}, 3, -1}) == -1,
              "short guides carry their turn: A > D over the top or under the bottom");
        auto angleOf = [](uint8_t x, uint8_t y) {
            double a = std::atan2(double(x) - 128.0, 128.0 - double(y)) * 57.29577951308232;
            return a < 0 ? a + 360.0 : a;
        };
        auto key = [](unsigned k, uint8_t &x, uint8_t &y) { // 0 up 1 right 2 down 3 left, 4 none
            x = k == 1 ? 255 : k == 3 ? 0 : 128;
            y = k == 0 ? 0 : k == 2 ? 255 : 128;
        };
        for (double hz : {15.0, 20.0, 30.0, 60.0})
        {
            // Taps with releases between them, the way issue 34's player pressed S, D, W for a CCW half turn.
            const unsigned taps[] = {2, 2, 4, 1, 1, 4, 0, 0};
            KeyboardSweep sweep;
            bool centred = false, diagonal = false, reversed = false, stable = true;
            double previous = -1.0, travelled = 0.0;
            double t = 5.0;
            for (int frame = 0; frame < 60; ++frame, t += 1.0 / hz)
            {
                uint8_t x, y;
                key(frame < 8 ? taps[frame] : 4, x, y);
                const uint8_t rawX = x, rawY = y;
                const bool on = sweep.apply(-1, t, x, y);
                if (!on)
                {
                    stable &= x == rawX && y == rawY;
                    continue;
                }
                uint8_t againX = rawX, againY = rawY;
                sweep.apply(-1, t, againX, againY);
                stable &= againX == x && againY == y;
                centred |= std::hypot(double(x) - 128.0, double(y) - 128.0) < 100.0;
                const double a = angleOf(x, y);
                diagonal |= a > 95.0 && a < 175.0;
                if (previous >= 0.0)
                {
                    double step = previous - a; // counter-clockwise lowers the angle
                    if (step < -180.0) step += 360.0;
                    if (step > 180.0) step -= 360.0;
                    reversed |= step < -0.5;
                    travelled += step;
                }
                previous = a;
            }
            const std::string rate = std::to_string(int(hz)) + " Hz: ";
            check(!centred, rate + "tapped keys never drop the stick to the centre during the guide");
            check(diagonal, rate + "the sweep passes the down-right diagonal between S and D");
            check(!reversed && travelled > 170.0 && travelled < 190.0, rate + "S, D, W make one counter-clockwise half turn");
            check(stable, rate + "repeated reads at one time agree; idle reads keep the raw axes");
        }
        {
            KeyboardSweep sweep;
            uint8_t x, y;
            key(2, x, y);
            sweep.apply(-1, 1.0, x, y);
            bool viaRight = false;
            for (int i = 1; i <= 20; ++i)
            {
                key(0, x, y);
                sweep.apply(-1, 1.0 + i / 60.0, x, y);
                viaRight |= x > 240;
            }
            check(viaRight && y < 8, "an opposite key turns the guide's way (down to up through right)");
            {
                KeyboardSweep half;
                uint8_t hx, hy;
                key(3, hx, hy);
                half.apply(-1, 7.0, hx, hy);
                bool viaBottom = false, viaTop = false;
                for (int i = 1; i <= 20; ++i)
                {
                    key(1, hx, hy);
                    half.apply(-1, 7.0 + i / 60.0, hx, hy);
                    viaBottom |= hy > 240;
                    viaTop |= hy < 16;
                }
                check(viaBottom && !viaTop && hx > 248, "A > D counter-clockwise sweeps under the bottom (Down180CCW)");
            }
            for (double hz : {30.0, 60.0})
            {
                // Full-turn guide (one held key): holding W turns the stick the prompt's way, never through the centre.
                KeyboardSweep spin;
                uint8_t sx, sy;
                double travelled = 0.0, previous = -1.0;
                bool centred = false, backwards = false;
                for (int i = 0; i <= int(0.55 * hz); ++i)
                {
                    key(0, sx, sy);
                    spin.apply(1, 20.0 + i / hz, sx, sy, true);
                    const double a = angleOf(sx, sy);
                    centred |= std::hypot(double(sx) - 128.0, double(sy) - 128.0) < 100.0;
                    if (previous >= 0.0)
                    {
                        double step = a - previous;
                        if (step < -180.0) step += 360.0;
                        if (step > 180.0) step -= 360.0;
                        backwards |= step < -0.5;
                        travelled += step;
                    }
                    previous = a;
                }
                const std::string rate = std::to_string(int(hz)) + " Hz: ";
                check(!centred && !backwards && travelled >= 360.0, rate + "holding W on a clockwise full turn spins at least once");
                key(4, sx, sy);
                spin.apply(1, 21.0, sx, sy, true);
                const uint8_t stopX = sx, stopY = sy;
                key(4, sx, sy);
                spin.apply(1, 21.1, sx, sy, true);
                check(sx == stopX && sy == stopY, rate + "releasing the key stops the turn where it is");
                key(4, sx, sy);
                check(!spin.apply(1, 21.5, sx, sy, true) && sx == 128 && sy == 128, rate + "then the stick centres");
                KeyboardSweep ccw;
                key(0, sx, sy);
                ccw.apply(-1, 30.0, sx, sy, true);
                key(0, sx, sy);
                ccw.apply(-1, 30.0 + 1.0 / hz, sx, sy, true);
                check(sx < 128, rate + "a counter-clockwise full turn leaves W towards A");
            }
            {
                // zzz-333: automatic stick QTE (Accessibility > automatic QTE)
                using gow_qte_prompt::AutoStick;
                AutoStick automatic;
                uint8_t ax = 77, ay = 99;
                check(!automatic.apply({{3, 1}, 2, -1}, 1.0, false, true, ax, ay) && ax == 77 && ay == 99,
                      "automatic stick: disabled leaves the axes untouched");
                check(!automatic.apply({{3, 1}, 2, -1}, 1.0, true, false, ax, ay) && ax == 77,
                      "automatic stick: focus loss leaves the axes untouched");
                check(!automatic.apply({}, 1.0, true, true, ax, ay) && ax == 77, "automatic stick: no guide, no input");
                const gow_qte_prompt::Sequence half{{3, 1}, 2, -1}; // Down180CCW: A > (S) > D
                automatic.apply(half, 10.0, true, true, ax, ay);
                check(ax < 8 && ay == 128, "automatic half turn starts at its first key (A)");
                automatic.apply(half, 10.2, true, true, ax, ay);
                check(ay > 248, "it passes under the bottom (S) counter-clockwise");
                automatic.apply(half, 10.35, true, true, ax, ay);
                check(ax > 248 && ay == 128, "and ends at its last key (D)");
                automatic.apply(half, 10.5, true, true, ax, ay);
                check(ax == 128 && ay == 128, "then releases so the next repetition is a new gesture");
                automatic.apply(half, 10.65, true, true, ax, ay);
                check(ax < 8, "and repeats from the first key");
                uint8_t bx = 0, by = 0;
                automatic.apply(half, 10.65, true, true, bx, by);
                check(bx == ax && by == ay, "repeated reads at one time agree");
                const gow_qte_prompt::Sequence full{{0}, 1, 1}; // 360CW: W, clockwise
                automatic.apply(full, 20.0, true, true, ax, ay);
                check(ax == 128 && ay < 8, "a new guide restarts: full turn starts at W");
                automatic.apply(full, 20.125, true, true, ax, ay);
                check(ax > 248, "and turns clockwise to D in an eighth of a second");
                automatic.apply(full, 20.25, true, true, ax, ay);
                check(ay > 248, "then S: two turns per second");
            }
            key(4, x, y);
            check(sweep.apply(-1, 1.5, x, y) && y < 8, "a released key holds the reached angle for a moment");
            key(4, x, y);
            check(!sweep.apply(-1, 1.9, x, y) && x == 128 && y == 128, "after the grace period the stick returns to the centre");
            key(1, x, y);
            check(!sweep.apply(0, 2.0, x, y) && x == 255 && y == 128, "without a guide the keys stay raw digital input");
            key(1, x, y);
            sweep.apply(1, 3.0, x, y);
            key(3, x, y);
            sweep.apply(1, 3.0 + 1.0 / 60.0, x, y);
            check(y > 128, "a clockwise guide turns right to left through down");
            key(2, x, y);
            sweep.apply(1, 4.0, x, y);
            key(1, x, y);
            sweep.apply(1, 4.5, x, y);
            check(x == 255 && y == 128, "a player turning against a guide still reaches the shorter target");
        }
    }

    std::printf(g_failures ? "\n%d case(s) failed\n" : "\nall cases passed\n", g_failures);
    return g_failures ? 1 : 0;
}
