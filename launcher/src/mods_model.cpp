#include <QRegularExpression>
#include "mods_model.h"

#include "installer_backend.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QProcess>
#include <QProcessEnvironment>
#include <QStandardPaths>
#include <QUrl>

namespace
{
    const char *kVariablesDeMods[] = {"GOW_ACTIVE_MODS", "GOW_MOD_VFS_TABLE", "GOW_MOD_VFS_STATS", "GOW_MOD_VFS_TRACE",
                                      "GOW_MOD_VFS_LOG", "GOW_MOD_PATCH_TABLE", "GOW_MOD_PATCH_LOG"};

    QString recortar(const QString &texto, int maximo = 220)
    {
        QString limpio = texto.simplified();
        return limpio.size() > maximo ? limpio.left(maximo - 1) + QChar(0x2026) : limpio;
    }
}

ModsModel::ModsModel(InstallerBackend *installer, QObject *parent)
    : QObject(parent)
    , m_installer(installer)
{
    QString portatil;
#ifdef Q_OS_WIN
    portatil = repoRoot() + QStringLiteral("/data/_tools/python/python.exe");
#else
    portatil = repoRoot() + QStringLiteral("/data/_tools/python/bin/python3");
#endif
    if (QFileInfo(portatil).isFile() && QFileInfo(portatil).isExecutable())
        m_python = portatil;
    else
        m_python = QStandardPaths::findExecutable(QStringLiteral("python3"));
    if (m_python.isEmpty())
        m_python = QStandardPaths::findExecutable(QStringLiteral("python"));
    leerPerfilActivo();
}

QString ModsModel::repoRoot() const
{
    if (m_installer && !m_installer->repoRoot().isEmpty())
        return m_installer->repoRoot();
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 8 && !dir.exists(QStringLiteral("engine/runtime.toml")); ++i)
        if (!dir.cdUp())
            break;
    return dir.exists(QStringLiteral("engine/runtime.toml")) ? dir.absolutePath() : QDir::currentPath();
}

QString ModsModel::cli() const
{
    return repoRoot() + QStringLiteral("/tools/mods/gow_mods_cli.py");
}

QString ModsModel::modsDir() const
{
    return repoRoot() + QStringLiteral("/data/mods");
}

ModsModel::Salida ModsModel::ejecutar(const QStringList &argumentos, int timeoutMs) const
{
    Salida salida;
    if (m_python.isEmpty()) {
        salida.error = QStringLiteral("Python 3.11+ was not found.");
        return salida;
    }
    if (!QFileInfo(cli()).isFile()) {
        salida.error = QStringLiteral("tools/mods/gow_mods_cli.py is missing.");
        return salida;
    }
    QProcess proceso;
    QProcessEnvironment entorno = QProcessEnvironment::systemEnvironment();
    entorno.insert(QStringLiteral("PYTHONUTF8"), QStringLiteral("1"));
    entorno.insert(QStringLiteral("PYTHONIOENCODING"), QStringLiteral("utf-8"));
    proceso.setProcessEnvironment(entorno);
    proceso.setWorkingDirectory(repoRoot());
    proceso.setProgram(m_python);
    proceso.setArguments(QStringList{QStringLiteral("-I"), cli()} + argumentos);
    proceso.setProcessChannelMode(QProcess::SeparateChannels);
    proceso.start();
    if (!proceso.waitForStarted(5000)) {
        salida.error = QStringLiteral("The mod manager could not start Python: ") + proceso.errorString();
        return salida;
    }
    if (!proceso.waitForFinished(timeoutMs)) {
        proceso.kill();
        proceso.waitForFinished(2000);
        salida.error = QStringLiteral("The mod manager did not respond (timeout).");
        return salida;
    }
    salida.codigo = proceso.exitCode();
    salida.texto = QString::fromUtf8(proceso.readAllStandardOutput()).trimmed();
    salida.error = QString::fromUtf8(proceso.readAllStandardError()).trimmed();
    salida.ok = proceso.exitStatus() == QProcess::NormalExit && salida.codigo == 0;
    if (!salida.ok && salida.error.isEmpty()) {
        // A JSON document on stdout is data, not an error message: never show a truncated plan as the failure.
        const QString limpio = salida.texto.trimmed();
        salida.error = (limpio.startsWith(QLatin1Char('{')) || limpio.startsWith(QLatin1Char('[')))
                           ? QStringLiteral("The mod manager failed without a diagnostic message.")
                           : recortar(salida.texto);
    }
    return salida;
}

void ModsModel::setBusy(bool valor)
{
    if (m_busy == valor)
        return;
    m_busy = valor;
    emit busyChanged();
}

QString ModsModel::primerError(const QJsonArray &issues, int &total)
{
    total = issues.size();
    QString mensaje;
    for (const QJsonValue &valor : issues) {
        const QJsonObject issue = valor.toObject();
        if (issue.value(QStringLiteral("severity")).toString() != QStringLiteral("error"))
            continue;
        mensaje = recortar(issue.value(QStringLiteral("message")).toString());
        break;
    }
    if (mensaje.isEmpty() && issues.size() > 0)
        mensaje = recortar(issues.first().toObject().value(QStringLiteral("message")).toString());
    return mensaje;
}

void ModsModel::cargarEstado(const QJsonObject &estado)
{
    const QJsonValue activo = estado.value(QStringLiteral("activePlan"));
    m_active = !activo.isNull() && !activo.isUndefined();
    m_staging = estado.value(QStringLiteral("staging")).toString();
    m_estadoPerfil = estado.value(QStringLiteral("profile")).toString();
}

void ModsModel::leerEstado()
{
    QFile archivo(modsDir() + QStringLiteral("/state.json"));
    if (!archivo.open(QIODevice::ReadOnly)) {
        // A missing/corrupt state file means "nothing staged"; never keep a stale "active" badge.
        m_active = false;
        m_staging.clear();
        m_estadoPerfil.clear();
        return;
    }
    const QJsonDocument documento = QJsonDocument::fromJson(archivo.readAll());
    if (documento.isObject())
        cargarEstado(documento.object());
    else {
        m_active = false;
        m_staging.clear();
        m_estadoPerfil.clear();
    }
}

void ModsModel::leerPerfilActivo()
{
    QFile archivo(modsDir() + QStringLiteral("/active-profile.txt"));
    if (!archivo.open(QIODevice::ReadOnly))
        return;
    const QString nombre = QString::fromUtf8(archivo.readAll()).trimmed();
    if (nombre.isEmpty() || nombre.size() > 32)
        return;
    const auto permitido = [](QChar c) {
        return (c >= QLatin1Char('a') && c <= QLatin1Char('z'))
            || (c >= QLatin1Char('0') && c <= QLatin1Char('9'))
            || c == QLatin1Char('_') || c == QLatin1Char('-');
    };
    for (const QChar &c : nombre)
        if (!permitido(c))
            return;
    m_perfil = nombre;
}

void ModsModel::refrescarPerfiles()
{
    const Salida salida = ejecutar({QStringLiteral("profiles"), QStringLiteral("--json")}, 15000);
    if (!salida.ok)
        return;
    const QJsonDocument documento = QJsonDocument::fromJson(salida.texto.toUtf8());
    if (!documento.isArray())
        return;
    m_perfiles = documento.array().toVariantList();
    emit profilesChanged();
}

void ModsModel::leerUltimaEjecucion()
{
    QFile archivo(modsDir() + QStringLiteral("/last-vfs-stats.json"));
    if (!archivo.open(QIODevice::ReadOnly))
        return;
    const QJsonDocument documento = QJsonDocument::fromJson(archivo.readAll());
    if (!documento.isObject())
        return; // the runner may be writing it right now; a partial read must not fake a result
    m_lastRun = documento.object().toVariantMap();
    emit stateChanged();
}

bool ModsModel::copiarCarpeta(const QString &origen, const QString &destino)
{
    if (!QDir(destino).mkpath(QStringLiteral(".")))
        return false;
    const QDir base(origen);
    QDirIterator iterador(origen, QDirIterator::Subdirectories);
    while (iterador.hasNext()) {
        const QString ruta = iterador.next();
        const QFileInfo info(ruta);
        if (info.isSymLink())
            return false;
        const QString relativo = base.relativeFilePath(ruta);
        if (info.isDir()) {
            if (!QDir(destino).mkpath(relativo))
                return false;
        } else if (info.isFile()) {
            const QString objetivo = destino + QLatin1Char('/') + relativo;
            QFile::remove(objetivo);
            if (!QFile::copy(ruta, objetivo))
                return false;
        }
    }
    return true;
}

QVariantList ModsModel::diagnosticos(const QJsonArray &items)
{
    QVariantList salida;
    for (const QJsonValue &valor : items) {
        const QJsonObject issue = valor.toObject();
        if (salida.size() >= 16)
            break;
        const QString texto = recortar(issue.value(QStringLiteral("message")).toString());
        if (texto.isEmpty())
            continue;
        QVariantMap fila;
        fila.insert(QStringLiteral("severity"), issue.value(QStringLiteral("severity")).toString(QStringLiteral("warning")));
        fila.insert(QStringLiteral("message"), texto);
        fila.insert(QStringLiteral("mod"), issue.value(QStringLiteral("mod")).toString());
        salida.append(fila);
    }
    return salida;
}

void ModsModel::anotarDiagnosticos(const QJsonArray &issues, const QJsonArray &warnings,
                                   const QJsonArray &conflicts, const QJsonArray &excluded)
{
    QVariantList fila;
    // Excluded mods are the most actionable entry ("why did my mod not run?"), so keep them in the same panel.
    for (const auto &lista : {issues, warnings, conflicts, excluded}) {
        const QVariantList parcial = diagnosticos(lista);
        for (const QVariant &item : parcial) {
            if (fila.size() >= 16)
                break;
            fila.append(item);
        }
    }
    m_diagnostics = fila;
    emit diagnosticsChanged();
}

void ModsModel::refresh()
{
    if (m_busy)
        return;
    if (!pythonReady()) {
        m_lastError = QStringLiteral("Python 3.11+ was not found.");
        emit stateChanged();
        return;
    }
    setBusy(true);
    m_lastError.clear();

    const Salida lista = ejecutar({QStringLiteral("list"), QStringLiteral("-p"), profile(), QStringLiteral("--json")}, 20000);
    if (!lista.ok) {
        m_lastError = lista.error;
        setBusy(false);
        emit stateChanged();
        return;
    }
    QJsonParseError error;
    const QJsonDocument documento = QJsonDocument::fromJson(lista.texto.toUtf8(), &error);
    if (error.error != QJsonParseError::NoError || !documento.isArray()) {
        m_lastError = QStringLiteral("Could not read the mod list: ") + error.errorString();
        setBusy(false);
        emit stateChanged();
        return;
    }

    QVariantList mods;
    int habilitados = 0;
    for (const QJsonValue &valor : documento.array()) {
        QJsonObject fila = valor.toObject();
        QVariantMap item = fila.toVariantMap();
        const QString clave = fila.value(QStringLiteral("mod")).toString();
        item.insert(QStringLiteral("key"), clave);
        item.insert(QStringLiteral("label"), clave);
        if (item.value(QStringLiteral("name")).toString().isEmpty())
            item.insert(QStringLiteral("name"), clave);
        const QJsonArray issues = fila.value(QStringLiteral("issues")).toArray();
        int total = 0;
        item.insert(QStringLiteral("issueText"), primerError(issues, total));
        item.insert(QStringLiteral("issueCount"), total);
        const QJsonArray avisos = fila.value(QStringLiteral("warnings")).toArray();
        if (item.value(QStringLiteral("issueText")).toString().isEmpty() && avisos.size() > 0)
            item.insert(QStringLiteral("issueText"), recortar(avisos.first().toObject().value(QStringLiteral("message")).toString()));
        if (item.value(QStringLiteral("enabled")).toBool())
            ++habilitados;
        mods.append(item);
    }
    m_mods = mods;
    m_enabled = habilitados;
    // Show the "rebuild the runner once" hint as soon as the page opens, not only after Check/Play:
    // refresh() only runs list/status, so derive it from the enabled mods' capabilities.
    m_requiresRebuild = false;
    for (const QVariant &valor : m_mods) {
        const QVariantMap fila = valor.toMap();
        if (!fila.value(QStringLiteral("enabled")).toBool())
            continue;
        for (const QVariant &cap : fila.value(QStringLiteral("capabilities")).toList()) {
            if (cap.toString() == QStringLiteral("data_patch")) {
                m_requiresRebuild = true;
                break;
            }
        }
        if (m_requiresRebuild)
            break;
    }

    const Salida estado = ejecutar({QStringLiteral("status"), QStringLiteral("--json")}, 15000);
    if (estado.ok) {
        const QJsonDocument doc = QJsonDocument::fromJson(estado.texto.toUtf8());
        if (doc.isObject()) {
            const QJsonObject raiz = doc.object();
            m_stale = raiz.value(QStringLiteral("stale")).toBool();
            cargarEstado(raiz.value(QStringLiteral("state")).toObject());
        }
    }
    // The Mods page shows the same counts in the user's language, so keep the notice for action results only.
    if (m_lastError.isEmpty())
        m_notice.clear();

    setBusy(false);
    refrescarPerfiles();
    leerUltimaEjecucion();
    emit modsChanged();
    emit stateChanged();
}

bool ModsModel::setEnabled(const QString &key, bool enabled)
{
    if (m_busy || key.isEmpty())
        return false;
    for (const QVariant &valor : m_mods) {
        const QVariantMap fila = valor.toMap();
        if (fila.value(QStringLiteral("key")).toString() != key)
            continue;
        if (enabled && !fila.value(QStringLiteral("valid")).toBool())
            return false;
    }
    const QString orden = enabled ? QStringLiteral("enable") : QStringLiteral("disable");
    setBusy(true);
    const Salida salida = ejecutar({orden, QStringLiteral("-p"), profile(), key}, 20000);
    if (!salida.ok) {
        m_lastError = salida.error;
        setBusy(false);
        emit stateChanged();
        return false;
    }
    setBusy(false); // refresh() is a no-op while busy
    refresh();
    return true;
}

bool ModsModel::setEnabledBatch(const QStringList &keys, bool enabled)
{
    if (m_busy || keys.isEmpty())
        return false;
    setBusy(true);
    const QString orden = enabled ? QStringLiteral("enable") : QStringLiteral("disable");
    const Salida salida = ejecutar(QStringList{orden, QStringLiteral("-p"), profile()} + keys, 30000);
    if (!salida.ok)
        m_lastError = salida.error;
    setBusy(false);
    if (!salida.ok) {
        emit stateChanged();
        return false;
    }
    refresh();
    return true;
}

QVariantMap ModsModel::importarArchivos(const QStringList &rutas)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy) {
        salida.insert(QStringLiteral("message"), QStringLiteral("The mod manager is busy."));
        return salida;
    }
    const QString drop = modsDir() + QStringLiteral("/mods");
    if (!QDir().mkpath(drop)) {
        salida.insert(QStringLiteral("message"), QStringLiteral("Could not create the mods folder."));
        return salida;
    }
    setBusy(true);
    int copiados = 0;
    QStringList problemas;
    for (const QString &ruta : rutas) {
        const QFileInfo info(ruta);
        const bool archivo = info.isFile();
        if (!info.exists() || (!archivo && !info.isDir())
            || (archivo && info.suffix().compare(QStringLiteral("zip"), Qt::CaseInsensitive) != 0)) {
            problemas.append(ruta);
            continue;
        }
        QString destino = drop + QLatin1Char('/') + info.fileName();
        int sufijo = 2;
        while (QFileInfo::exists(destino))
            destino = drop + QLatin1Char('/') + info.completeBaseName() + QLatin1Char('-')
                      + QString::number(sufijo++) + (archivo ? QStringLiteral(".zip") : QString());
        const bool copiado = archivo ? QFile::copy(ruta, destino) : copiarCarpeta(ruta, destino);
        if (copiado)
            ++copiados;
        else
            problemas.append(ruta);
    }
    setBusy(false);
    salida.insert(QStringLiteral("installed"), copiados);
    salida.insert(QStringLiteral("ok"), copiados > 0);
    if (!problemas.isEmpty())
        salida.insert(QStringLiteral("message"), problemas.join(QStringLiteral(", ")));
    refresh(); // the CLI validates and installs everything from the drop folder
    return salida;
}

QVariantMap ModsModel::cambiarPerfil(const QString &nombre)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy || nombre.isEmpty())
        return salida;
    if (nombre == m_perfil) {
        salida.insert(QStringLiteral("ok"), true);
        return salida;
    }
    // state.json is a single global transaction: clear the staged plan before switching selections.
    leerEstado();
    if (m_active)
        ejecutar({QStringLiteral("deactivate"), QStringLiteral("--reason"), QStringLiteral("profile-switch")}, 30000);
    m_perfil = nombre;
    QFile archivo(modsDir() + QStringLiteral("/active-profile.txt"));
    if (archivo.open(QIODevice::WriteOnly))
        archivo.write(m_perfil.toUtf8());
    emit profileChanged();
    refresh();
    salida.insert(QStringLiteral("ok"), true);
    return salida;
}

QVariantMap ModsModel::crearPerfil(const QString &nombre, const QString &copiarDe)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy || nombre.isEmpty())
        return salida;
    QStringList argumentos{QStringLiteral("profiles"), QStringLiteral("--create"), nombre};
    if (!copiarDe.isEmpty())
        argumentos << QStringLiteral("--from") << copiarDe;
    argumentos << QStringLiteral("--json");
    setBusy(true);
    const Salida resultado = ejecutar(argumentos, 15000);
    setBusy(false);
    if (!resultado.ok) {
        salida.insert(QStringLiteral("message"), resultado.error);
        return salida;
    }
    const QJsonDocument documento = QJsonDocument::fromJson(resultado.texto.toUtf8());
    if (documento.isArray()) {
        m_perfiles = documento.array().toVariantList();
        emit profilesChanged();
    }
    salida.insert(QStringLiteral("ok"), true);
    return salida;
}

QVariantMap ModsModel::borrarPerfil(const QString &nombre)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy || nombre.isEmpty() || nombre == QStringLiteral("launcher"))
        return salida;
    setBusy(true);
    const Salida resultado = ejecutar({QStringLiteral("profiles"), QStringLiteral("--delete"), nombre,
                                       QStringLiteral("--json")}, 15000);
    setBusy(false);
    if (!resultado.ok) {
        salida.insert(QStringLiteral("message"), resultado.error);
        return salida;
    }
    if (m_perfil == nombre) {
        m_perfil = QStringLiteral("launcher");
        QFile archivo(modsDir() + QStringLiteral("/active-profile.txt"));
        if (archivo.open(QIODevice::WriteOnly))
            archivo.write(m_perfil.toUtf8());
        emit profileChanged();
    }
    const QJsonDocument documento = QJsonDocument::fromJson(resultado.texto.toUtf8());
    if (documento.isArray()) {
        m_perfiles = documento.array().toVariantList();
        emit profilesChanged();
    }
    salida.insert(QStringLiteral("ok"), true);
    return salida;
}

QVariantMap ModsModel::exportar(const QString &key)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy || key.isEmpty())
        return salida;
    setBusy(true);
    const Salida resultado = ejecutar({QStringLiteral("export"), key, QStringLiteral("--json")}, 30000);
    setBusy(false);
    if (!resultado.ok) {
        salida.insert(QStringLiteral("message"), resultado.error);
        return salida;
    }
    const QJsonDocument documento = QJsonDocument::fromJson(resultado.texto.toUtf8());
    if (!documento.isObject()) {
        salida.insert(QStringLiteral("message"), QStringLiteral("Could not read the export result."));
        return salida;
    }
    const QString ruta = documento.object().value(QStringLiteral("path")).toString();
    salida.insert(QStringLiteral("ok"), true);
    salida.insert(QStringLiteral("path"), ruta);
    m_notice = QStringLiteral("Mod exported to ") + ruta;
    emit stateChanged();
    return salida;
}

void ModsModel::abrirExportaciones()
{
    const QString carpeta = modsDir() + QStringLiteral("/exports");
    QDir().mkpath(carpeta);
    QDesktopServices::openUrl(QUrl::fromLocalFile(carpeta));
}

QVariantMap ModsModel::analizar()
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy) {
        salida.insert(QStringLiteral("error"), QStringLiteral("The mod manager is busy."));
        return salida;
    }
    if (!pythonReady()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("Python 3.11+ was not found."));
        return salida;
    }
    struct Guard { ModsModel *self; ~Guard() { self->setBusy(false); } } guard{this};
    setBusy(true);
    const Salida planSalida = ejecutar({QStringLiteral("plan"), QStringLiteral("-p"), profile(), QStringLiteral("--json")}, 25000);
    if (!planSalida.ok) {
        salida.insert(QStringLiteral("error"), planSalida.error);
        m_lastError = planSalida.error;
        emit stateChanged();
        return salida;
    }
    const QJsonDocument documento = QJsonDocument::fromJson(planSalida.texto.toUtf8());
    if (!documento.isObject()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("Could not read the mod plan."));
        return salida;
    }
    const QJsonObject plan = documento.object();
    m_requiresRebuild = plan.value(QStringLiteral("requiresRebuild")).toBool();
    emit stateChanged();
    anotarDiagnosticos(plan.value(QStringLiteral("issues")).toArray(), plan.value(QStringLiteral("warnings")).toArray(),
                       plan.value(QStringLiteral("conflicts")).toArray(), plan.value(QStringLiteral("excluded")).toArray());
    // `plan --json` exits 0 even when the plan has errors (the document carries issues[]). Report the first
    // error instead of claiming the selection is fine; `apply` would refuse it anyway.
    for (const QJsonValue &valor : plan.value(QStringLiteral("issues")).toArray()) {
        const QJsonObject issue = valor.toObject();
        if (issue.value(QStringLiteral("severity")).toString() == QStringLiteral("error")) {
            salida.insert(QStringLiteral("error"), recortar(issue.value(QStringLiteral("message")).toString()));
            return salida;
        }
    }
    salida.insert(QStringLiteral("ok"), true);
    salida.insert(QStringLiteral("mods"), int(plan.value(QStringLiteral("mods")).toArray().size()));
    salida.insert(QStringLiteral("excluded"), int(plan.value(QStringLiteral("excluded")).toArray().size()));
    salida.insert(QStringLiteral("diagnostics"), int(m_diagnostics.size()));
    return salida;
}

QVariantMap ModsModel::prepararEntorno(const QString &pacoteManual, const QString &elf, const QString &runner)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    QVariantMap entorno;
    for (const char *nombre : kVariablesDeMods)
        entorno.insert(QString::fromLatin1(nombre), QString());
    salida.insert(QStringLiteral("env"), entorno);

    if (m_busy) {
        salida.insert(QStringLiteral("error"), QStringLiteral("The mod manager is busy."));
        return salida;
    }
    if (!pythonReady()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("Python 3.11+ was not found."));
        return salida;
    }
    struct Guard { ModsModel *self; ~Guard() { self->setBusy(false); } } guard{this};
    setBusy(true);
    leerEstado();

    const QStringList identity{QStringLiteral("--selected-elf"), elf, QStringLiteral("--selected-runner"), runner};
    const Salida planSalida = ejecutar(identity + QStringList{QStringLiteral("plan"), QStringLiteral("-p"), profile(), QStringLiteral("--json")}, 25000);
    if (!planSalida.ok) {
        salida.insert(QStringLiteral("error"), planSalida.error);
        return salida;
    }
    QJsonParseError error;
    const QJsonDocument documento = QJsonDocument::fromJson(planSalida.texto.toUtf8(), &error);
    if (error.error != QJsonParseError::NoError || !documento.isObject()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("Could not read the mod plan: ") + error.errorString());
        return salida;
    }
    const QJsonObject plan = documento.object();
    const QJsonArray mods = plan.value(QStringLiteral("mods")).toArray();
    const QJsonArray excluidos = plan.value(QStringLiteral("excluded")).toArray();
    m_requiresRebuild = plan.value(QStringLiteral("requiresRebuild")).toBool();
    emit stateChanged();
    anotarDiagnosticos(plan.value(QStringLiteral("issues")).toArray(), plan.value(QStringLiteral("warnings")).toArray(),
                       plan.value(QStringLiteral("conflicts")).toArray(), plan.value(QStringLiteral("excluded")).toArray());

    // `plan --json` reports errors inside the document. Refuse before staging anything: `apply` would reject the
    // plan too, and an error after apply would leave an active plan and staged files behind a failed launch.
    for (const QJsonValue &valor : plan.value(QStringLiteral("issues")).toArray()) {
        const QJsonObject issue = valor.toObject();
        if (issue.value(QStringLiteral("severity")).toString() == QStringLiteral("error")) {
            salida.insert(QStringLiteral("error"), recortar(issue.value(QStringLiteral("message")).toString()));
            return salida;
        }
    }

    if (mods.isEmpty()) {
        // Nothing selected: undo a previous launcher-profile activation if there is one, so the original game is
        // used and the staged copies are removed. A plan left by another profile is not touched.
        if (m_active && m_estadoPerfil == profile()) {
            ejecutar({QStringLiteral("deactivate"), QStringLiteral("--reason"), QStringLiteral("launcher-ui")}, 25000);
            leerEstado(); // the "Staged" badge must not survive a successful deactivate
        }
        if (!excluidos.isEmpty()) {
            const QString motivo = excluidos.first().toObject().value(QStringLiteral("message")).toString();
            salida.insert(QStringLiteral("error"),
                          motivo.isEmpty() ? QStringLiteral("Every enabled mod was excluded.") : motivo);
            return salida;
        }
        m_notice = QStringLiteral("No mods enabled; the original game is used.");
        salida.insert(QStringLiteral("ok"), true);
        salida.insert(QStringLiteral("applied"), 0);
        emit stateChanged();
        return salida;
    }

    const QJsonObject texturas = plan.value(QStringLiteral("textures")).toObject();
    // Check collisions BEFORE apply. An inherited GOW_TEXTURE_PACK is not a conflict: Lanzador::iniciar removes
    // it when the manual pack is off, and the staged mod pack is injected last.
    if (!texturas.isEmpty() && !pacoteManual.isEmpty()) {
        salida.insert(QStringLiteral("error"),
                      QStringLiteral("A texture-pack mod and the launcher's texture pack are both selected. Disable one of them."));
        return salida;
    }

    const Salida aplicado = ejecutar(identity + QStringList{QStringLiteral("apply"), QStringLiteral("-p"), profile()}, 60000);
    if (!aplicado.ok) {
        salida.insert(QStringLiteral("error"), aplicado.error);
        return salida;
    }

    // The CLI writes the activation state (plan, staging folder, hooks) as its last step.
    leerEstado();
    if (!m_active || m_staging.isEmpty()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("The mod activation did not produce a staging folder."));
        return salida;
    }

    QFile activatedFile(modsDir() + QStringLiteral("/hooks/plan.json"));
    if (!activatedFile.open(QIODevice::ReadOnly) ||
        QJsonDocument::fromJson(activatedFile.readAll()).object().value(QStringLiteral("planId")) != plan.value(QStringLiteral("planId"))) {
        salida.insert(QStringLiteral("error"), QStringLiteral("The selected build or mods changed during preparation. Try again."));
        return salida;
    }

    if (!plan.value(QStringLiteral("patches")).toArray().isEmpty())
        entorno.insert(QStringLiteral("GOW_MOD_PATCH_TABLE"),
                       QDir::toNativeSeparators(modsDir() + QStringLiteral("/hooks/data-patches.tsv")));
    if (!plan.value(QStringLiteral("vfs")).toObject().isEmpty()) {
        entorno.insert(QStringLiteral("GOW_MOD_VFS_TABLE"),
                       QDir::toNativeSeparators(modsDir() + QStringLiteral("/hooks/vfs-overrides.tsv")));
        // Runtime evidence: mod_vfs_table.cpp writes hit/lookup counters here while the game runs, so the
        // Mods page can prove the overrides were actually used (not just staged).
        entorno.insert(QStringLiteral("GOW_MOD_VFS_STATS"),
                       QDir::toNativeSeparators(modsDir() + QStringLiteral("/last-vfs-stats.json")));
    }
    if (!texturas.isEmpty())
        entorno.insert(QStringLiteral("GOW_TEXTURE_PACK"),
                       QDir::toNativeSeparators(m_staging + QStringLiteral("/textures")));

    const QJsonObject variables = plan.value(QStringLiteral("env")).toObject();
    for (auto it = variables.begin(); it != variables.end(); ++it) {
        const QString clave = it.key();
        // plan["env"] is { key: {value, mod} }. Reading the object with toString() yielded an empty string,
        // so Lanzador::iniciar removed the variable and every env mod silently did nothing. Accept both shapes
        // for compatibility with plans written by older manager versions.
        const QJsonValue bruto = it.value();
        const QString valor = bruto.isObject() ? bruto.toObject().value(QStringLiteral("value")).toString()
                                               : bruto.toString();
        if (clave.startsWith(QStringLiteral("GOW_MOD_VFS_")) || valor.isEmpty())
            continue;
        if (clave == QStringLiteral("GOW_TEXTURE_PACK") && !texturas.isEmpty())
            continue;
        entorno.insert(clave, valor);
    }

    QStringList activeNames;
    for (const auto &entry : mods) {
        const auto mod = entry.toObject();
        QString label = mod.value(QStringLiteral("id")).toString() + QStringLiteral(" @ ") + mod.value(QStringLiteral("version")).toString();
        label.replace(QRegularExpression(QStringLiteral("[;\\r\\n\\t]")), QStringLiteral(" "));
        activeNames.append(label.left(120));
        if (activeNames.size() == 32) break;
    }
    entorno.insert(QStringLiteral("GOW_ACTIVE_MODS"), activeNames.join(QLatin1Char(';')));
    salida.insert(QStringLiteral("env"), entorno);
    salida.insert(QStringLiteral("ok"), true);
    salida.insert(QStringLiteral("applied"), int(mods.size()));
    salida.insert(QStringLiteral("warnings"), int(m_diagnostics.size()));
    m_notice = QStringLiteral("%1 mod(s) staged for the next launch").arg(int(mods.size()));
    m_stale = false;
    emit stateChanged();
    return salida;
}

bool ModsModel::descartar()
{
    if (m_busy)
        return false;
    leerEstado();
    if (m_active && m_estadoPerfil != profile()) {
        m_lastError = QStringLiteral("Another profile staged these mods; restore it with the command-line manager.");
        emit stateChanged();
        return false;
    }
    setBusy(true);
    const Salida salida = ejecutar({QStringLiteral("deactivate"), QStringLiteral("--reason"), QStringLiteral("launcher-ui")}, 30000);
    if (!salida.ok)
        m_lastError = salida.error;
    else
        m_notice = QStringLiteral("Original files restored; the staged mods were removed.");
    setBusy(false);
    refresh();
    return salida.ok;
}

QVariantMap ModsModel::importar(const QString &carpeta, bool reemplazar)
{
    QVariantMap salida;
    salida.insert(QStringLiteral("ok"), false);
    if (m_busy)
        return salida;
    if (!QFileInfo(carpeta).isDir()) {
        salida.insert(QStringLiteral("error"), QStringLiteral("The chosen folder does not exist."));
        return salida;
    }
    m_lastError.clear();
    QStringList argumentos{QStringLiteral("import"), QDir::toNativeSeparators(carpeta)};
    if (reemplazar)
        argumentos.append(QStringLiteral("--replace"));
    setBusy(true);
    const Salida importado = ejecutar(argumentos, 30000);
    setBusy(false); // refresh() is a no-op while busy
    salida.insert(QStringLiteral("ok"), importado.ok);
    salida.insert(QStringLiteral("message"), importado.ok ? importado.texto : importado.error);
    if (!importado.ok)
        m_lastError = importado.error;
    refresh();
    return salida;
}

void ModsModel::abrirCarpeta()
{
    // Minecraft-style install folder: this is the only directory a player needs to touch.
    const QString carpeta = modsDir() + QStringLiteral("/mods");
    QDir().mkpath(carpeta);
    const QString leeme = carpeta + QStringLiteral("/README.txt");
    if (!QFileInfo::exists(leeme)) {
        QFile archivo(leeme);
        if (archivo.open(QIODevice::WriteOnly))
            archivo.write("Drop .zip files or unpacked mod folders here.\n"
                          "They are installed and enabled automatically when the launcher refreshes.\n"
                          "Delete a file here to uninstall its mod.\n");
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(carpeta));
}

void ModsModel::abrirCarpetaPaquete(const QString &ruta)
{
    if (!ruta.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(ruta));
}
