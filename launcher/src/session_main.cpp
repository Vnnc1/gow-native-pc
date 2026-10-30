#include "session_diagnostics.h"
#include <QCoreApplication>

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QCoreApplication::setApplicationVersion(QStringLiteral(TOBIICHI_VERSION));
    return SessionDiagnostics::run(app.arguments().mid(1));
}
