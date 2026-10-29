#include "lanzador.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QDateTime>
#include <QGuiApplication>
#include <QImage>
#include <QImageReader>
#include <QProcessEnvironment>
#include <QScreen>
#include <QSettings>
#include <QStandardPaths>
#include <QTextStream>
#include <QTimer>

#include <algorithm>
#include <cmath>
#include <utility>

namespace
{
    // XOR of every 32-bit word of the ELF (the CRC PCSX2 identifies games by).
    constexpr quint32 kCrcGodOfWar = 0xD6385328u;

#ifdef Q_OS_WIN
    const QString kNombreEjecutable = QStringLiteral("ps2EntryRunner.exe");
#else
    const QString kNombreEjecutable = QStringLiteral("ps2EntryRunner");
#endif

    // Runtime settings for the game (as in Waffle565's play.cmd / run_gow.sh): VIF1/VU1/GIF on the GS
    // thread, asynchronous FINISH and sound on the default output. A variable already set in the user's environment
    // is kept, so runs can be compared without touching the launcher.
    const std::pair<const char *, const char *> kEntornoBase[] = {
        {"PS2X_GS_WORKER", "1"},
        {"GOW_GS_FINISH_ASINCRONO", "1"},
        {"GOW_AUDIO_DEVICE", "default"},
    };

    QString leerTexto(const QString &ruta)
    {
        QFile archivo(ruta);
        if (!archivo.open(QIODevice::ReadOnly))
            return {};
        return QString::fromUtf8(archivo.readAll()).trimmed();
    }

    // Commercial name from pci.ids: "Rembrandt [Radeon 680M]" -> "Radeon 680M".
    QString nombrePci(const QString &fabricante, const QString &dispositivo)
    {
        static const QStringList bases = {QStringLiteral("/usr/share/hwdata/pci.ids"), QStringLiteral("/usr/share/misc/pci.ids"),
                                          QStringLiteral("/usr/share/pci.ids")};
        for (const QString &base : bases)
        {
            QFile archivo(base);
            if (!archivo.open(QIODevice::ReadOnly | QIODevice::Text))
                continue;
            QTextStream entrada(&archivo);
            bool dentro = false;
            while (!entrada.atEnd())
            {
                const QString linea = entrada.readLine();
                if (linea.isEmpty() || linea.startsWith(QLatin1Char('#')))
                    continue;
                if (!linea.startsWith(QLatin1Char('\t')))
                {
                    if (dentro)
                        break;
                    dentro = linea.startsWith(fabricante + QStringLiteral("  "));
                    continue;
                }
                if (dentro && !linea.startsWith(QStringLiteral("\t\t")) && linea.mid(1, 4) == dispositivo)
                {
                    QString nombre = linea.mid(7).trimmed();
                    const qsizetype abre = nombre.indexOf(QLatin1Char('['));
                    const qsizetype cierra = nombre.lastIndexOf(QLatin1Char(']'));
                    if (abre >= 0 && cierra > abre)
                        nombre = nombre.mid(abre + 1, cierra - abre - 1);
                    return nombre;
                }
            }
        }
        return {};
    }

    QString nombreFabricante(const QString &id)
    {
        if (id == QStringLiteral("10de"))
            return QStringLiteral("NVIDIA");
        if (id == QStringLiteral("1002"))
            return QStringLiteral("AMD");
        if (id == QStringLiteral("8086"))
            return QStringLiteral("Intel");
        return id.toUpper();
    }

    QString buscarHaciaArriba(const QString &desde, const QString &relativa)
    {
        QDir dir(desde);
        for (int nivel = 0; nivel < 6; ++nivel)
        {
            const QString candidata = dir.absoluteFilePath(relativa);
            if (QFileInfo::exists(candidata))
                return QDir::cleanPath(candidata);
            if (!dir.cdUp())
                break;
        }
        return {};
    }

    QString primeraIso(const QString &carpeta)
    {
        const QFileInfoList isos = QDir(carpeta).entryInfoList({QStringLiteral("*.iso"), QStringLiteral("*.ISO")}, QDir::Files, QDir::Name);
        return isos.isEmpty() ? QString() : isos.first().absoluteFilePath();
    }
}

Lanzador::Lanzador(QObject *parent) : QObject(parent)
{
    QDir().mkpath(carpetaDatos() + QStringLiteral("/registros"));
}

Lanzador::~Lanzador()
{
    // The game stays open if the launcher closes: the process is detached instead of killed.
    if (m_proceso && m_proceso->state() != QProcess::NotRunning)
    {
        m_proceso->disconnect(this);
        m_proceso->setParent(nullptr);
    }
}

bool Lanzador::jugando() const
{
    return m_proceso && m_proceso->state() != QProcess::NotRunning;
}

QString Lanzador::version() const
{
    return QStringLiteral(TOBIICHI_VERSION);
}

QString Lanzador::sistema() const
{
#ifdef Q_OS_WIN
    return QStringLiteral("windows");
#else
    return QStringLiteral("linux");
#endif
}

QString Lanzador::carpetaDatos() const
{
    return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
}

QString Lanzador::rutaIcono() const
{
    return carpetaDatos() + QStringLiteral("/icono.png");
}

QString Lanzador::rutaRegistro() const
{
    return carpetaDatos() + QStringLiteral("/registros/ultimo.log");
}

QVariantList Lanzador::tarjetasGraficas() const
{
    QVariantList lista;
#ifdef Q_OS_WIN
    // Windows picks the GPU per program (Settings > Display > Graphics); the launcher writes that preference.
    lista.append(QVariantMap{{QStringLiteral("id"), QStringLiteral("ahorro")}, {QStringLiteral("tipo"), QStringLiteral("integrada")},
                             {QStringLiteral("nombre"), QString()}, {QStringLiteral("fabricante"), QString()}});
    lista.append(QVariantMap{{QStringLiteral("id"), QStringLiteral("rendimiento")}, {QStringLiteral("tipo"), QStringLiteral("dedicada")},
                             {QStringLiteral("nombre"), QString()}, {QStringLiteral("fabricante"), QString()}});
#else
    const QDir dispositivos(QStringLiteral("/sys/bus/pci/devices"));
    for (const QString &ranura : dispositivos.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name))
    {
        const QString base = dispositivos.absoluteFilePath(ranura);
        const QString clase = leerTexto(base + QStringLiteral("/class"));
        // 0x0300xx = VGA, 0x0302xx = 3D (NVIDIA GPUs of hybrid laptops), 0x0380xx = other display.
        if (!clase.startsWith(QStringLiteral("0x0300")) && !clase.startsWith(QStringLiteral("0x0302")) &&
            !clase.startsWith(QStringLiteral("0x0380")))
            continue;
        const QString fabricante = leerTexto(base + QStringLiteral("/vendor")).mid(2);
        const QString dispositivo = leerTexto(base + QStringLiteral("/device")).mid(2);
        const QString controlador = QFileInfo(base + QStringLiteral("/driver")).symLinkTarget().section(QLatin1Char('/'), -1);
        QString nombre = nombrePci(fabricante, dispositivo);
        if (nombre.isEmpty())
            nombre = fabricante + QLatin1Char(':') + dispositivo;
        lista.append(QVariantMap{
            {QStringLiteral("id"), ranura},
            {QStringLiteral("nombre"), nombre},
            {QStringLiteral("fabricante"), nombreFabricante(fabricante)},
            {QStringLiteral("controlador"), controlador},
            {QStringLiteral("predeterminada"), leerTexto(base + QStringLiteral("/boot_vga")) == QStringLiteral("1")},
        });
    }
    // Integrated: the one that boots the system (boot_vga) unless it is the only one; the rest are dedicated.
    for (QVariant &v : lista)
    {
        QVariantMap tarjeta = v.toMap();
        const bool predeterminada = tarjeta.value(QStringLiteral("predeterminada")).toBool();
        const bool nvidia = tarjeta.value(QStringLiteral("fabricante")).toString() == QStringLiteral("NVIDIA");
        tarjeta.insert(QStringLiteral("tipo"), lista.size() == 1 ? QString() : (predeterminada && !nvidia ? QStringLiteral("integrada") : QStringLiteral("dedicada")));
        v = tarjeta;
    }
#endif
    return lista;
}

QVariantMap Lanzador::pantalla() const
{
    QScreen *pantalla = QGuiApplication::primaryScreen();
    if (!pantalla)
        return {{QStringLiteral("ancho"), 1920}, {QStringLiteral("alto"), 1080}, {QStringLiteral("hz"), 60}};
    const QSize tam = pantalla->size() * pantalla->devicePixelRatio();
    return {{QStringLiteral("ancho"), tam.width()}, {QStringLiteral("alto"), tam.height()},
            {QStringLiteral("hz"), static_cast<int>(std::lround(pantalla->refreshRate()))}};
}

QVariantMap Lanzador::rutasDetectadas() const
{
    const QString desde = QCoreApplication::applicationDirPath();
    // Fallback when the installer has not prepared anything: a game/ folder next to the launcher.
    QString elf = buscarHaciaArriba(desde, QStringLiteral("game/SCUS_973.99"));
    if (elf.isEmpty())
        elf = buscarHaciaArriba(desde, QStringLiteral("SCUS_973.99"));
    QString ejecutable = buscarHaciaArriba(desde, kNombreEjecutable);
    if (ejecutable.isEmpty())
        ejecutable = buscarHaciaArriba(desde, QStringLiteral("PS2Recomp/build/ps2xRuntime/") + kNombreEjecutable);
    if (ejecutable.isEmpty()) // Visual Studio generators (one folder per configuration)
        ejecutable = buscarHaciaArriba(desde, QStringLiteral("PS2Recomp/build/ps2xRuntime/Release/") + kNombreEjecutable);
    if (ejecutable.isEmpty())
        ejecutable = buscarHaciaArriba(desde, QStringLiteral("build/ps2xRuntime/") + kNombreEjecutable);
    const QString iso = elf.isEmpty() ? QString() : primeraIso(QFileInfo(elf).absolutePath());
    return {{QStringLiteral("elf"), elf}, {QStringLiteral("iso"), iso}, {QStringLiteral("ejecutable"), ejecutable}};
}

QVariantMap Lanzador::comprobarJuego(const QString &elf) const
{
    QVariantMap resultado{{QStringLiteral("existe"), false}, {QStringLiteral("valido"), false}, {QStringLiteral("crc"), QString()}};
    QFile archivo(elf);
    if (elf.isEmpty() || !archivo.open(QIODevice::ReadOnly))
        return resultado;
    resultado.insert(QStringLiteral("existe"), true);
    const QByteArray datos = archivo.readAll();
    quint32 crc = 0u;
    const qsizetype palabras = datos.size() / 4;
    const auto *bytes = reinterpret_cast<const uchar *>(datos.constData());
    for (qsizetype i = 0; i < palabras; ++i)
        crc ^= static_cast<quint32>(bytes[i * 4]) | static_cast<quint32>(bytes[i * 4 + 1]) << 8u |
               static_cast<quint32>(bytes[i * 4 + 2]) << 16u | static_cast<quint32>(bytes[i * 4 + 3]) << 24u;
    resultado.insert(QStringLiteral("crc"), QStringLiteral("%1").arg(crc, 8, 16, QLatin1Char('0')).toUpper());
    resultado.insert(QStringLiteral("valido"), datos.startsWith("\x7F" "ELF") && crc == kCrcGodOfWar);
    return resultado;
}

QVariantMap Lanzador::comprobarDatos(const QString &elf, const QString &iso) const
{
    const QString carpeta = QFileInfo(elf).absolutePath();
    QString imagen = iso;
    if (!imagen.isEmpty() && !QFileInfo(imagen).isFile())
        imagen.clear();
    if (imagen.isEmpty() && iso.isEmpty() && !elf.isEmpty())
    {
        // Same order as configureGowCdImage: "../God of War.iso" next to the ELF, or the first .iso in its folder.
        const QString hermana = QDir(carpeta).absoluteFilePath(QStringLiteral("../God of War.iso"));
        imagen = QFileInfo(hermana).isFile() ? QDir::cleanPath(hermana) : primeraIso(carpeta);
    }
    const QDir dir(carpeta);
    const bool extraidos = !elf.isEmpty() && dir.exists(QStringLiteral("GODOFWAR.TOC")) && dir.exists(QStringLiteral("PART1.PAK"));
    return {{QStringLiteral("ok"), !imagen.isEmpty() || extraidos}, {QStringLiteral("iso"), imagen},
            {QStringLiteral("extraidos"), extraidos}, {QStringLiteral("isoElegidaFalta"), !iso.isEmpty() && imagen.isEmpty()}};
}

QVariantMap Lanzador::comprobarEjecutable(const QString &ruta) const
{
    const QFileInfo info(ruta);
    return {{QStringLiteral("existe"), !ruta.isEmpty() && info.isFile()}, {QStringLiteral("ejecutable"), !ruta.isEmpty() && info.isFile() && info.isExecutable()}};
}

QString Lanzador::carpetaMemoria(const QString &elf) const
{
    return elf.isEmpty() ? QString() : QDir(QFileInfo(elf).absolutePath()).absoluteFilePath(QStringLiteral("mc0"));
}

QString Lanzador::rutaDesdeUrl(const QUrl &url) const
{
    return url.isLocalFile() ? QDir::cleanPath(url.toLocalFile()) : url.toString();
}

QUrl Lanzador::urlDesdeRuta(const QString &ruta) const
{
    return QUrl::fromLocalFile(ruta);
}

void Lanzador::aplicarTarjeta(QProcessEnvironment &entorno, const QString &id, const QString &ejecutable) const
{
#ifdef Q_OS_WIN
    // Per-program preference of Windows 10/11 (the one Settings > Graphics writes).
    QSettings preferencias(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\DirectX\\UserGpuPreferences"), QSettings::NativeFormat);
    const QString clave = QDir::toNativeSeparators(ejecutable);
    if (id == QStringLiteral("ahorro"))
        preferencias.setValue(clave, QStringLiteral("GpuPreference=1;"));
    else if (id == QStringLiteral("rendimiento"))
        preferencias.setValue(clave, QStringLiteral("GpuPreference=2;"));
    else
        preferencias.remove(clave);
    Q_UNUSED(entorno);
#else
    Q_UNUSED(ejecutable);
    if (id.isEmpty() || id == QStringLiteral("auto"))
        return;
    for (const QVariant &v : tarjetasGraficas())
    {
        const QVariantMap tarjeta = v.toMap();
        if (tarjeta.value(QStringLiteral("id")).toString() != id)
            continue;
        if (tarjeta.value(QStringLiteral("controlador")).toString() == QStringLiteral("nvidia"))
        {
            // NVIDIA proprietary driver on a hybrid laptop: PRIME render offload.
            entorno.insert(QStringLiteral("__NV_PRIME_RENDER_OFFLOAD"), QStringLiteral("1"));
            entorno.insert(QStringLiteral("__GLX_VENDOR_LIBRARY_NAME"), QStringLiteral("nvidia"));
            entorno.insert(QStringLiteral("__VK_LAYER_NV_optimus"), QStringLiteral("NVIDIA_only"));
        }
        else if (!tarjeta.value(QStringLiteral("predeterminada")).toBool())
        {
            // Mesa: DRI_PRIME=pci-0000_03_00_0 selects that card.
            QString etiqueta = id;
            etiqueta.replace(QLatin1Char(':'), QLatin1Char('_')).replace(QLatin1Char('.'), QLatin1Char('_'));
            entorno.insert(QStringLiteral("DRI_PRIME"), QStringLiteral("pci-") + etiqueta);
        }
        return;
    }
#endif
}

bool Lanzador::iniciar(const QVariantMap &a)
{
    if (jugando())
        return false;
    const QString ejecutable = a.value(QStringLiteral("ejecutable")).toString();
    QString elf = a.value(QStringLiteral("elf")).toString();
    if (!comprobarEjecutable(ejecutable).value(QStringLiteral("ejecutable")).toBool())
    {
        emit error(QStringLiteral("errorEjecutable"), ejecutable);
        return false;
    }
    if (!QFileInfo(elf).isFile())
    {
        emit error(QStringLiteral("errorElf"), elf);
        return false;
    }

    QProcessEnvironment entorno = QProcessEnvironment::systemEnvironment();
    for (const auto &[nombre, valor] : kEntornoBase)
        if (!entorno.contains(QLatin1String(nombre)))
            entorno.insert(QLatin1String(nombre), QLatin1String(valor));
    const auto bandera = [&](const char *nombre, bool activa, const char *valorApagado = nullptr)
    {
        if (activa)
            entorno.insert(QLatin1String(nombre), QStringLiteral("1"));
        else if (valorApagado)
            entorno.insert(QLatin1String(nombre), QLatin1String(valorApagado));
        else
            entorno.remove(QLatin1String(nombre));
    };
    // Game options.
    bandera("GOW_SKIP_FMV", a.value(QStringLiteral("saltarVideos")).toBool());
    bandera("GOW_FAST_BOOT", a.value(QStringLiteral("arranqueRapido")).toBool());
    bandera("TOBIICHI_DMC5_CONTROLS", a.value(QStringLiteral("controlesDmc5")).toBool(), "0");
    bandera("TOBIICHI_ESC_SALIR", a.value(QStringLiteral("escSalir")).toBool(), "0");
    bandera("GOW_CANCELAR", a.value(QStringLiteral("cancelarAnimaciones"), true).toBool(), "0");
    // gow-native-pc: accessibility — holding a button instead of mashing it in the minigames (ps2_pad.cpp with
    // runtime/gow_qte_hold.h). The buttons are action names of TOBIICHI_TECLAS; without the variable nothing changes.
    if (a.value(QStringLiteral("qteHold")).toBool())
    {
        // Only the face buttons: L1, R1, L2 and R2 are held in normal play (block, magic) and repeating them would
        // drop a block. GOW_QTE_HOLD itself takes any action name, for anyone who wants one by hand.
        const QString cuales = a.value(QStringLiteral("qteHoldButtons"), QStringLiteral("circle")).toString();
        const QString botones = cuales == QStringLiteral("face") ? QStringLiteral("circle,cross,square,triangle")
                                                                : QStringLiteral("circle");
        entorno.insert(QStringLiteral("GOW_QTE_HOLD"), botones);
        entorno.insert(QStringLiteral("GOW_QTE_HOLD_HZ"),
                       QString::number(std::clamp(a.value(QStringLiteral("qteHoldRate"), 10).toInt(), 2, 20)));
    }
    else
    {
        entorno.remove(QStringLiteral("GOW_QTE_HOLD"));
        entorno.remove(QStringLiteral("GOW_QTE_HOLD_HZ"));
    }
    // Configurable keyboard and mouse (ps2_pad.cpp): "action=code,code;...".
    const QString teclas = a.value(QStringLiteral("teclas")).toString();
    if (teclas.isEmpty())
        entorno.remove(QStringLiteral("TOBIICHI_TECLAS"));
    else
        entorno.insert(QStringLiteral("TOBIICHI_TECLAS"), teclas);
    // Controller layout changed button by button (ps2_pad.cpp): "action=button,button;..."; empty = the fixed layout.
    const QString mandoMapa = a.value(QStringLiteral("mando")).toString();
    if (mandoMapa.isEmpty())
        entorno.remove(QStringLiteral("TOBIICHI_MANDO"));
    else
        entorno.insert(QStringLiteral("TOBIICHI_MANDO"), mandoMapa);
    // Cheat menu (F2 in game): the cheats active at start and the menu language.
    const QString trucos = a.value(QStringLiteral("trucos")).toString();
    if (trucos.isEmpty())
        entorno.remove(QStringLiteral("TOBIICHI_TRUCOS"));
    else
        entorno.insert(QStringLiteral("TOBIICHI_TRUCOS"), trucos);
    entorno.insert(QStringLiteral("TOBIICHI_IDIOMA"), a.value(QStringLiteral("idioma"), QStringLiteral("en")).toString());
    // gow-native-pc: continuous optimisation. The runtime writes each VU1 micro-memory it has not seen before (cheap: only
    // new code); the Install tab's "Speed up visited areas" compiles them into the game as native code.
    const QString capturaVu1 = a.value(QStringLiteral("capturaVu1")).toString();
    if (!capturaVu1.isEmpty() && QDir().mkpath(capturaVu1))
        entorno.insert(QStringLiteral("GOW_VU1_CAPTURA"), capturaVu1);
    else
        entorno.remove(QStringLiteral("GOW_VU1_CAPTURA"));
    // Window.
    const bool completa = a.value(QStringLiteral("modoPantalla")).toString() == QStringLiteral("completa");
    entorno.insert(QStringLiteral("TOBIICHI_PANTALLA"), completa ? QStringLiteral("completa") : QStringLiteral("ventana"));
    entorno.insert(QStringLiteral("TOBIICHI_ANCHO"), QString::number(a.value(QStringLiteral("ancho")).toInt()));
    entorno.insert(QStringLiteral("TOBIICHI_ALTO"), QString::number(a.value(QStringLiteral("alto")).toInt()));
    entorno.insert(QStringLiteral("TOBIICHI_TITULO"), QStringLiteral("God of War"));
    entorno.insert(QStringLiteral("TOBIICHI_PANEL"), QStringLiteral("0")); // the debug panel opens with F1
    if (QFileInfo::exists(rutaIcono()))
        entorno.insert(QStringLiteral("TOBIICHI_ICONO"), rutaIcono());
    // Image: aspect ratio (widescreen changes the game camera) and scaling.
    const QString aspecto = a.value(QStringLiteral("aspecto")).toString();
    if (aspecto.isEmpty() || aspecto == QStringLiteral("4:3"))
        entorno.remove(QStringLiteral("TOBIICHI_PANORAMICO"));
    else
        entorno.insert(QStringLiteral("TOBIICHI_PANORAMICO"), aspecto);
    entorno.insert(QStringLiteral("TOBIICHI_ASPECTO"), a.value(QStringLiteral("estirar")).toBool() ? QStringLiteral("estirar") : QStringLiteral("auto"));
    entorno.insert(QStringLiteral("TOBIICHI_FILTRO"), a.value(QStringLiteral("filtro"), QStringLiteral("fsr")).toString());
    // Sharpness 0..1 in the interface -> RCAS steps (2 = soft, 0 = maximum).
    const double nitidez = std::clamp(a.value(QStringLiteral("nitidez"), 0.8).toDouble(), 0.0, 1.0);
    entorno.insert(QStringLiteral("TOBIICHI_NITIDEZ"), QString::number(2.0 * (1.0 - nitidez), 'f', 2));
    bandera("TOBIICHI_FXAA", a.value(QStringLiteral("fxaa")).toBool());
    // Anisotropic filtering of the game's textures (gs_hw_backend.cpp, from the God of War II port): 1 = off.
    const int aniso = std::clamp(a.value(QStringLiteral("anisotropico"), 1).toInt(), 1, 16);
    if (aniso > 1)
        entorno.insert(QStringLiteral("GOW_ANISO"), QString::number(aniso));
    else
        entorno.remove(QStringLiteral("GOW_ANISO"));
    // Runtime upscaling (gs_host_present.cpp). "fsr" = bicubic with sharpening (GOW_SHARPEN, 0 to 0.5 with
    // the sharpness; 0 = none); "bilineal" and "pixel" = bilinear stretch without sharpening (soft image).
    {
        const QString filtro = a.value(QStringLiteral("filtro"), QStringLiteral("fsr")).toString();
        if (filtro == QStringLiteral("fsr"))
        {
            entorno.insert(QStringLiteral("GOW_SCALER"), QStringLiteral("sharp"));
            entorno.insert(QStringLiteral("GOW_SHARPEN"), QString::number(0.5 * nitidez, 'f', 2));
        }
        else
        {
            entorno.insert(QStringLiteral("GOW_SCALER"), QStringLiteral("bilinear"));
            entorno.insert(QStringLiteral("GOW_SHARPEN"), QStringLiteral("0"));
        }
    }
    // GS internal resolution (1..8; the interface resolves "automatic" from the display) and sharp image.
    entorno.insert(QStringLiteral("PS2X_GS_ESCALA"), QString::number(std::clamp(a.value(QStringLiteral("escala"), 1).toInt(), 1, 8)));
    // The render-target renderer reads the scale from PS2X_GS_HW_SCALE.
    entorno.insert(QStringLiteral("PS2X_GS_HW_SCALE"), QString::number(std::clamp(a.value(QStringLiteral("escala"), 2).toInt(), 1, 8)));
    bandera("PS2X_GS_NITIDO", a.value(QStringLiteral("imagenNitida"), true).toBool(), "0");
    bandera("PS2X_GS_ESCALA_DINAMICA", a.value(QStringLiteral("escalaDinamica"), true).toBool(), "0");
    bandera("PS2X_GS_HW", a.value(QStringLiteral("dibujoHardware"), true).toBool(), "0");
    // Window pacing.
    entorno.insert(QStringLiteral("TOBIICHI_VENTANA_FPS"), QString::number(a.value(QStringLiteral("fpsLimite"), 120).toInt()));
    bandera("TOBIICHI_VSYNC", a.value(QStringLiteral("vsync")).toBool());
    bandera("TOBIICHI_FPS_GOSTER", a.value(QStringLiteral("mostrarFps")).toBool());
    // Files.
    // The runtime reads an extracted disc folder (.disc_layout next to the ELF); without one it reads an ISO:
    // the chosen one, or the first one next to the ELF.
    QString iso = a.value(QStringLiteral("iso")).toString();
    const QString carpetaElf = QFileInfo(elf).absolutePath();
    if (iso.isEmpty() && !QFileInfo::exists(QDir(carpetaElf).absoluteFilePath(QStringLiteral(".disc_layout"))))
        iso = primeraIso(carpetaElf); // no extracted disc (.disc_layout): the ISO in the ELF's folder
    if (iso.isEmpty())
        entorno.remove(QStringLiteral("GOW_ISO"));
    else
        entorno.insert(QStringLiteral("GOW_ISO"), iso);
    const QString cache = QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + QStringLiteral("/sombreadores");
    QDir().mkpath(cache);
    if (!entorno.contains(QStringLiteral("PS2X_GS_SHADER_CACHE_DIR")))
        entorno.insert(QStringLiteral("PS2X_GS_SHADER_CACHE_DIR"), cache);
    aplicarTarjeta(entorno, a.value(QStringLiteral("gpu")).toString(), ejecutable);

    // Log: the previous game's log is kept as anterior.log.
    const QString registro = rutaRegistro();
    const QString anterior = carpetaDatos() + QStringLiteral("/registros/anterior.log");
    QFile::remove(anterior);
    QFile::rename(registro, anterior);

    delete m_proceso;
    m_proceso = new QProcess(this);
    m_proceso->setProgram(ejecutable);
    m_proceso->setArguments({elf});
    m_proceso->setProcessEnvironment(entorno);
    m_proceso->setWorkingDirectory(carpetaDatos());
    m_proceso->setProcessChannelMode(QProcess::MergedChannels);
    m_proceso->setStandardOutputFile(registro);
    connect(m_proceso, &QProcess::finished, this, &Lanzador::terminado);
    connect(m_proceso, &QProcess::errorOccurred, this, [this](QProcess::ProcessError fallo)
    {
        if (fallo == QProcess::FailedToStart)
        {
            emit error(QStringLiteral("errorArranque"), m_proceso->errorString());
            emit jugandoCambiado();
        }
    });
    m_reloj.start();
    m_proceso->start();
    emit jugandoCambiado();
    return true;
}

void Lanzador::terminado(int codigo, QProcess::ExitStatus estado)
{
    const int segundos = static_cast<int>(m_reloj.elapsed() / 1000);
    const bool fallo = estado == QProcess::CrashExit || codigo != 0;
    QString resumen;
    if (fallo)
    {
        // Last log lines with errors, for the notice.
        QFile archivo(rutaRegistro());
        if (archivo.open(QIODevice::ReadOnly | QIODevice::Text))
        {
            const QStringList lineas = QString::fromUtf8(archivo.readAll()).split(QLatin1Char('\n'), Qt::SkipEmptyParts);
            QStringList utiles;
            for (qsizetype i = lineas.size() - 1; i >= 0 && utiles.size() < 6; --i)
            {
                const QString &linea = lineas[i];
                if (linea.contains(QStringLiteral("error"), Qt::CaseInsensitive) || linea.contains(QStringLiteral("fatal"), Qt::CaseInsensitive) ||
                    linea.contains(QStringLiteral("failed"), Qt::CaseInsensitive))
                    utiles.prepend(linea.left(200));
            }
            if (utiles.isEmpty())
                for (qsizetype i = std::max<qsizetype>(0, lineas.size() - 4); i < lineas.size(); ++i)
                    utiles.append(lineas[i].left(200));
            resumen = utiles.join(QLatin1Char('\n'));
        }
    }
    emit juegoTerminado(codigo, fallo, segundos, resumen);
    emit jugandoCambiado();
}

void Lanzador::detener()
{
    if (!jugando())
        return;
    m_proceso->terminate();
    QProcess *proceso = m_proceso;
    QTimer::singleShot(3000, proceso, [proceso]
    {
        if (proceso->state() != QProcess::NotRunning)
            proceso->kill();
    });
}

void Lanzador::abrirCarpeta(const QString &ruta) const
{
    QString carpeta = ruta;
    if (QFileInfo(ruta).isFile())
        carpeta = QFileInfo(ruta).absolutePath();
    QDir().mkpath(carpeta);
    QDesktopServices::openUrl(QUrl::fromLocalFile(carpeta));
}

void Lanzador::abrirRegistro() const
{
    const QString registro = rutaRegistro();
    QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo::exists(registro) ? registro : QFileInfo(registro).absolutePath()));
}

bool Lanzador::crearAccesoDirecto(bool escritorio) const
{
#ifdef Q_OS_WIN
    // Windows shortcut (.lnk) in the Start menu or on the desktop.
    const QString destino = QStandardPaths::writableLocation(escritorio ? QStandardPaths::DesktopLocation : QStandardPaths::ApplicationsLocation);
    return QFile::link(QCoreApplication::applicationFilePath(), destino + QStringLiteral("/God of War.lnk"));
#else
    const QString ejecutable = QCoreApplication::applicationFilePath();
    QString contenido;
    QTextStream salida(&contenido);
    salida << "[Desktop Entry]\n"
           << "Type=Application\n"
           << "Name=God Of War: Tobiichi Launcher\n"
           << "GenericName=Game Launcher\n"
           << "Comment=God of War (PS2) PC port\n"
           << "Exec=\"" << ejecutable << "\"\n"
           << "Icon=" << rutaIcono() << "\n"
           << "Terminal=false\n"
           << "Categories=Game;\n"
           << "StartupWMClass=gow-launcher\n"
           << "Actions=jugar;\n"
           << "\n[Desktop Action jugar]\n"
           << "Name=Play now\n"
           << "Name[tr]=Hemen oyna\n"
           << "Name[es]=Jugar ya\n"
           << "Exec=\"" << ejecutable << "\" --jugar\n";
    const auto escribir = [&](const QString &ruta, bool marcarEjecutable)
    {
        QDir().mkpath(QFileInfo(ruta).absolutePath());
        QFile archivo(ruta);
        if (!archivo.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text))
            return false;
        archivo.write(contenido.toUtf8());
        archivo.close();
        if (marcarEjecutable)
            archivo.setPermissions(archivo.permissions() | QFileDevice::ExeOwner | QFileDevice::ExeUser);
        return true;
    };
    bool ok = escribir(QStandardPaths::writableLocation(QStandardPaths::ApplicationsLocation) + QStringLiteral("/gow-native-pc.desktop"), false);
    if (escritorio)
        ok = escribir(QStandardPaths::writableLocation(QStandardPaths::DesktopLocation) + QStringLiteral("/gow-native-pc.desktop"), true) && ok;
    return ok;
#endif
}

QString Lanzador::guardarPortada(const QString &origen) const
{
    QImageReader lector(origen);
    if (!lector.canRead())
        return {};
    borrarPortada();
    // A new name every time, so QML does not reuse the previous image from its cache.
    const QString sufijo = QFileInfo(origen).suffix().toLower();
    const QString destino = carpetaDatos() + QStringLiteral("/portada-") +
                            QString::number(QDateTime::currentMSecsSinceEpoch()) + QLatin1Char('.') + sufijo;
    return QFile::copy(origen, destino) ? destino : QString();
}

void Lanzador::borrarPortada() const
{
    const QDir dir(carpetaDatos());
    for (const QString &nombre : dir.entryList({QStringLiteral("portada-*")}, QDir::Files))
        QFile::remove(dir.absoluteFilePath(nombre));
}

bool Lanzador::esRecorte(const QString &ruta) const
{
    const QImage imagen(ruta);
    if (imagen.isNull() || !imagen.hasAlphaChannel())
        return false;
    // Top, left and right edges (the bottom one usually cuts the figure).
    int transparentes = 0, total = 0;
    const auto mirar = [&](int x, int y)
    {
        ++total;
        if (qAlpha(imagen.pixel(x, y)) < 16)
            ++transparentes;
    };
    for (int x = 0; x < imagen.width(); x += 2)
        mirar(x, 0);
    for (int y = 0; y < imagen.height(); y += 2)
    {
        mirar(0, y);
        mirar(imagen.width() - 1, y);
    }
    return total > 0 && transparentes * 10 >= total * 7;
}
