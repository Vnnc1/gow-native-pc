// Machine-local regional builds are separate from the USA generation manifest.
#pragma once
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMutex>
#include <QSet>
#include <QVariantList>

namespace RegionalInstallations {
inline QString repositoryRoot()
{
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 6; ++i) {
        if (dir.exists(QStringLiteral("games/gow1/game.toml"))) return dir.absolutePath();
        if (!dir.cdUp()) break;
    }
    return {};
}

inline bool samePath(const QString &a, const QString &b)
{
    if (a.isEmpty() || b.isEmpty()) return false;
#ifdef Q_OS_WIN
    constexpr auto sensitivity = Qt::CaseInsensitive;
#else
    constexpr auto sensitivity = Qt::CaseSensitive;
#endif
    return QDir::cleanPath(QDir::fromNativeSeparators(a)).compare(
        QDir::cleanPath(QDir::fromNativeSeparators(b)), sensitivity) == 0;
}

inline QString sha256(const QString &path)
{
    // Hash binaries once per observed version, not every time the window regains focus.
    struct Cached { qint64 size; QDateTime modified; QDateTime changed; QString hash; };
    static QHash<QString, Cached> cache;
    const QFileInfo info(path);
    if (!info.isFile()) return {};
    auto found = cache.constFind(path);
    if (found != cache.cend() && found->size == info.size() && found->modified == info.lastModified()
        && found->changed == info.metadataChangeTime()) return found->hash;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (!hash.addData(&file)) return {};
    const QString result = QString::fromLatin1(hash.result().toHex());
    cache.insert(path, {info.size(), info.lastModified(), info.metadataChangeTime(), result});
    return result;
}

inline QString regionName(const QJsonObject &row)
{
    QString name = row.value("label").toString().trimmed();
    if (name.isEmpty()) name = row.value("region").toString().trimmed();
    if (name.isEmpty()) name = QStringLiteral("unnamed region");
    name.replace('\r', ' ').replace('\n', ' ');
    return name;
}

// A regional build that fails validation is dropped from the selector, which used to look like the launcher had lost
// the game. Say why, and name the region and the fix, without printing paths, hashes or other machine details. The
// message goes to stderr and to data/<game>/logs/launcher.log (the launcher is a windowed executable, so stderr alone
// is often invisible). Repeats of the same message are reported once per process to avoid spamming every UI refresh.
inline void reportExcluded(const QString &root, const QString &game, const QString &message)
{
    static QMutex mutex;
    static QSet<QString> reported;
    {
        QMutexLocker lock(&mutex);
        if (reported.contains(message)) return;
        reported.insert(message);
    }
    qWarning().noquote() << "regional builds:" << message;
    QDir().mkpath(root + "/data/" + game + "/logs");
    QFile log(root + "/data/" + game + "/logs/launcher.log");
    if (log.open(QIODevice::WriteOnly | QIODevice::Append))
        log.write(QDateTime::currentDateTime().toString(Qt::ISODate).toUtf8() + "  " + message.toUtf8() + '\n');
}

inline QVariantList read(const QString &root, const QString &game = QStringLiteral("gow1"))
{
    QVariantList out;
    QFile file(root + "/data/" + game + "/regional-builds.json");
    if (!file.open(QIODevice::ReadOnly)) return out;
    const auto manifest = QJsonDocument::fromJson(file.readAll()).object();
    if (manifest.value("schema").toInt() != 1 || !samePath(manifest.value("owner").toString(), root)
        || manifest.value("profile_sha256").toString() != sha256(root + "/games/" + game + "/game.toml"))
    {
        reportExcluded(root, game, QStringLiteral("Regional builds were ignored: the registration list does not belong "
            "to this checkout, or games/%1/game.toml changed. Re-register the regional build with "
            "tools/pipeline/register_region.py.").arg(game));
        return out;
    }
    QSet<QString> regions;
    for (const auto &value : manifest.value("builds").toArray()) {
        const auto row = value.toObject();
        const auto region = row.value("region").toString();
        const auto runner = row.value("runner").toString();
        const auto elf = row.value("elf").toString();
        const auto data = row.value("dataDir").toString();
        bool frameOk = false;
        const auto frame = row.value("framePc").toString().toUInt(&frameOk, 0);
        const auto exclude = [&](const QString &reason)
        {
            reportExcluded(root, game, QStringLiteral("Regional build \"%1\" (%2) was excluded: %3. Re-register it with "
                "tools/pipeline/register_region.py.").arg(regionName(row), region.isEmpty()
                    ? QStringLiteral("no region id") : region, reason));
        };
        if (region.isEmpty()) { exclude(QStringLiteral("the entry has no region id")); continue; }
        if (regions.contains(region)) { exclude(QStringLiteral("duplicate registration for this region")); continue; }
        if (!QDir::isAbsolutePath(runner) || !QDir::isAbsolutePath(elf) || !QDir::isAbsolutePath(data)
            || !frameOk || frame < 0x100000 || frame >= 0x2000000 || frame % 4
            || row.value("runner_sha256").toString().size() != 64
            || row.value("elf_sha256").toString().size() != 64)
        {
            exclude(QStringLiteral("the registration is incomplete or has an invalid frame address"));
            continue;
        }
        if (sha256(runner) != row.value("runner_sha256").toString()
            || sha256(elf) != row.value("elf_sha256").toString())
        {
            exclude(QStringLiteral("the runner or disc no longer matches its registration (build fingerprint mismatch)"));
            continue;
        }
        QFile cmake(QFileInfo(runner).absolutePath() + "/../CMakeCache.txt");
        if (!cmake.open(QIODevice::ReadOnly))
        {
            exclude(QStringLiteral("the build directory is missing its CMake cache"));
            continue;
        }
        QString source;
        while (!cmake.atEnd()) {
            const auto line = cmake.readLine().trimmed();
            const QByteArray prefix("CMAKE_HOME_DIRECTORY:INTERNAL=");
            if (line.startsWith(prefix)) source = QString::fromUtf8(line.mid(prefix.size()));
        }
        if (!samePath(source, row.value("source").toString()))
        {
            exclude(QStringLiteral("the build directory does not belong to this checkout"));
            continue;
        }
        if (!QFileInfo::exists(QFileInfo(elf).absolutePath() + "/.disc_layout"))
        {
            exclude(QStringLiteral("the regional disc is not prepared (missing .disc_layout)"));
            continue;
        }
        auto entry = row.toVariantMap();
        entry.insert("language", "region:" + region);
        entry.insert("regional", true);
        entry.insert("card", data + "/Mcd001.ps2");
        entry.insert("saves", data + "/saves");
        out.append(entry);
        regions.insert(region);
    }
    return out;
}

inline QVariantMap forElf(const QString &elf)
{
    for (const auto &entry : read(repositoryRoot())) {
        const auto row = entry.toMap();
        if (samePath(row.value("elf").toString(), elf)) return row;
    }
    return {};
}
}
