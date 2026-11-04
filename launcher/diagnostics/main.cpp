#include "diagnostic_kit.h"
#include <QGuiApplication>
#include <QLockFile>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QStandardPaths>
#include <QDir>
#include <QTimer>
#include <cstdio>

int main(int argc,char **argv) {
    QGuiApplication app(argc,argv);
    app.setOrganizationName("gow-native-pc-diagnostics");
    app.setApplicationName("DiagnosticKit");
    app.setApplicationVersion(TOBIICHI_VERSION);
    app.setApplicationDisplayName("God of War — Diagnóstico");
    const QString base=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    QDir().mkpath(base);
    QLockFile lock(base+"/launcher.lock");
    if(!lock.tryLock(0)) return 2;
    QQuickStyle::setStyle("Basic");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    DiagnosticKit kit;
    // Deployment validation; remembers a valid selection but never starts a game.
    if(app.arguments().contains("--check-game")) {
        const int i=app.arguments().indexOf("--check-game");
        const bool ok=i+1<argc && kit.selectGame(app.arguments()[i+1]);
        std::printf("%s\n",kit.statusKey().toUtf8().constData());
        return ok?0:1;
    }
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("diagnosticKit",&kit);
    engine.load(QUrl("qrc:/diagnostics/Main.qml"));
    if(engine.rootObjects().isEmpty()) return 1;
    const auto args=app.arguments();
    const int capture=args.indexOf("--capture-ui");
    if(capture>=0 && capture+1<args.size()) QTimer::singleShot(800,&app,[&] {
        auto *window=qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        if(!window || !window->grabWindow().save(args[capture+1])) app.exit(3);
    });
    const int smoke=args.indexOf("--game-smoke");
    if(smoke>=0) {
        if(smoke+1>=args.size() || !kit.selectGame(args[smoke+1]) || !kit.start(args.contains("--detailed"),false,1)) return 4;
        QTimer::singleShot(100000,&kit,&DiagnosticKit::stop);
        QTimer::singleShot(115000,&app,&QCoreApplication::quit);
    }
    if(app.arguments().contains("--ui-smoke")) QTimer::singleShot(2000,&app,&QCoreApplication::quit);
    return app.exec();
}
