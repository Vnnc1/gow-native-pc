// Controller input for the launcher (exposed to QML as "mando"): whether an XInput controller is connected, and, while the
// Controls tab captures a button, each button pressed. Codes are the game's (raylib GAMEPAD_BUTTON_*), so the layout
// chosen here is what ps2_pad.cpp reads from TOBIICHI_MANDO. XInput is loaded at run time (xinput1_4 / xinput9_1_0, part
// of Windows): Xbox controllers and anything that presents itself as one (Steam Input, DS4Windows).
// Linux uses SDL2's standardized game-controller mapping, translated to the same raylib codes.
#pragma once

#include <QObject>
#include <QString>
#include <QTimer>

#ifdef Q_OS_LINUX
struct _SDL_GameController;
#endif

class Mando : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool conectado READ conectado NOTIFY conectadoChanged)
    Q_PROPERTY(QString nombre READ nombre NOTIFY conectadoChanged)

public:
    explicit Mando(QObject *parent = nullptr);
    ~Mando() override;

    bool conectado() const { return m_slot >= 0; }
    QString nombre() const;
    // capture mode: polls every frame and emits boton() for each press
    Q_INVOKABLE void escuchar(bool activo);

signals:
    void conectadoChanged();
    void boton(int codigo);

private:
    void leer();

    QTimer m_timer;
    int m_slot = -1;           // XInput user index of the connected controller
    unsigned m_previos = 0;    // buttons held at the last poll (raylib codes as bits)
    bool m_escuchando = false;
#ifdef Q_OS_LINUX
    _SDL_GameController *m_controller = nullptr;
    bool m_sdlReady = false;
#endif
};
