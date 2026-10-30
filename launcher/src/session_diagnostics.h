#pragma once

#include <QString>
#include <QStringList>
#include <QVariantMap>

namespace SessionDiagnostics {
// Local reports only: fixed file allowlist, no game files or inherited environment.
QString create(const QString &base, const QVariantMap &settings);
QString latest(const QString &base);
QString exportZip(const QString &session, QString *error);
bool mark(const QString &session, const QString &note);
int run(const QStringList &arguments);
}
