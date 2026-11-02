#include "installer_backend.h"
#include "regional_installations.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QStandardPaths>
#include <QThread>
#include <QUrl>

namespace
{
    // The repository: the folder above the launcher that holds games/<id>/game.toml (a release ships the launcher in
    // <repo>/launcher/bin; a development build sits in <repo>/launcher/build).
    QString findRoot()
    {
        QDir dir(QCoreApplication::applicationDirPath());
        for (int i = 0; i < 6; ++i)
        {
            if (QFileInfo::exists(dir.filePath(QStringLiteral("games/gow1/game.toml"))))
                return dir.absolutePath();
            if (!dir.cdUp())
                break;
        }
        return QCoreApplication::applicationDirPath();
    }

    bool onPath(const QString &program)
    {
        return !QStandardPaths::findExecutable(program).isEmpty();
    }

    // A Python 3 that really runs: the Microsoft Store's python.exe stub in WindowsApps is on PATH without being a Python
    // (it only opens the Store), so being on PATH is not enough. Require 3.12 for the shared recompiler helpers.
    QString workingPython()
    {
        static const QString found = []
        {
            for (const QString &candidate : {QStringLiteral("python3"), QStringLiteral("python"), QStringLiteral("py")})
            {
                if (!onPath(candidate))
                    continue;
                QProcess probe;
                probe.start(candidate, {QStringLiteral("-c"), QStringLiteral("import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)")});
                if (probe.waitForFinished(8000) && probe.exitStatus() == QProcess::NormalExit && probe.exitCode() == 0)
                    return candidate;
                probe.kill();
            }
            return QString();
        }();
        return found;
    }
}

// Read legacy installations for playing until the next successful clang build.
static QString installedToolchain(const QString &root)
{
    QFile file(root + QStringLiteral("/data/toolchain.txt"));
    if (file.open(QIODevice::ReadOnly | QIODevice::Text) && QString::fromUtf8(file.readAll()).trimmed() == QStringLiteral("msvc"))
        return QStringLiteral("msvc");
    return QStringLiteral("clang");
}

InstallerBackend::InstallerBackend(QObject *parent) : QObject(parent), m_root(findRoot()) {}

// the portable Python of the build tools (data/_tools, build.ps1 stage "tools"), else a system one
QString InstallerBackend::python() const
{
#ifdef Q_OS_WIN
    const QString portable = m_root + QStringLiteral("/data/_tools/python/python.exe");
    if (QFileInfo::exists(portable))
        return portable;
#endif
    const QString found = workingPython();
    return found.isEmpty() ? QStringLiteral("python") : found;
}

// Read the same portable-tool manifest as the PowerShell pipeline.
bool InstallerBackend::toolsReady() const
{
#ifdef Q_OS_LINUX
    return !workingPython().isEmpty() && onPath("git") && onPath("cmake")
        && onPath("ninja") && onPath("clang") && onPath("clang++") && onPath("pkg-config");
#else
    QFile manifest(m_root + QStringLiteral("/tools/pipeline/toolchains.json"));
    if (!manifest.open(QIODevice::ReadOnly))
        return false;
    const auto tools = QJsonDocument::fromJson(manifest.readAll()).object().value(QStringLiteral("tools")).toObject();
    if (tools.isEmpty())
        return false;
    for (auto it = tools.begin(); it != tools.end(); ++it) {
        const auto tool = it.value().toObject();
        const auto path = m_root + QStringLiteral("/data/_tools/") + tool.value(QStringLiteral("dir")).toString()
            + QLatin1Char('/') + tool.value(QStringLiteral("exe")).toString();
        if (!QFileInfo::exists(path))
            return false;
    }
    return true;
#endif
}

// the CMake/Ninja build folder: a short path (the runtime's dependencies exceed MAX_PATH under long folders), chosen
// per copy by tools/pipeline/build.ps1 and kept in data/build-root.txt (C:\gow-build, or C:\gow-build-<hash> when
// another copy already uses that one)
QString InstallerBackend::buildRoot() const
{
#ifdef Q_OS_LINUX
    QFile file(m_root + QStringLiteral("/data/build-root-linux.txt"));
#else
    QFile file(m_root + QStringLiteral("/data/build-root.txt"));
#endif
    if (file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        const QString path = QString::fromUtf8(file.readAll()).trimmed();
        if (!path.isEmpty())
            return QDir::fromNativeSeparators(path);
    }
#ifdef Q_OS_LINUX
    return m_root + QStringLiteral("/data/build-linux/") + m_game;
#else
    return QStringLiteral("C:/gow-build");
#endif
}

QString InstallerBackend::runnerPath() const
{
    // clang builds go to <build root>-clang (build.ps1)
    QString folder = buildRoot();
#ifdef Q_OS_WIN
    if (installedToolchain(m_root) == QStringLiteral("clang"))
        folder += QStringLiteral("-clang");
#endif
    // A fresh installation must not reuse the default build folder of another repository copy.
    QFile cache(folder + QStringLiteral("/CMakeCache.txt"));
    if (!cache.open(QIODevice::ReadOnly | QIODevice::Text))
        return {};
    QString source;
    const QByteArray prefix("CMAKE_HOME_DIRECTORY:INTERNAL=");
    while (!cache.atEnd())
    {
        const QByteArray line = cache.readLine().trimmed();
        if (line.startsWith(prefix))
            source = QDir::cleanPath(QDir::fromNativeSeparators(QString::fromUtf8(line.mid(prefix.size()))));
    }
    const QString expected = QDir::cleanPath(m_root + QStringLiteral("/engine/runtime/PS2Recomp"));
#ifdef Q_OS_WIN
    const auto pathCase = Qt::CaseInsensitive;
#else
    const auto pathCase = Qt::CaseSensitive;
#endif
    if (source.compare(expected, pathCase) != 0)
        return {};
#ifdef Q_OS_WIN
    const QString exe = folder + QStringLiteral("/ps2xRuntime/ps2EntryRunner.exe");
#else
    const QString exe = folder + QStringLiteral("/ps2xRuntime/ps2EntryRunner");
#endif
    return QFileInfo::exists(exe) ? exe : QString();
}

QVariantMap InstallerBackend::environment() const
{
    const QString runtimeDir = m_root + QStringLiteral("/engine/runtime");
    return {
        {QStringLiteral("tools"), toolsReady()},
        {QStringLiteral("runtime"), QFileInfo::exists(runtimeDir + QStringLiteral("/PS2Recomp/CMakeLists.txt"))},
        {QStringLiteral("game"), !runnerPath().isEmpty()},
        {QStringLiteral("discs"), !languages().isEmpty()},
        {QStringLiteral("runtimeDir"), runtimeDir},
        {QStringLiteral("runner"), runnerPath()},
        {QStringLiteral("dataDir"), m_root + QStringLiteral("/data")},
    };
}

QString InstallerBackend::diagnosticsFramePc() const
{
    // A line scan is enough for this one key: game.toml is written by hand, `frame_pc = "0x..."` under [diagnostics].
    QFile file(m_root + QStringLiteral("/games/") + m_game + QStringLiteral("/game.toml"));
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return {};
    bool inSection = false;
    for (const QByteArray &raw : file.readAll().split('\n'))
    {
        const QString line = QString::fromUtf8(raw).section(QLatin1Char('#'), 0, 0).trimmed();
        if (line.startsWith(QLatin1Char('[')))
            inSection = line == QStringLiteral("[diagnostics]");
        else if (inSection && line.section(QLatin1Char('='), 0, 0).trimmed() == QStringLiteral("frame_pc"))
        {
            QString value = line.section(QLatin1Char('='), 1).trimmed();
            value.remove(QLatin1Char('"'));
            bool ok = false;
            value.toUInt(&ok, 0);
            return ok ? value : QString();
        }
    }
    return {};
}

void InstallerBackend::openRunnerFolder() const
{
    const QString runner = runnerPath();
    if (!runner.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(runner).absolutePath()));
}

QVariantList InstallerBackend::languages() const
{
    QFile file(m_root + QStringLiteral("/data/") + m_game + QStringLiteral("/languages.json"));
    const QJsonObject manifest = file.open(QIODevice::ReadOnly)
        ? QJsonDocument::fromJson(file.readAll()).object() : QJsonObject();
    QVariantList out;
    for (const QJsonValue &v : manifest.value(QStringLiteral("languages")).toArray())
        if (QFileInfo::exists(v.toObject().value(QStringLiteral("elf")).toString())) {
            auto entry = v.toObject().toVariantMap();
            entry.insert(QStringLiteral("runner"), runnerPath());
            out << entry;
        }
    out.append(RegionalInstallations::read(m_root, m_game));
    return out;
}

bool InstallerBackend::firstPlayPrepared() const
{
    return QFileInfo::exists(m_root + QStringLiteral("/data/") + m_game + QStringLiteral("/native.stamp"));
}

bool InstallerBackend::hasPendingNativeCode() const
{
    const QString base = m_root + QStringLiteral("/data/") + m_game;
    const QDateTime built = QFileInfo(base + QStringLiteral("/native.stamp")).lastModified();
    const QDir captures(base + QStringLiteral("/vu1_capture"));
    for (const QFileInfo &file : captures.entryInfoList({QStringLiteral("*.bin"), QStringLiteral("vu1n_heads_seen.txt")}, QDir::Files))
        if (!built.isValid() || file.lastModified() > built)
            return true;
    return false;
}

QVariantMap InstallerBackend::discScanReport() const
{
    QFile file(m_root + QStringLiteral("/data/") + m_game + QStringLiteral("/vu1_capture/disc-report.json"));
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object().toVariantMap();
}

QStringList InstallerBackend::loadingArt() const
{
    QDir dir(m_root + QStringLiteral("/data/") + m_game + QStringLiteral("/loading"));
    QStringList out;
    for (const QFileInfo &f : dir.entryInfoList({QStringLiteral("*.png"), QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"),
                                                 QStringLiteral("*.webp")}, QDir::Files, QDir::Name | QDir::IgnoreCase))
        out << QUrl::fromLocalFile(f.absoluteFilePath()).toString();
    return out;
}

QString InstallerBackend::recompileElf() const
{
    QFile file(m_root + QStringLiteral("/data/") + m_game + QStringLiteral("/languages.json"));
    if (!file.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(file.readAll()).object().value(QStringLiteral("recompile_elf")).toString();
}

void InstallerBackend::identify(const QStringList &paths)
{
    if (running() || identifying() || paths.isEmpty())
        return;
    auto *p = new QProcess(this);
    m_identifying = p;
    emit identifyingChanged();
    p->setProgram(python());
    p->setArguments(QStringList{QStringLiteral("-I"), m_root + QStringLiteral("/tools/disc/identify.py")} + paths);
    connect(p, &QProcess::readyReadStandardError, this, [this, p]()
    {
        emit logLine(QString::fromUtf8(p->readAllStandardError()).trimmed());
    });
    const auto complete = [this, p, paths](bool failed)
    {
        if (m_identifying != p) return;
        const QJsonArray list = QJsonDocument::fromJson(p->readAllStandardOutput()).array();
        QVariantList results = list.toVariantList();
        // A foreign-code disc is playable only through its registered regional runner.
        // Keep compatible=false: the USA recompilation pipeline must never consume it.
        for (auto &result : results) {
            auto disc = result.toMap();
            for (const auto &entry : RegionalInstallations::read(m_root, m_game)) {
                const auto region = entry.toMap();
                if (disc.value("region") == region.value("region")
                    && disc.value("elf_crc") == region.value("elf_crc")
                    && disc.value("text_sha1") == region.value("text_sha1")) {
                    disc.insert("playable", true);
                    disc.insert("selection", region.value("language"));
                    disc.insert("reason_code", "regional_installed");
                    disc.insert("problems", QStringList());
                }
            }
            result = disc;
        }
        if (failed || results.isEmpty())
        {
            results.clear();
            for (const QString &path : paths)
                results.append(QVariantMap{{QStringLiteral("path"), path}, {QStringLiteral("compatible"), false},
                    {QStringLiteral("reason_code"), QStringLiteral("import_failed")},
                    {QStringLiteral("problems"), QStringList{p->errorString()}}});
        }
        m_identifying = nullptr;
        emit identifyingChanged();
        emit identified(results);
        p->deleteLater();
    };
    connect(p, &QProcess::finished, this, [complete](int code, QProcess::ExitStatus status)
    {
        complete(code != 0 || status != QProcess::NormalExit);
    });
    connect(p, &QProcess::errorOccurred, this, [complete](QProcess::ProcessError error)
    {
        if (error == QProcess::FailedToStart) complete(true);
    });
    p->start();
}

bool InstallerBackend::run(const QString &stages, const QVariantMap &options)
{
    if (m_process || m_identifying)
        return false;
#ifdef Q_OS_WIN
    const QString script = m_root + QStringLiteral("/tools/pipeline/build.ps1");
#else
    const QString script = m_root + QStringLiteral("/tools/pipeline/linux.py");
#endif
    // An antivirus can quarantine the pipeline script: PowerShell then reports "the term ... is not recognized" (the file
    // was there when it checked -File and gone when it ran it), which says nothing to a player. Say what happened.
    if (!QFileInfo::exists(script))
    {
        QMetaObject::invokeMethod(this, [this] { emit finished(false, kPipelineScriptGone); }, Qt::QueuedConnection);
        return true;
    }
#ifdef Q_OS_WIN
    QStringList args{QStringLiteral("-NoProfile"), QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"),
                     QStringLiteral("-File"), script,
                     QStringLiteral("-Game"), m_game, QStringLiteral("-Stages"), stages};
    // no -BuildRoot: build.ps1 picks this copy's build folder and records it in data/build-root.txt
    const QStringList isos = options.value(QStringLiteral("isos")).toStringList();
    if (!isos.isEmpty())
        args << QStringLiteral("-Discs") << isos.join(QLatin1Char('|'));
    const QString xdelta = options.value(QStringLiteral("xdelta")).toString(); // stage xdelta: the ISO patch to apply
    if (!xdelta.isEmpty())
        args << QStringLiteral("-Xdelta") << xdelta;
    const QString config = options.value(QStringLiteral("config"), QStringLiteral("Release")).toString();
    args << QStringLiteral("-Config") << config;
    args << QStringLiteral("-Toolchain") << QStringLiteral("clang");
    if (options.value(QStringLiteral("ltcg")).toBool())
        args << QStringLiteral("-Ltcg");
#else
    QStringList args{QStringLiteral("-I"), QStringLiteral("-u"), script,
                     QStringLiteral("--game"), m_game, QStringLiteral("--stages"), stages,
                     QStringLiteral("--config"), options.value(QStringLiteral("config"), QStringLiteral("Release")).toString()};
    const QString xdelta = options.value(QStringLiteral("xdelta")).toString();
    if (!xdelta.isEmpty()) args << QStringLiteral("--xdelta") << xdelta;
    const QStringList isos = options.value(QStringLiteral("isos")).toStringList();
    if (!isos.isEmpty()) args << QStringLiteral("--discs") << isos;
#endif
    m_stages = stages;
    m_process = new QProcess(this);
#ifdef Q_OS_WIN
    m_process->setProgram(QStringLiteral("powershell.exe"));
#else
    m_process->setProgram(python());
#endif
    m_process->setArguments(args);
    // The runtime keeps no shader cache: PS2X_GS_SHADER_CACHE_DIR is not read, so none is passed.
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    m_process->setProcessEnvironment(environment);
    m_process->setWorkingDirectory(m_root);
    m_process->setProcessChannelMode(QProcess::MergedChannels);
    connect(m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error)
    {
        if (error != QProcess::FailedToStart || !m_process)
            return;
        emit logLine(m_process->errorString());
        m_process->deleteLater();
        m_process = nullptr;
        emit runningChanged();
        emit finished(false, -1);
    });
    connect(m_process, &QProcess::readyReadStandardOutput, this, &InstallerBackend::readOutput);
    connect(m_process, &QProcess::finished, this, [this, script](int code, QProcess::ExitStatus status)
    {
        if (!m_process)
            return;
        if ((status != QProcess::NormalExit || code != 0) && !QFileInfo::exists(script))
            code = kPipelineScriptGone;
        readOutput();
        if (!m_pending.isEmpty())
            emit logLine(QString::fromLocal8Bit(m_pending));
        m_pending.clear();
        m_process->deleteLater();
        m_process = nullptr;
        emit runningChanged();
        emit finished(status == QProcess::NormalExit && code == 0, code);
    });
    m_process->start();
    emit runningChanged();
    return true;
}

void InstallerBackend::readOutput()
{
    if (!m_process)
        return;
    m_pending += m_process->readAllStandardOutput();
    qsizetype nl;
    while ((nl = m_pending.indexOf('\n')) >= 0)
    {
        QString line = QString::fromLocal8Bit(m_pending.left(nl)).trimmed();
        m_pending.remove(0, nl + 1);
        if (line.isEmpty())
            continue;
        if (line.startsWith(QStringLiteral("@@progress ")))
        {
            const QStringList f = line.mid(11).split(QLatin1Char(' '));
            if (f.size() == 2)
                emit progress(f[0].toInt(), f[1].toInt());
        }
        else if (line.startsWith(QStringLiteral("@@status ")))
            emit statusText(line.mid(9));
        else if (line.startsWith(QStringLiteral("=== ")) && line.endsWith(QStringLiteral(" ===")))
            emit stepChanged(line.mid(4, line.size() - 8));
        else
            emit logLine(line);
    }
}

void InstallerBackend::cancel()
{
    if (!m_process)
        return;
    // the pipeline starts compilers and the game: end the whole process tree
#ifdef Q_OS_WIN
    QProcess::execute(QStringLiteral("taskkill"), {QStringLiteral("/T"), QStringLiteral("/F"), QStringLiteral("/PID"),
                                                   QString::number(m_process->processId())});
#else
    m_process->terminate(); // linux.py signals only its private process group
#endif
}

void InstallerBackend::checkUpdate()
{
#ifndef Q_OS_WIN
    emit updateChecked({{QStringLiteral("error"), QStringLiteral("Linux updates use the source checkout; see docs/linux.md.")}});
    return;
#else
    auto *p = new QProcess(this);
    p->setProgram(QStringLiteral("powershell.exe"));
    p->setArguments({QStringLiteral("-NoProfile"), QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"), QStringLiteral("-File"),
                     m_root + QStringLiteral("/tools/pipeline/update.ps1"), QStringLiteral("-Check")});
    connect(p, &QProcess::finished, this, [this, p](int, QProcess::ExitStatus)
    {
        const QByteArray out = p->readAllStandardOutput().trimmed();
        const QJsonDocument doc = QJsonDocument::fromJson(out.mid(out.lastIndexOf('\n') + 1));
        emit updateChecked(doc.isObject() ? doc.object().toVariantMap() : QVariantMap{{QStringLiteral("error"), QString::fromLocal8Bit(out)}});
        p->deleteLater();
    });
    p->start();
#endif
}

bool InstallerBackend::applyUpdate(const QString &url, const QString &sha256, const QString &version)
{
#ifndef Q_OS_WIN
    Q_UNUSED(url); Q_UNUSED(sha256); Q_UNUSED(version);
    return false;
#else
    if (m_process || url.isEmpty())
        return false;
    // detached: the script waits for this process to end before replacing its files, then starts the launcher again
    const bool started = QProcess::startDetached(QStringLiteral("powershell.exe"),
        {QStringLiteral("-NoProfile"), QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"), QStringLiteral("-WindowStyle"),
         QStringLiteral("Hidden"), QStringLiteral("-File"), m_root + QStringLiteral("/tools/pipeline/update.ps1"), QStringLiteral("-Apply"),
         QStringLiteral("-Url"), url, QStringLiteral("-Sha256"), sha256, QStringLiteral("-Version"), version,
         QStringLiteral("-WaitPid"), QString::number(QCoreApplication::applicationPid())}, m_root);
    if (started)
        QCoreApplication::quit();
    return started;
#endif
}

int InstallerBackend::cpuThreads() const
{
    return QThread::idealThreadCount();
}

bool InstallerBackend::cpuSupported() const
{
#if (defined(__clang__) || defined(__GNUC__)) && (defined(__x86_64__) || defined(__i386__))
    __builtin_cpu_init();
    return __builtin_cpu_supports("sse4.2") && __builtin_cpu_supports("popcnt");
#elif defined(Q_OS_LINUX)
    return false; // The native Linux pipeline currently targets x86-64-v2 only.
#else
    return true;
#endif
}

bool InstallerBackend::pgoApplied() const
{
    const QString runner = runnerPath();
    if (runner.isEmpty())
        return false;
    // trained on a runtime an update has since changed (tools/pipeline/update.ps1): recommend training it again
    if (QFileInfo::exists(m_root + QStringLiteral("/data/pgo-stale.txt")))
        return false;
    QFile cache(QFileInfo(runner).dir().absoluteFilePath(QStringLiteral("../CMakeCache.txt")));
    if (!cache.open(QIODevice::ReadOnly))
        return false;
    for (const QByteArray &line : cache.readAll().split('\n'))
        if (line.startsWith("CMAKE_CXX_FLAGS:") && line.contains("-fprofile-instr-use="))
            return true;
    return false;
}

bool InstallerBackend::needsRebuild() const
{
    return QFileInfo::exists(m_root + QStringLiteral("/data/needs-rebuild.txt"));
}

void InstallerBackend::openRequirementPage(const QString &which) const
{
#ifdef Q_OS_LINUX
    Q_UNUSED(which);
    QDesktopServices::openUrl(QUrl::fromLocalFile(m_root + QStringLiteral("/docs/linux.md")));
#else
    static const QVariantMap pages{
        {QStringLiteral("git"), QStringLiteral("https://git-scm.com/download/win")},
        {QStringLiteral("python"), QStringLiteral("https://www.python.org/downloads/windows/")},
    };
    QDesktopServices::openUrl(QUrl(pages.value(which).toString()));
#endif
}
