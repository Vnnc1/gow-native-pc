// God of War Native PC launcher (gow-native-pc), based on the Tobiichi Launcher by YYOzcan (GPL-3.0).
// Entry point: title font, generated icon, the play backend ("lanzador", Tobiichi's) and the install backend
// ("installer", src/installer_backend.cpp) for QML.
#include "installer_backend.h"
#include "lanzador.h"
#include "mando.h"

#include <QDir>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QSettings>
#include <QIcon>
#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QTimer>

namespace
{
    // Icon: a white omega on a crimson rounded square with a darker diagonal blade, drawn with the title font so no
    // image file is needed.
    QImage dibujarIcono(const QString &familia, int lado)
    {
        QImage imagen(lado, lado, QImage::Format_ARGB32_Premultiplied);
        imagen.fill(Qt::transparent);
        QPainter p(&imagen);
        p.setRenderHint(QPainter::Antialiasing);
        const qreal s = lado / 256.0;
        const QRectF marco(8 * s, 8 * s, 240 * s, 240 * s);
        QLinearGradient fondo(0, 8 * s, 0, 248 * s);
        fondo.setColorAt(0.0, QColor(0xe0, 0x35, 0x2a));
        fondo.setColorAt(1.0, QColor(0x7a, 0x16, 0x10));
        QPainterPath cuadro;
        cuadro.addRoundedRect(marco, 52 * s, 52 * s);
        p.setPen(Qt::NoPen);
        p.fillPath(cuadro, fondo);
        QPainterPath hoja;
        hoja.moveTo(150 * s, 8 * s);
        hoja.lineTo(205 * s, 8 * s);
        hoja.lineTo(110 * s, 248 * s);
        hoja.lineTo(55 * s, 248 * s);
        hoja.closeSubpath();
        p.fillPath(cuadro.intersected(hoja), QColor(0, 0, 0, 55));

        QFont fuente(familia);
        fuente.setPixelSize(static_cast<int>(170 * s));
        fuente.setWeight(QFont::Black);
        QPainterPath omega;
        omega.addText(0, 0, fuente, QStringLiteral("Ω"));
        const QRectF caja = omega.boundingRect();
        omega.translate(128 * s - caja.center().x(), 130 * s - caja.center().y());
        p.fillPath(omega.translated(0, 5 * s), QColor(0, 0, 0, 90));
        p.fillPath(omega, Qt::white);
        return imagen;
    }
}

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    // own settings (not shared with an installed Tobiichi launcher)
    QGuiApplication::setOrganizationName(QStringLiteral("gow-native-pc"));
    QGuiApplication::setApplicationName(QStringLiteral("Launcher"));
    QGuiApplication::setApplicationDisplayName(QStringLiteral("God of War — Native PC"));
    QGuiApplication::setApplicationVersion(QStringLiteral(TOBIICHI_VERSION));
    QGuiApplication::setDesktopFileName(QStringLiteral("gow-native-pc"));
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    // Title font: a heavy sans (Segoe UI Black on Windows), the system font elsewhere.
    QString familiaTitulo = QGuiApplication::font().family();
    if (QFontDatabase::hasFamily(QStringLiteral("Segoe UI")))
        familiaTitulo = QStringLiteral("Segoe UI");

    Lanzador lanzador;
    InstallerBackend installer;
    Mando mando;
    const QImage icono = dibujarIcono(familiaTitulo, 256);
    QDir().mkpath(lanzador.carpetaDatos());
    icono.save(lanzador.rutaIcono());
    QGuiApplication::setWindowIcon(QIcon(QPixmap::fromImage(icono)));

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("lanzador"), &lanzador);
    engine.rootContext()->setContextProperty(QStringLiteral("installer"), &installer);
    engine.rootContext()->setContextProperty(QStringLiteral("mando"), &mando);
    engine.rootContext()->setContextProperty(QStringLiteral("fuenteTitulo"), familiaTitulo);
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app, [] { QCoreApplication::exit(1); },
                     Qt::QueuedConnection);
    // For documentation and tests: TOBIICHI_CAPTURA=<png> saves the window and quits;
    // TOBIICHI_CAPTURA_PESTANA picks the tab and TOBIICHI_CAPTURA_ALTO the window height; TOBIICHI_CAPTURA_IDIOMA shows
    // another interface language for the capture only (the saved setting is not changed).
    const QByteArray captura = qgetenv("TOBIICHI_CAPTURA");
    engine.rootContext()->setContextProperty(QStringLiteral("pestanaInicial"), qEnvironmentVariableIntValue("TOBIICHI_CAPTURA_PESTANA"));
    engine.rootContext()->setContextProperty(QStringLiteral("idiomaCaptura"),
                                             captura.isEmpty() ? QString() : qEnvironmentVariable("TOBIICHI_CAPTURA_IDIOMA"));
    engine.loadFromModule(QStringLiteral("Tobiichi"), QStringLiteral("Main"));
    if (!captura.isEmpty() && qEnvironmentVariableIntValue("TOBIICHI_CAPTURA_ALTO") > 0 && !engine.rootObjects().isEmpty())
        engine.rootObjects().first()->setProperty("height", qEnvironmentVariableIntValue("TOBIICHI_CAPTURA_ALTO"));
    if (!captura.isEmpty())
        QTimer::singleShot(3000, &app, [&engine, captura]
        {
            if (auto *ventana = qobject_cast<QQuickWindow *>(engine.rootObjects().value(0)))
                ventana->grabWindow().save(QString::fromLocal8Bit(captura));
            QCoreApplication::quit();
        });
    return app.exec();
}
