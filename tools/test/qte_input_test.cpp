// Production keyboard-stick integration with a fake host input backend; no window or game data.
#include "raylib.h"
#include "runtime/ps2_pad.h"
#include "runtime/gow_qte_prompt.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>

bool tobiichiSticksTeclado(uint8_t (&sticks)[4]);
namespace {
std::array<bool, 512> keys{};
std::array<bool, 8> mouse{};
std::array<bool, 4> pads{};
bool focused = true;
double clockTime = 0;
int failures = 0;
void check(bool pass, const char *name) {
    std::printf("%s %s\n", pass ? "ok" : "FAIL", name);
    failures += !pass;
}
void env(const char *key, const char *value) {
#ifdef _WIN32
    _putenv_s(key, value);
#else
    setenv(key, value, 1);
#endif
}
}
extern "C" {
bool IsKeyDown(int code) { return code >= 0 && code < int(keys.size()) && keys[code]; }
bool IsMouseButtonDown(int code) { return code >= 0 && code < int(mouse.size()) && mouse[code]; }
bool IsGamepadAvailable(int slot) { return slot >= 0 && slot < 4 && pads[slot]; }
bool IsGamepadButtonPressed(int, int) { return false; }
bool IsGamepadButtonDown(int, int) { return false; }
float GetGamepadAxisMovement(int, int) { return 0; }
const char *GetGamepadName(int) { return "test"; }
void SetGamepadVibration(int, float, float, float) {}
bool IsWindowFocused() { return focused; }
bool IsWindowReady() { return true; }
double GetTime() { return clockTime; }
}
#ifdef _WIN32
bool ps2PadWindowsRumble(uint8_t, bool) { return false; }
#endif

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "shake";
    const bool smoke = std::strcmp(mode, "smoke") == 0;
    const bool off = smoke || std::strcmp(mode, "off") == 0;
    env("GOW_QTE_STICK", smoke ? "rotate" : mode);
    env("GOW_PAD_TEST", smoke ? "1" : "0");
    env("TOBIICHI_TECLAS", "li_arriba=87;li_abajo=83;li_izq=65;li_der=68;ld_izq=74;ld_mod=341,342;cross=32;qte_stick=71,1003;l1=81;r1=69;l2=90;r2=345;circle=70");
    env("GOW_QTE_HOLD", "circle,cross,square,triangle,l1,l2,r1,r2");
    env("GOW_QTE_HOLD_HZ", "10");
    keys[KEY_D] = keys[KEY_J] = true;
    uint8_t sticks[4]{};
    check(tobiichiSticksTeclado(sticks) && sticks[0] < 32 && sticks[2] > 224,
          "normal keyboard directions reach the final stick reader");
    keys[KEY_G] = true;
    tobiichiSticksTeclado(sticks);
    clockTime = 0.2;
    tobiichiSticksTeclado(sticks);
    check(sticks[0] < 32 && sticks[1] == 128, "gesture preserves right-stick input");
    check(off ? sticks[2] > 224 : (std::strcmp(mode, "shake") == 0 ? sticks[2] == 255 : sticks[2] < 128),
          "selected mode reaches the production input path");
    keys[KEY_G] = false;
    check(tobiichiSticksTeclado(sticks) && sticks[2] > 224 && sticks[3] == 128,
          "release restores the player's movement");
    mouse[3] = true;
    tobiichiSticksTeclado(sticks);
    clockTime += 0.3;
    tobiichiSticksTeclado(sticks);
    check(off ? sticks[2] > 224 : sticks[2] < 128, "remapped mouse button drives the same gesture");
    focused = false;
    check(tobiichiSticksTeclado(sticks) && sticks[2] > 224 && sticks[3] == 128,
          "focus loss stops gesture injection");
    focused = true;
    for (int slot = 0; slot < 4; ++slot) {
        pads[slot] = true;
        check(!tobiichiSticksTeclado(sticks), "a connected controller retains its sticks in every slot");
        pads[slot] = false;
    }
    keys.fill(false); mouse.fill(false);
    PSPadBackend backend;
    uint8_t state[32]{};
    keys[KEY_LEFT_CONTROL] = true; // R2 is mapped to right Ctrl: aliases must agree.
    bool preserved = true;
    for (int direction : {KEY_W, KEY_A, KEY_S, KEY_D}) {
        keys[direction] = true;
        for (int frame = 0; frame < 60; ++frame) {
            clockTime += 1.0 / 60.0;
            backend.readState(0, 0, state, sizeof(state));
            const uint16_t buttons = state[2] | (state[3] << 8);
            preserved &= !(buttons & 0x0200) && state[4] == 128 && state[5] == 128;
            tobiichiSticksTeclado(sticks);
            preserved &= sticks[0] == 128 && sticks[1] == 128 && (sticks[2] != 128 || sticks[3] != 128);
        }
        keys[direction] = false;
    }
    check(preserved, "Ctrl + WASD preserves held R2 and left-stick movement without rolling");
    keys[KEY_SPACE] = true;
    preserved = true;
    for (int frame = 0; frame < 60; ++frame) {
        clockTime += 1.0 / 60.0;
        backend.readState(0, 0, state, sizeof(state));
        const uint16_t buttons = state[2] | (state[3] << 8);
        preserved &= !(buttons & (0x0200 | 0x4000));
    }
    check(preserved, "Ctrl + Space keeps both R2 and Cross held even with all face and shoulder repeats enabled");
    keys[KEY_SPACE] = false;
    clockTime += 1.0;
    backend.readState(0, 0, state, sizeof(state));
    check(!(state[3] & 0x02), "leaving a chord restarts the shoulder repeat delay");
    clockTime += 0.33;
    backend.readState(0, 0, state, sizeof(state));
    check(state[3] & 0x02, "R2 held alone still supports optional QTE repetition");
    keys[KEY_LEFT_CONTROL] = false;
    keys[KEY_LEFT_ALT] = keys[KEY_D] = true;
    tobiichiSticksTeclado(sticks);
    check(sticks[0] > 224 && sticks[2] == 128 && sticks[3] == 128,
          "dedicated Alt + movement still drives the evade stick");
    // zzz-329: a published rotation guide (CCW half turn from down: S, D, W) through the production reader.
    keys.fill(false); mouse.fill(false);
    const gow_qte_prompt::Sequence guide{{2, 1, 0}, 3};
    clockTime = 50.0;
    gow_qte_prompt::publish(0, guide);
    keys[KEY_S] = true;
    tobiichiSticksTeclado(sticks);
    keys[KEY_S] = false;
    clockTime += 1.0 / 30.0;
    gow_qte_prompt::publish(0, guide);
    tobiichiSticksTeclado(sticks);
    check(smoke ? sticks[3] == 128 : sticks[2] == 128 && sticks[3] == 255,
          "a released guide key keeps the stick out (scripted tests keep raw keys)");
    keys[KEY_D] = true;
    clockTime += 1.0 / 30.0;
    gow_qte_prompt::publish(0, guide);
    tobiichiSticksTeclado(sticks);
    check(smoke ? sticks[2] == 255 && sticks[3] == 128 : sticks[2] > 128 && sticks[2] < 255 && sticks[3] > 128,
          "the next guide key sweeps through the diagonal instead of jumping");
    keys[KEY_D] = false;
    gow_qte_prompt::publish(0);
    clockTime += 1.0 / 30.0;
    check(tobiichiSticksTeclado(sticks) && sticks[2] == 128 && sticks[3] == 128,
          "without a guide on screen released keys centre the stick at once");
    keys[KEY_G] = true;
    clockTime += 1.0;
    gow_qte_prompt::publish(0, guide);
    tobiichiSticksTeclado(sticks);
    const bool rotate = std::strcmp(mode, "rotate") == 0;
    check(!rotate || (sticks[2] == 128 && sticks[3] == 255), "held gesture starts at the guide's first key");
    clockTime += 0.0625;
    gow_qte_prompt::publish(0, guide);
    tobiichiSticksTeclado(sticks);
    check(!rotate || (sticks[2] > 200 && sticks[3] > 200), "held gesture turns the guide's way (counter-clockwise)");
    keys[KEY_G] = false;
    gow_qte_prompt::publish(0);
    return failures ? 1 : 0;
}
