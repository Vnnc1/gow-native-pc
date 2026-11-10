// Mod manager for the launcher (exposed to QML as "modeloMods"): discovery and metadata through
// tools/mods/gow_mods_cli.py, enable/disable order, plan conflicts/missing files, persistence and the environment
// the runner needs. It never edits game files: the CLI stages copies and the runner is pointed at them
// (GOW_MOD_VFS_TABLE / GOW_TEXTURE_PACK, runtime patches 52/55/71). Nothing changes when no mod is enabled.
#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QObject>
#include <QProcess>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>

class InstallerBackend;

class ModsModel : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList mods READ mods NOTIFY modsChanged)
    Q_PROPERTY(QVariantList diagnostics READ diagnostics NOTIFY diagnosticsChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString notice READ notice NOTIFY stateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY stateChanged)
    Q_PROPERTY(int enabledCount READ enabledCount NOTIFY modsChanged)
    Q_PROPERTY(bool active READ active NOTIFY stateChanged)
    Q_PROPERTY(bool stale READ stale NOTIFY stateChanged)
    Q_PROPERTY(bool pythonReady READ pythonReady NOTIFY stateChanged)
    Q_PROPERTY(QString modsDir READ modsDir NOTIFY stateChanged)
    Q_PROPERTY(QString profile READ profile NOTIFY profileChanged)
    Q_PROPERTY(QVariantList profiles READ profiles NOTIFY profilesChanged)
    // Runtime evidence written by mod_vfs_table.cpp (GOW_MOD_VFS_STATS), so the player can see that a
    // file/texture mod really took effect instead of guessing.
    Q_PROPERTY(QVariantMap lastRun READ lastRun NOTIFY stateChanged)
    // True when the plan contains declarative data patches: the runner must have been rebuilt with runtime
    // patch 84, otherwise it simply ignores GOW_MOD_PATCH_TABLE. Never pretend the mod took effect.
    Q_PROPERTY(bool requiresRebuild READ requiresRebuild NOTIFY stateChanged)

public:
    explicit ModsModel(InstallerBackend *installer, QObject *parent = nullptr);

    QVariantList mods() const { return m_mods; }
    QVariantList diagnostics() const { return m_diagnostics; }
    bool busy() const { return m_busy; }
    QString notice() const { return m_notice; }
    QString lastError() const { return m_lastError; }
    int enabledCount() const { return m_enabled; }
    // True only when the launcher profile itself has a staged plan (other profiles are not ours to restore).
    bool active() const { return m_active && m_estadoPerfil == profile(); }
    bool stale() const { return m_stale; }
    bool pythonReady() const { return !m_python.isEmpty(); }
    QString modsDir() const;
    QString profile() const { return m_perfil; }
    QVariantList profiles() const { return m_perfiles; }
    QVariantMap lastRun() const { return m_lastRun; }
    bool requiresRebuild() const { return m_requiresRebuild; }

    // Reads data/mods/packages through the CLI and the current activation state.
    Q_INVOKABLE void refresh();
    // Adds/removes the mod from the active profile (persisted by the CLI); invalid mods cannot be enabled.
    Q_INVOKABLE bool setEnabled(const QString &key, bool enabled);
    // One CLI call for a whole selection (Enable all / Disable all / filtered batch).
    Q_INVOKABLE bool setEnabledBatch(const QStringList &keys, bool enabled);
    // Drag & drop: copy dropped .zip files or folders into the drop folder and let the CLI install them.
    Q_INVOKABLE QVariantMap importarArchivos(const QStringList &rutas);
    // Named mod sets (profiles).
    Q_INVOKABLE QVariantMap cambiarPerfil(const QString &nombre);
    Q_INVOKABLE QVariantMap crearPerfil(const QString &nombre, const QString &copiarDe);
    Q_INVOKABLE QVariantMap borrarPerfil(const QString &nombre);
    // Share a mod: pack it into data/mods/exports/<id>@<version>.zip.
    Q_INVOKABLE QVariantMap exportar(const QString &key);
    Q_INVOKABLE void abrirExportaciones();
    // Stages the enabled mods and returns {ok, env, warnings, error}: env is passed to Lanzador::iniciar as
    // "modEntorno". With nothing enabled it returns the keys that must be removed, so a stale environment is not
    // inherited from a previous session.
    // Plans the current selection without staging it, to show conflicts/missing files before playing.
    Q_INVOKABLE QVariantMap analizar();
    Q_INVOKABLE QVariantMap prepararEntorno(const QString &pacoteManual, const QString &elf, const QString &runner);
    // Restores the original game files (the CLI undoes the staging transaction).
    Q_INVOKABLE bool descartar();
    // Installs an unpacked mod folder as data/mods/packages/<id>@<version>.
    Q_INVOKABLE QVariantMap importar(const QString &carpeta, bool reemplazar);
    Q_INVOKABLE void abrirCarpeta();
    Q_INVOKABLE void abrirCarpetaPaquete(const QString &ruta);

signals:
    void modsChanged();
    void diagnosticsChanged();
    void busyChanged();
    void stateChanged();
    void profileChanged();
    void profilesChanged();

private:
    struct Salida
    {
        bool ok = false;
        int codigo = -1;
        QString texto;
        QString error;
    };

    Salida ejecutar(const QStringList &argumentos, int timeoutMs = 15000) const;
    QString cli() const;
    QString repoRoot() const;
    void setBusy(bool valor);
    void cargarEstado(const QJsonObject &estado);
    // state.json is the CLI's transaction record: read it directly so the Play button always sees the current
    // activation, even when the Mods page has not been opened yet in this session.
    void leerEstado();
    void leerPerfilActivo();
    void refrescarPerfiles();
    void leerUltimaEjecucion();
    void anotarDiagnosticos(const QJsonArray &issues, const QJsonArray &warnings,
                            const QJsonArray &conflicts, const QJsonArray &excluded = QJsonArray());
    static QVariantList diagnosticos(const QJsonArray &items);
    static QString primerError(const QJsonArray &issues, int &total);
    static bool copiarCarpeta(const QString &origen, const QString &destino);

    InstallerBackend *m_installer = nullptr;
    QString m_python;
    QVariantList m_mods;
    QVariantList m_diagnostics;
    bool m_busy = false;
    QString m_notice;
    QString m_lastError;
    int m_enabled = 0;
    bool m_active = false;
    bool m_stale = false;
    QString m_staging;
    QString m_estadoPerfil;
    QString m_perfil = QStringLiteral("launcher");
    QVariantList m_perfiles;
    QVariantMap m_lastRun;
    bool m_requiresRebuild = false;
};
