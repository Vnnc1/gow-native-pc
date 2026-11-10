#include "diagnostic_kit.h"
#include "session_diagnostics.h"
#include "session_summary.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QProcess>
#include <QMap>
#include <QProcessEnvironment>
#include <QSaveFile>
#include <QSettings>
#include <QStandardPaths>
#include <QUrl>
#include <QtEndian>
#define NOMINMAX
#include <windows.h>
#include <commdlg.h>

namespace {
QJsonObject json(const QString &path) {
    QFile f(path);
    return f.open(QIODevice::ReadOnly) && f.size() <= 1024*1024 ? QJsonDocument::fromJson(f.readAll()).object() : QJsonObject();
}
QString hashFile(const QString &path) {
    QFile f(path); QCryptographicHash h(QCryptographicHash::Sha256);
    return f.open(QIODevice::ReadOnly) && h.addData(&f) ? QString::fromLatin1(h.result().toHex()) : QString();
}
QString textHash(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly) || f.size() < 52 || f.size() > 32*1024*1024) return {};
    const QByteArray b = f.readAll();
    if (b.left(4) != QByteArray("\x7f" "ELF",4) || b[4] != 1 || b[5] != 1) return {};
    const auto u16 = [&](qsizetype n) { return qFromLittleEndian<quint16>(b.constData()+n); };
    const auto u32 = [&](qsizetype n) { return qFromLittleEndian<quint32>(b.constData()+n); };
    const quint64 table = u32(32), stride = u16(46), count = u16(48), names = u16(50);
    if (u16(18) != 8 || stride < 40 || count == 0 || names >= count || table + stride*count > quint64(b.size())) return {};
    const quint64 ns = table + names*stride, no = u32(ns+16), size = u32(ns+20);
    if (no+size > quint64(b.size())) return {};
    for (quint64 i=0; i<count; ++i) {
        const quint64 s=table+i*stride, name=u32(s), offset=u32(s+16), bytes=u32(s+20);
        if (name+6 <= size && b.mid(no+name,6) == QByteArray(".text\0",6) && offset+bytes <= quint64(b.size()) && bytes)
            return QCryptographicHash::hash(b.mid(offset,bytes),QCryptographicHash::Sha1).toHex();
    }
    return {};
}
bool write(const QString &path, const QByteArray &bytes) {
    QSaveFile f(path); return f.open(QIODevice::WriteOnly) && f.write(bytes)==bytes.size() && f.commit();
}
}

DiagnosticKit::DiagnosticKit(QObject *parent) : QObject(parent) {
    m_root = QDir(QCoreApplication::applicationDirPath()).absoluteFilePath("../..");
    m_base = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    QDir().mkpath(m_base);
    m_manifest = json(m_root + "/diagnostic-kit.json");
    m_game = QSettings().value("game").toString();
    m_session = SessionDiagnostics::latest(m_base + "/registros");
    connect(&m_timer, &QTimer::timeout, this, &DiagnosticKit::refresh);
    m_timer.start(2000); refresh();
    if (m_manifest.value("schema").toInt()!=1) fail("diagInvalidPackage");
}
bool DiagnosticKit::fail(const QString &key, const QString &detail) {
    m_status=key; m_detail=detail; emit changed(); return false;
}
bool DiagnosticKit::selectGame(const QString &path) {
    if (m_running) return false;
    if (m_manifest.value("executable").toObject().value("text_sha1").toString().size()!=40 || elfName().isEmpty() || QFileInfo(path).fileName()!=elfName() ||
        textHash(path)!=m_manifest.value("executable").toObject().value("text_sha1").toString())
        return fail("diagInvalidGame");
    const QDir folder=QFileInfo(path).dir();
    for (const auto &v : m_manifest.value("required_files").toArray())
        if (!QFileInfo::exists(folder.filePath(v.toString()))) return fail("diagMissingDisc",v.toString());
    m_game=QFileInfo(path).absoluteFilePath(); QSettings().setValue("game",m_game);
    m_status="diagReady"; m_detail.clear(); emit changed(); return true;
}
void DiagnosticKit::chooseGame(const QString &title) {
    wchar_t filename[32768]{};
    const auto filter = (elfName()+QChar(0)+elfName()+QChar(0)+QChar(0)).toStdWString();
    const auto caption=title.toStdWString();
    OPENFILENAMEW of{}; of.lStructSize=sizeof(of); of.lpstrFile=filename; of.nMaxFile=32768;
    of.lpstrFilter=filter.c_str(); of.lpstrTitle=caption.c_str(); of.Flags=OFN_FILEMUSTEXIST|OFN_PATHMUSTEXIST|OFN_NOCHANGEDIR;
    if (GetOpenFileNameW(&of)) selectGame(QString::fromWCharArray(filename));
}
bool DiagnosticKit::start(bool detailed, bool fastVu, int scale) {
    refresh(); if (m_running) return false;
    __builtin_cpu_init();
    if (!__builtin_cpu_supports("sse4.2") || !__builtin_cpu_supports("popcnt")) return fail("diagCpuUnsupported");
    if (!selectGame(m_game)) return false;
    const QString runner=m_root+"/runtime/ps2EntryRunner.exe", helper=QCoreApplication::applicationDirPath()+"/gow-session.exe";
    if (m_manifest.value("schema").toInt()!=1 || m_manifest.value("runner_sha256").toString().size()!=64 || m_manifest.value("helper_sha256").toString().size()!=64 || hashFile(runner)!=m_manifest.value("runner_sha256").toString() || hashFile(helper)!=m_manifest.value("helper_sha256").toString())
        return fail("diagInvalidPackage");
    if (scale!=1 && scale!=2) return fail("diagInvalidPackage");
    const QString pc=m_manifest.value("frame_pc").toString();
    bool pcOk=false; const auto pcValue=pc.toUInt(&pcOk,0);
    if (!pcOk || pcValue<0x100000 || pcValue>=0x2000000 || pcValue%4) return fail("diagInvalidPackage");
    QVariantMap settings{{"diagnostics",detailed},{"framePc",pc},{"escala",scale},{"vuRapida",fastVu},
        {"fxaa",false},{"vsync",false},{"finAnticipado",true},{"jitInline",true},{"arranqueRapido",true},{"saltarVideos",true}};
    m_session=SessionDiagnostics::create(m_base+"/registros",settings);
    if (m_session.isEmpty()) return fail("diagWriteError");
    const auto abortStart = [&](const QString &key) {
        auto meta=json(m_session+"/session.json"); meta["state"]="failed_to_start";
        write(m_session+"/session.json",QJsonDocument(meta).toJson());
        return fail(key);
    };
    const QString id=QFileInfo(m_session).fileName(), card=m_base+"/cards/"+id+".ps2";
    QDir().mkpath(m_base+"/cards");
    const QString original=QFileInfo(m_game).dir().filePath("Mcd001.ps2");
    if (QFileInfo::exists(original) && (QFileInfo(original).size()>16*1024*1024 || !QFile::copy(original,card))) return abortStart("diagWriteError");
    auto env=QProcessEnvironment::systemEnvironment();
    for (const auto &k:env.keys()) if(k.startsWith("GOW_")||k.startsWith("PS2X_")||k.startsWith("TOBIICHI_")) env.remove(k);
    const QMap<QString,QString> values{
        {"GOW_PERF_DIAG",detailed?"1":"frames"},{"GOW_FRAME_DIAG","1"},{"GOW_PERF_FRAME_PC",pc},
        {"GOW_MC0",card},{"GOW_SAVES_DIR",m_base+"/saves/"+id},{"GOW_FAST_BOOT","1"},{"GOW_SKIP_FMV","1"},
        {"GOW_AUDIO_DEVICE","default"},{"GOW_VU1N_X64","1"},{"GOW_VU1X_INLINE","1"},{"GOW_VU1_FAST",fastVu?"1":"0"},
        {"GOW_VU1_CAPTURE_MISSES","0"},{"GOW_GS_EARLY_FINISH","1"},{"GOW_VU1_EARLY_FINISH","0"},
        {"GOW_GS_FINISH_ASINCRONO","1"},{"PS2X_GS_WORKER","1"},{"PS2X_GS_HW_SCALE",QString::number(scale)},
        {"TOBIICHI_ANCHO","1280"},{"TOBIICHI_ALTO","720"},{"TOBIICHI_PANTALLA","ventana"},{"TOBIICHI_IDIOMA","pt"},
        {"TOBIICHI_VSYNC","0"},{"TOBIICHI_VENTANA_FPS","60"},{"TOBIICHI_FPS_GOSTER","1"},{"TOBIICHI_FXAA","0"}};
    for(auto it=values.begin();it!=values.end();++it) env.insert(it.key(),it.value());
    if(detailed) for(const QString &k:{"GOW_SYNC_DIAG","GOW_VU1N_DIAG","GOW_AUDIO_STATS","GOW_IOP_DRIFT","GOW_GS_HW_STATS"}) env.insert(k,"1");
    if (QCoreApplication::arguments().contains("--game-smoke")) {
        env.insert("GOW_PAD_TEST","1"); env.insert("GOW_PAD_GUION",m_manifest.value("pad_script").toString());
        env.insert("GOW_PAD_CAPTURAS","10,80");
    }
    QProcess collector; collector.setProgram(helper); collector.setArguments({m_session,runner,m_game,m_root});
    collector.setWorkingDirectory(m_session); collector.setProcessEnvironment(env);
    if(!collector.startDetached()) return abortStart("diagLaunchError");
    m_running=true; m_report.clear(); m_status="diagRunning"; m_detail.clear(); emit changed(); return true;
}
void DiagnosticKit::refresh() {
    if(m_session.isEmpty()) return;
    const auto meta=SessionDiagnostics::sessionMetadata(m_session); const auto state=meta.value("state").toString();
    const bool active=state=="prepared"||state=="starting"||state=="running";
    if(active) {
        const auto stamp=QDateTime::fromString(meta.value("last_heartbeat_utc").toString(meta.value("created_utc").toString()),Qt::ISODateWithMs);
        m_running=stamp.isValid() && stamp.secsTo(QDateTime::currentDateTimeUtc())<30;
        if(!m_running) m_status="diagInterrupted";
    } else if(!state.isEmpty()) {
        m_running=false; m_status=state=="completed"?"diagFinished":"diagInterrupted";
        if(meta.value("final_metadata_incomplete").toBool() && m_report.isEmpty())
            SessionDiagnostics::writeSummary(m_session,meta);
        QFile f(m_session+"/RESUMO.txt"); if(f.open(QIODevice::ReadOnly)) m_report=QString::fromUtf8(f.read(32768));
    }
    emit changed();
}
void DiagnosticKit::stop() { if(m_running && !write(m_session+"/stop.request","stop")) fail("diagWriteError"); }
void DiagnosticKit::mark(const QString &note) {
    if(m_running && SessionDiagnostics::mark(m_session,note)) { m_status="diagMarked"; emit changed(); }
}
void DiagnosticKit::exportReport() {
    QString error; const auto path=SessionDiagnostics::exportZip(m_session,&error);
    if(path.isEmpty()) { fail("diagWriteError",error); return; }
    m_detail=path; m_status="diagExported"; emit changed();
    QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(path).absolutePath()));
}
void DiagnosticKit::openReports() { QDesktopServices::openUrl(QUrl::fromLocalFile(m_base+"/registros")); }
