#include "installer_backend.h"

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
    // (it only opens the Store), so being on PATH is not enough. "python" first, then the "py" launcher.
    QString workingPython()
    {
        static const QString found = []
        {
            for (const QString &candidate : {QStringLiteral("python"), QStringLiteral("py")})
            {
                if (!onPath(candidate))
                    continue;
                QProcess probe;
                probe.start(candidate, {QStringLiteral("-c"), QStringLiteral("import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)")});
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
    const QString portable = m_root + QStringLiteral("/data/_tools/python/python.exe");
    if (QFileInfo::exists(portable))
        return portable;
    const QString found = workingPython();
    return found.isEmpty() ? QStringLiteral("python") : found;
}

// Read the same portable-tool manifest as the PowerShell pipeline.
bool InstallerBackend::toolsReady() const
{
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
}

// the CMake/Ninja build folder: a short path (the runtime's dependencies exceed MAX_PATH under long folders), chosen
// per copy by tools/pipeline/build.ps1 and kept in data/build-root.txt (C:\gow-build, or C:\gow-build-<hash> when
// another copy already uses that one)
QString InstallerBackend::buildRoot() const
{
    QFile file(m_root + QStringLiteral("/data/build-root.txt"));
    if (file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        const QString path = QString::fromUtf8(file.readAll()).trimmed();
        if (!path.isEmpty())
            return QDir::fromNativeSeparators(path);
    }
    return QStringLiteral("C:/gow-build");
}

QString InstallerBackend::runnerPath() const
{
    // clang builds go to <build root>-clang (build.ps1)
    QString folder = buildRoot();
    if (installedToolchain(m_root) == QStringLiteral("clang"))
        folder += QStringLiteral("-clang");
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
    if (source.compare(expected, Qt::CaseInsensitive) != 0)
        return {};
    const QString exe = folder + QStringLiteral("/ps2xRuntime/ps2EntryRunner.exe");
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
    if (!file.open(QIODevice::ReadOnly))
        return {};
    const QJsonObject manifest = QJsonDocument::fromJson(file.readAll()).object();
    QVariantList out;
    for (const QJsonValue &v : manifest.value(QStringLiteral("languages")).toArray())
        if (QFileInfo::exists(v.toObject().value(QStringLiteral("elf")).toString()))
            out << v.toObject().toVariantMap();
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
    auto *p = new QProcess(this);
    p->setProgram(python());
    p->setArguments(QStringList{QStringLiteral("-I"), m_root + QStringLiteral("/tools/disc/identify.py")} + paths);
    connect(p, &QProcess::finished, this, [this, p](int, QProcess::ExitStatus)
    {
        const QJsonArray list = QJsonDocument::fromJson(p->readAllStandardOutput()).array();
        emit identified(list.toVariantList());
        p->deleteLater();
    });
    p->start();
}

bool InstallerBackend::run(const QString &stages, const QVariantMap &options)
{
    if (m_process)
        return false;
    QStringList args{QStringLiteral("-NoProfile"), QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"),
                     QStringLiteral("-File"), m_root + QStringLiteral("/tools/pipeline/build.ps1"),
                     QStringLiteral("-Game"), m_game, QStringLiteral("-Stages"), stages};
    // no -BuildRoot: build.ps1 picks this copy's build folder and records it in data/build-root.txt
    const QStringList isos = options.value(QStringLiteral("isos")).toStringList();
    if (!isos.isEmpty())
        args << QStringLiteral("-Discs") << isos.join(QLatin1Char('|'));
    const QString config = options.value(QStringLiteral("config"), QStringLiteral("Release")).toString();
    args << QStringLiteral("-Config") << config;
    args << QStringLiteral("-Toolchain") << QStringLiteral("clang");
    if (options.value(QStringLiteral("ltcg")).toBool())
        args << QStringLiteral("-Ltcg");
    m_stages = stages;
    m_process = new QProcess(this);
    m_process->setProgram(QStringLiteral("powershell.exe"));
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
    connect(m_process, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status)
    {
        if (!m_process)
            return;
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
    QProcess::execute(QStringLiteral("taskkill"), {QStringLiteral("/T"), QStringLiteral("/F"), QStringLiteral("/PID"),
                                                   QString::number(m_process->processId())});
}

void InstallerBackend::checkUpdate()
{
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
}

bool InstallerBackend::applyUpdate(const QString &url, const QString &sha256, const QString &version)
{
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
}

int InstallerBackend::cpuThreads() const
{
    return QThread::idealThreadCount();
}

bool InstallerBackend::pgoApplied() const
{
    const QString runner = runnerPath();
    if (runner.isEmpty())
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
    static const QVariantMap pages{
        {QStringLiteral("git"), QStringLiteral("https://git-scm.com/download/win")},
        {QStringLiteral("python"), QStringLiteral("https://www.python.org/downloads/windows/")},
    };
    QDesktopServices::openUrl(QUrl(pages.value(which).toString()));
}
