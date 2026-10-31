// Installation side of the launcher (exposed to QML as "installer"): finds the repository, checks the build tools,
// identifies disc images, runs the pipeline (tools/pipeline/build.ps1) with live progress, and reads the languages the
// prepared discs offer (data/<game>/languages.json). The play side stays in lanzador.cpp (Tobiichi's launcher).
//
// Pipeline output protocol (one line each, see tools/pipeline/build.ps1):
//   "=== <step> ==="          a new step               -> stepChanged(step)
//   "@@progress <done> <all>" progress of the step     -> progress(done, all)
//   "@@status <text>"         the step's current state -> statusText(text)
//   anything else             log                      -> logLine(line)
#pragma once

#include <QObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>

class InstallerBackend : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString repoRoot READ repoRoot CONSTANT)
    Q_PROPERTY(QString gameId READ gameId CONSTANT)
    Q_PROPERTY(bool running READ running NOTIFY runningChanged)
    // the stages of the current (or last) run, as passed to run(): the loading screen plans its overall bar from them
    Q_PROPERTY(QString stages READ stages NOTIFY runningChanged)

public:
    explicit InstallerBackend(QObject *parent = nullptr);

    QString repoRoot() const { return m_root; }
    QString gameId() const { return m_game; }
    bool running() const { return m_process != nullptr; }
    QString stages() const { return m_stages; }

    // {tools, runtime, game, discs: bool; runtimeDir, runner, dataDir: string}
    Q_INVOKABLE QVariantMap environment() const;
    // [diagnostics].frame_pc of games/<id>/game.toml (GOW_PERF_FRAME_PC with the diagnostics toggle), empty when absent
    Q_INVOKABLE QString diagnosticsFramePc() const;
    // the compiled game (empty when not built yet)
    Q_INVOKABLE QString runnerPath() const;
    Q_INVOKABLE void openRunnerFolder() const;
    // data/<game>/languages.json: [{language, label, edition, quality, elf}]
    Q_INVOKABLE QVariantList languages() const;
    // the recorded VU1 code was compiled in (optimize / native stage ran): the first play does not stutter
    Q_INVOKABLE bool firstPlayPrepared() const;
    Q_INVOKABLE bool hasPendingNativeCode() const;
    // The installed game was compiled with the profile-guided optimisation (its CMake flags use the profile).
    Q_INVOKABLE bool pgoApplied() const;
    // logical processors; the install skips the profile-guided build on small CPUs (InstallPage.qml)
    Q_INVOKABLE int cpuThreads() const;
    Q_INVOKABLE QVariantMap discScanReport() const;
    // pictures for the loading screen: the player's own images in data/<game>/loading (png, jpg, webp; none ship with
    // this repository), as file URLs, sorted by name
    Q_INVOKABLE QStringList loadingArt() const;
    // the executable recompiled by the pipeline (empty when no disc was prepared)
    Q_INVOKABLE QString recompileElf() const;
    // identifies disc images (tools/disc/identify.py) in the background -> identified(list)
    Q_INVOKABLE void identify(const QStringList &paths);
    // runs the pipeline: stages "fetch,discs,configure,recomp,sync,build" etc. options: isos (list), optimize (bool),
    // config ("Release"/"RelWithDebInfo"), ltcg (bool)
    Q_INVOKABLE bool run(const QString &stages, const QVariantMap &options);
    Q_INVOKABLE void cancel();
    // download pages of the requirements (Build Tools, Git, Python)
    Q_INVOKABLE void openRequirementPage(const QString &which) const;
    // launcher updates (tools/pipeline/update.ps1): the latest GitHub release in the background -> updateChecked({version,
    // tag, url, sha256, notes, page} or {error}); applying closes the launcher, the script replaces the files and starts it
    // again. needsRebuild: an update changed the runtime patches (data/needs-rebuild.txt) and the game must be rebuilt.
    Q_INVOKABLE void checkUpdate();
    Q_INVOKABLE bool applyUpdate(const QString &url, const QString &sha256, const QString &version);
    Q_INVOKABLE bool needsRebuild() const;

signals:
    void identified(const QVariantList &discs);
    void stepChanged(const QString &step);
    void progress(int done, int total);
    void statusText(const QString &text);
    void logLine(const QString &line);
    void finished(bool ok, int exitCode);
    void updateChecked(const QVariantMap &info);
    void runningChanged();

private:
    QString python() const;
    bool toolsReady() const;
    QString buildRoot() const;
    void readOutput();

    QString m_root;
    QString m_game = QStringLiteral("gow1");
    QProcess *m_process = nullptr;
    QByteArray m_pending;
    QString m_stages;
};
