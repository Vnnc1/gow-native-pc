#include "mando.h"

#ifdef Q_OS_WIN
#include <windows.h>
#include <xinput.h>
#elif defined(Q_OS_LINUX)
#include <SDL.h>
#endif

namespace
{
#ifdef Q_OS_WIN
    using XInputGetStateFn = DWORD(WINAPI *)(DWORD, XINPUT_STATE *);
    XInputGetStateFn xinputGetState()
    {
        static const XInputGetStateFn fn = []() -> XInputGetStateFn
        {
            for (const wchar_t *dll : {L"xinput1_4.dll", L"xinput9_1_0.dll", L"xinput1_3.dll"})
                if (HMODULE module = LoadLibraryW(dll))
                    if (auto f = reinterpret_cast<XInputGetStateFn>(GetProcAddress(module, "XInputGetState")))
                        return f;
            return nullptr;
        }();
        return fn;
    }

    // XInput buttons -> raylib GAMEPAD_BUTTON_* (the codes the game reads), as bit (1 << code)
    unsigned codigos(const XINPUT_GAMEPAD &g)
    {
        static const struct { WORD xinput; int raylib; } tabla[] = {
            {XINPUT_GAMEPAD_DPAD_UP, 1}, {XINPUT_GAMEPAD_DPAD_RIGHT, 2}, {XINPUT_GAMEPAD_DPAD_DOWN, 3},
            {XINPUT_GAMEPAD_DPAD_LEFT, 4}, {XINPUT_GAMEPAD_Y, 5}, {XINPUT_GAMEPAD_B, 6}, {XINPUT_GAMEPAD_A, 7},
            {XINPUT_GAMEPAD_X, 8}, {XINPUT_GAMEPAD_LEFT_SHOULDER, 9}, {XINPUT_GAMEPAD_RIGHT_SHOULDER, 11},
            {XINPUT_GAMEPAD_BACK, 13}, {XINPUT_GAMEPAD_START, 15}, {XINPUT_GAMEPAD_LEFT_THUMB, 16},
            {XINPUT_GAMEPAD_RIGHT_THUMB, 17}};
        unsigned bits = 0;
        for (const auto &t : tabla)
            if (g.wButtons & t.xinput)
                bits |= 1u << t.raylib;
        // triggers: pressed past a quarter of their travel (LT 10, RT 12)
        if (g.bLeftTrigger > 64)
            bits |= 1u << 10;
        if (g.bRightTrigger > 64)
            bits |= 1u << 12;
        return bits;
    }
#endif
}

Mando::Mando(QObject *parent) : QObject(parent)
{
#ifdef Q_OS_LINUX
    m_sdlReady = SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) == 0;
#endif
    connect(&m_timer, &QTimer::timeout, this, &Mando::leer);
    m_timer.start(1000); // connection check; escuchar() polls every frame
    leer();
}

Mando::~Mando()
{
#ifdef Q_OS_LINUX
    if (m_controller) SDL_GameControllerClose(m_controller);
    if (m_sdlReady) SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER);
#endif
}

QString Mando::nombre() const
{
#ifdef Q_OS_LINUX
    return m_controller ? QString::fromUtf8(SDL_GameControllerName(m_controller)) : QString();
#else
    return m_slot >= 0 ? QStringLiteral("XInput %1").arg(m_slot + 1) : QString();
#endif
}

void Mando::escuchar(bool activo)
{
    m_escuchando = activo;
    m_timer.setInterval(activo ? 16 : 1000);
    m_previos = ~0u; // buttons already held when the capture opens do not count
    leer();
}

void Mando::leer()
{
    int slot = -1;
    unsigned bits = 0;
#ifdef Q_OS_WIN
    const XInputGetStateFn get = xinputGetState();
    if (get)
        for (DWORD i = 0; i < 4 && slot < 0; ++i)
        {
            XINPUT_STATE state{};
            if (get(i, &state) == ERROR_SUCCESS)
            {
                slot = static_cast<int>(i);
                bits = codigos(state.Gamepad);
            }
        }
#elif defined(Q_OS_LINUX)
    if (!m_sdlReady) return;
    SDL_PumpEvents();
    SDL_GameControllerUpdate();
    if (m_controller && !SDL_GameControllerGetAttached(m_controller)) {
        SDL_GameControllerClose(m_controller);
        m_controller = nullptr;
    }
    if (!m_controller) {
        for (int i = 0; i < SDL_NumJoysticks() && !m_controller; ++i)
            if (SDL_IsGameController(i)) m_controller = SDL_GameControllerOpen(i);
    }
    if (m_controller) {
        slot = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(m_controller));
        static const struct { SDL_GameControllerButton button; int code; } mapping[] = {
            {SDL_CONTROLLER_BUTTON_DPAD_UP, 1}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, 2},
            {SDL_CONTROLLER_BUTTON_DPAD_DOWN, 3}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, 4},
            {SDL_CONTROLLER_BUTTON_Y, 5}, {SDL_CONTROLLER_BUTTON_B, 6},
            {SDL_CONTROLLER_BUTTON_A, 7}, {SDL_CONTROLLER_BUTTON_X, 8},
            {SDL_CONTROLLER_BUTTON_LEFTSHOULDER, 9}, {SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, 11},
            {SDL_CONTROLLER_BUTTON_BACK, 13}, {SDL_CONTROLLER_BUTTON_START, 15},
            {SDL_CONTROLLER_BUTTON_LEFTSTICK, 16}, {SDL_CONTROLLER_BUTTON_RIGHTSTICK, 17}};
        for (const auto &entry : mapping)
            if (SDL_GameControllerGetButton(m_controller, entry.button)) bits |= 1u << entry.code;
        if (SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_TRIGGERLEFT) > 8192) bits |= 1u << 10;
        if (SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT) > 8192) bits |= 1u << 12;
    }
    // Qt owns the UI event loop; discard SDL events after polling to bound its queue.
    SDL_FlushEvents(SDL_FIRSTEVENT, SDL_LASTEVENT);
#endif
    if (slot != m_slot)
    {
        m_slot = slot;
        emit conectadoChanged();
    }
    if (m_escuchando)
    {
        const unsigned nuevos = bits & ~m_previos;
        m_previos = bits;
        for (int codigo = 1; codigo <= 17; ++codigo)
            if (nuevos & (1u << codigo))
            {
                emit boton(codigo);
                break;
            }
    }
}
