#include "session_diagnostics.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSettings>
#include <QSysInfo>
#include <QThread>
#include <QTimer>
#include <QUuid>
#include <QtEndian>
#include <algorithm>
#include <array>
#ifdef Q_OS_WIN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#endif

namespace {
constexpr qint64 logLimit = 4 * 1024 * 1024;
const QStringList reportFiles{"session.json", "startup.log", "runtime.log", "runtime.1.log", "runtime.2.log",
                              "metrics.jsonl", "events.jsonl"};
QString utc() { return QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs); }
bool saveJson(const QString &path, const QJsonObject &obj)
{
    QSaveFile file(path);
    const auto bytes = QJsonDocument(obj).toJson();
    return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.commit();
}
QJsonObject readJson(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 1024 * 1024) return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}
QString sha(const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return {};
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (!hash.addData(&file)) return {};
    return QString::fromLatin1(hash.result().toHex());
}
bool validSession(const QString &path)
{
    return !QFileInfo(path).isSymLink() && readJson(path + "/session.json").value("schema").toInt() == 1;
}
QString redact(QString text, const QStringList &paths)
{
    for (const auto &path : paths) {
        if (path.size() < 4) continue;
        text.replace(QDir::toNativeSeparators(path), "<path>", Qt::CaseInsensitive);
        text.replace(QDir::fromNativeSeparators(path), "<path>", Qt::CaseInsensitive);
    }
    static const QRegularExpression profile(R"((?:[A-Za-z]:[/\\](?:Users|Documents and Settings)[/\\])[^/\\\s"']+)", QRegularExpression::CaseInsensitiveOption);
    static const QRegularExpression email(R"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})");
    text.replace(profile, "<user>");
    text.replace(email, "<email>");
    return text;
}
quint32 crc32(const QByteArray &data)
{
    static const auto table = [] {
        std::array<quint32, 256> t{};
        for (quint32 i = 0; i < 256; ++i) {
            quint32 c = i;
            for (int j = 0; j < 8; ++j) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
            t[i] = c;
        }
        return t;
    }();
    quint32 crc = ~0u;
    for (const auto c : data) crc = table[(crc ^ static_cast<unsigned char>(c)) & 255] ^ (crc >> 8);
    return ~crc;
}
void u16(QByteArray &b, quint16 n) { n = qToLittleEndian(n); b.append(reinterpret_cast<const char *>(&n), 2); }
void u32(QByteArray &b, quint32 n) { n = qToLittleEndian(n); b.append(reinterpret_cast<const char *>(&n), 4); }

class Recorder : public QObject {
public:
    QString dir;
    QStringList paths;
    QJsonObject meta;
    QProcess game;
    QTimer timer;
    QElapsedTimer clock;
    QByteArray pending;
    QFile runtime, startup, metrics, events;
    qint64 lastOutput = 0, lastSample = 0;
    quint64 previousCpu = 0, warningLines = 0, rotations = 0;
    bool stopping = false, done = false, writeFailure = false;
    int result = 1;
#ifdef Q_OS_WIN
    HANDLE handle = nullptr;
    ~Recorder() override { if (handle) CloseHandle(handle); }
#endif
    explicit Recorder(const QString &directory) : dir(directory), runtime(dir + "/runtime.log"),
        startup(dir + "/startup.log"), metrics(dir + "/metrics.jsonl"), events(dir + "/events.jsonl") {}
    void append(QFile &file, const QByteArray &data, qint64 limit)
    {
        if (!file.isOpen() || file.size() + data.size() > limit) {
            meta["collection_truncated"] = true;
            return;
        }
        if (file.write(data) != data.size()) writeFailure = true;
    }
    void event(QJsonObject entry)
    {
        entry["utc"] = utc(); entry["elapsed_ms"] = clock.elapsed();
        append(events, QJsonDocument(entry).toJson(QJsonDocument::Compact) + '\n', 1024 * 1024);
        events.flush();
    }
    void persist()
    {
        meta["last_heartbeat_utc"] = utc(); meta["elapsed_ms"] = clock.elapsed();
        meta["warning_candidate_lines"] = static_cast<qint64>(warningLines);
        meta["log_rotations"] = static_cast<qint64>(rotations);
        meta["write_failure"] = writeFailure;
        if (!saveJson(dir + "/session.json", meta)) writeFailure = true;
    }
    void line(const QByteArray &bytes)
    {
        QString text = redact(QString::fromUtf8(bytes).trimmed(), paths);
        if (text.isEmpty()) return;
        lastOutput = clock.elapsed();
        const auto output = (QString("[%1 ms] ").arg(lastOutput) + text + '\n').toUtf8();
        if (runtime.size() + output.size() > logLimit) {
            runtime.close();
            QFile::remove(dir + "/runtime.2.log");
            QFile::rename(dir + "/runtime.1.log", dir + "/runtime.2.log");
            QFile::rename(dir + "/runtime.log", dir + "/runtime.1.log");
            if (!runtime.open(QIODevice::WriteOnly | QIODevice::Truncate)) writeFailure = true;
            ++rotations;
        }
        append(runtime, output, logLimit);
        if (startup.size() + output.size() <= 256 * 1024) append(startup, output, 256 * 1024);
        // Candidate text is evidence, not a diagnosis: e.g. "0 errors" can match.
        static const QRegularExpression warning("\\b(error|fatal|failed|exception|mismatch|underrun|unsupported)\\b", QRegularExpression::CaseInsensitiveOption);
        if (text.contains(warning)) {
            ++warningLines;
            if (warningLines <= 1000) event({{"type", "runtime_warning_candidate"}, {"text", text.left(2048)}});
        }
        static const QRegularExpression tag(R"(^\[(gow-perf|gow-frame|gow-sync|gow-sync-config|audio-stats|iop-drift|vu1n|vu1x|gow-audio[^\]]*|gow-iop[^\]]*|gow-vu1[^\]]*|gow-snd[^\]]*)\])");
        const auto match = tag.match(text);
        if (match.hasMatch()) {
            QJsonObject sample{{"type", "runtime"}, {"tag", match.captured(1)}, {"elapsed_ms", lastOutput}};
            static const QRegularExpression number(R"(([A-Za-z_][A-Za-z_0-9]*)(<=|=)(-?[0-9]+(?:\.[0-9]+)?))");
            auto numbers = number.globalMatch(text);
            QJsonObject values;
            while (numbers.hasNext()) { const auto n = numbers.next(); values[n.captured(1) + (n.captured(2) == "<=" ? "_max" : "")] = n.captured(3).toDouble(); }
            const auto levels = QRegularExpression("level=([0-9]+)-([0-9]+)").match(text);
            if (levels.hasMatch()) { values.remove("level"); values["level_min"] = levels.captured(1).toDouble(); values["level_max"] = levels.captured(2).toDouble(); }
            if (match.captured(1) == "gow-perf") {
                const bool scopes = qEnvironmentVariable("GOW_PERF_DIAG") == "1";
                sample["timing_scopes_enabled"] = scopes;
                if (!scopes) for (const QString &key : {"ee_ms", "vu_ms", "gs_ms", "iop_ms", "guest_wait_ms", "upload_ms", "host_wait_ms"}) values.remove(key);
            }
            if (match.captured(1) == "audio-stats" && values.value("missing").toDouble() > 0)
                event({{"type", "audio_missing_frames"}, {"missing", values["missing"]}, {"requested", values["requested"]}});
            QJsonObject observations = meta.value("observations").toObject();
            if (match.captured(1) == "gow-perf" && values.contains("guest_flip_hz")) {
                const double fps = values.value("guest_flip_hz").toDouble();
                observations["guest_fps_min_window"] = std::min(fps, observations.value("guest_fps_min_window").toDouble(fps));
                observations["guest_fps_max_window"] = std::max(fps, observations.value("guest_fps_max_window").toDouble(fps));
                observations["guest_fps_windows"] = observations.value("guest_fps_windows").toInt() + 1;
            }
            if (match.captured(1) == "gow-frame") {
                observations["guest_interval_max_ms"] = std::max(values.value("max_ms").toDouble(), observations.value("guest_interval_max_ms").toDouble());
                observations["guest_intervals_over_100ms"] = observations.value("guest_intervals_over_100ms").toDouble() + values.value("over_100").toDouble();
                if (values.value("over_100").toDouble() > 0) event({{"type", "long_guest_interval_window"}, {"max_ms", values["max_ms"]}, {"over_100", values["over_100"]}});
            }
            if (match.captured(1) == "audio-stats") {
                observations["audio_missing_frames"] = observations.value("audio_missing_frames").toDouble() + values.value("missing").toDouble();
                observations["audio_dropped_frames"] = observations.value("audio_dropped_frames").toDouble() + values.value("dropped").toDouble();
            }
            if (values.contains("missBlocks")) observations["native_missBlocks_max_counter"] = std::max(values.value("missBlocks").toDouble(), observations.value("native_missBlocks_max_counter").toDouble());
            meta["observations"] = observations;
            meta["observations_scope"] = "All observed windows, including startup/loading; not a controlled gameplay benchmark.";
            sample["values"] = values;
            append(metrics, QJsonDocument(sample).toJson(QJsonDocument::Compact) + '\n', logLimit);
        }
    }
    void drain(bool final = false)
    {
        while (game.bytesAvailable() > 0) {
            pending += game.read(16384);
            qsizetype newline;
            while ((newline = pending.indexOf('\n')) >= 0) {
                line(pending.left(newline)); pending.remove(0, newline + 1);
            }
            if (pending.size() > 32768) { line(pending.left(32768) + " [line truncated]"); pending.clear(); }
        }
        if (final && !pending.isEmpty()) { line(pending); pending.clear(); }
        runtime.flush(); startup.flush(); metrics.flush();
    }
    void sample()
    {
        const qint64 now = clock.elapsed();
        QJsonObject values{{"type", "host_process"}, {"elapsed_ms", now}, {"runtime_output_age_ms", now - lastOutput}, {"process_running", game.state() == QProcess::Running}};
#ifdef Q_OS_WIN
        if (!handle && game.processId()) handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, DWORD(game.processId()));
        values["process_counters_available"] = handle != nullptr;
        if (handle) {
            PROCESS_MEMORY_COUNTERS_EX mem{}; mem.cb = sizeof(mem);
            if (GetProcessMemoryInfo(handle, reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&mem), sizeof(mem))) {
                values["working_set_bytes"] = qint64(mem.WorkingSetSize);
                values["peak_working_set_bytes"] = qint64(mem.PeakWorkingSetSize);
                values["private_bytes"] = qint64(mem.PrivateUsage);
                values["page_fault_count"] = qint64(mem.PageFaultCount);
            }
            FILETIME created{}, ended{}, kernel{}, user{};
            if (GetProcessTimes(handle, &created, &ended, &kernel, &user)) {
                const auto ticks = [](FILETIME t) { return (quint64(t.dwHighDateTime) << 32) | t.dwLowDateTime; };
                const quint64 cpu = ticks(kernel) + ticks(user);
                if (lastSample && now > lastSample) values["cpu_percent_one_core"] = double(cpu - previousCpu) / double(now - lastSample) / 100.0;
                previousCpu = cpu;
            }
            IO_COUNTERS io{};
            if (GetProcessIoCounters(handle, &io)) {
                values["io_read_bytes_total"] = qint64(io.ReadTransferCount);
                values["io_write_bytes_total"] = qint64(io.WriteTransferCount);
            }
        }
        MEMORYSTATUSEX memory{}; memory.dwLength = sizeof(memory);
        if (GlobalMemoryStatusEx(&memory)) values["system_available_ram_bytes"] = qint64(memory.ullAvailPhys);
        SYSTEM_POWER_STATUS power{};
        if (GetSystemPowerStatus(&power)) { values["ac_line_status"] = int(power.ACLineStatus); values["battery_percent"] = int(power.BatteryLifePercent); }
#endif
        lastSample = now;
        append(metrics, QJsonDocument(values).toJson(QJsonDocument::Compact) + '\n', logLimit);
        metrics.flush(); persist();
    }
    void finish(int code, QProcess::ExitStatus status, const QString &state = {})
    {
        if (done) return;
        done = true; timer.stop(); drain(true); sample();
        meta["state"] = state.isEmpty() ? (status == QProcess::CrashExit ? "crashed" : code == 0 ? "completed" : "nonzero_exit") : state;
        meta["exit_code"] = code; meta["exit_code_hex"] = QString::number(quint32(code), 16);
        meta["stop_requested"] = stopping; meta["ended_utc"] = utc();
        event({{"type", "process_exit"}, {"code", code}, {"state", meta["state"]}}); persist();
        result = status == QProcess::NormalExit && code == 0 && state.isEmpty() ? 0 : 1;
        QCoreApplication::exit(result);
    }
};
}

QString SessionDiagnostics::create(const QString &base, const QVariantMap &settings)
{
    const QString id = QDateTime::currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz") + "-" + QUuid::createUuid().toString(QUuid::Id128).left(8);
    const QString dir = base + "/sessions/" + id;
    if (!QDir().mkpath(dir)) return {};
    QJsonObject selected;
    // Explicit settings allowlist excludes ISO/save paths, key bindings and other personal fields.
    for (const QString &key : {"diagnostics", "framePc", "gpu", "modoPantalla", "ancho", "alto", "escala",
                               "aspecto", "fxaa", "vsync", "fpsLimite", "filtro", "anisotropico",
                               "jitInline", "finAnticipado", "idioma", "saltarVideos", "arranqueRapido"})
        if (settings.contains(key)) selected[key] = QJsonValue::fromVariant(settings.value(key));
    if (!saveJson(dir + "/session.json", {{"schema", 1}, {"id", id}, {"created_utc", utc()}, {"state", "prepared"}, {"settings", selected}})) return {};
    if (!saveJson(base + "/latest.json", {{"id", id}})) return {};
    // Retain ten completed, owned sessions. Never prune active/interrupted evidence automatically.
    QDir sessions(base + "/sessions");
    const auto entries = sessions.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot | QDir::NoSymLinks, QDir::Name | QDir::Reversed);
    int completed = 0;
    for (const auto &entry : entries) {
        const auto metadata = readJson(entry.filePath() + "/session.json");
        const auto state = metadata.value("state").toString();
        if (metadata.value("schema").toInt() != 1 || (state != "completed" && state != "crashed" && state != "nonzero_exit" && state != "failed_to_start")) continue;
        if (++completed <= 10) continue;
        // Delete only known report files, then an empty owned directory; no recursive traversal.
        for (const auto &name : reportFiles) QFile::remove(entry.filePath() + '/' + name);
        sessions.rmdir(entry.fileName());
    }
    return dir;
}
QString SessionDiagnostics::latest(const QString &base)
{
    const auto id = readJson(base + "/latest.json").value("id").toString();
    static const QRegularExpression format("^[0-9]{8}-[0-9]{6}-[0-9]{3}-[a-f0-9]{8}$");
    const QString path = base + "/sessions/" + id;
    return format.match(id).hasMatch() && validSession(path) ? path : QString();
}
bool SessionDiagnostics::mark(const QString &session, const QString &note)
{
    if (!validSession(session)) return false;
    return saveJson(session + "/marker.request", {{"note", note.left(1000)}, {"requested_utc", utc()}});
}

QString SessionDiagnostics::exportZip(const QString &session, QString *error)
{
    const auto fail = [&](const QString &message) { if (error) *error = message; return QString(); };
    if (!validSession(session)) return fail("No recorded session is available.");
    const QString out = QFileInfo(session).absolutePath() + "/report-" + QFileInfo(session).fileName() + '-' + QUuid::createUuid().toString(QUuid::Id128).left(8) + ".zip";
    QSaveFile zip(out);
    if (!zip.open(QIODevice::WriteOnly)) return fail(zip.errorString());
    QByteArray central;
    quint16 count = 0;
    auto entry = [&](const QByteArray &name, const QByteArray &data) {
        const quint32 offset = quint32(zip.pos()), crc = crc32(data), size = quint32(data.size());
        QByteArray header;
        u32(header, 0x04034b50); u16(header, 20); u16(header, 0); u16(header, 0); u16(header, 0); u16(header, 33);
        u32(header, crc); u32(header, size); u32(header, size); u16(header, quint16(name.size())); u16(header, 0); header += name;
        if (zip.write(header) != header.size() || zip.write(data) != data.size()) return false;
        u32(central, 0x02014b50); u16(central, 20); u16(central, 20); u16(central, 0); u16(central, 0); u16(central, 0); u16(central, 33);
        u32(central, crc); u32(central, size); u32(central, size); u16(central, quint16(name.size()));
        u16(central, 0); u16(central, 0); u16(central, 0); u16(central, 0); u32(central, 0); u32(central, offset); central += name; ++count;
        return true;
    };
    for (const auto &name : reportFiles) {
        QFile file(session + '/' + name);
        if (!file.exists()) continue;
        if (QFileInfo(file).isSymLink() || !file.open(QIODevice::ReadOnly) || file.size() > logLimit) return fail("Invalid or oversized report file: " + name);
        if (!entry(name.toUtf8(), file.read(logLimit))) return fail(zip.errorString());
    }
    const QByteArray readme = "Local diagnostic snapshot. No automatic upload. Review before sharing: redaction is best effort.\n"
        "Attach this ZIP to a project bug report with the area/save point, steps, expected/observed behavior and approximate marker time.\n"
        "Do not attach your ISO, extracted game files, saves or credentials. Screenshots are optional and must be chosen separately.\n"
        "Runtime metrics are five-second windows; guest frame intervals are not display presentation latency.\n"
        "CPU percent uses one core = 100%; silence alone is not a hang. Warning candidates are not confirmed errors.\n"
        "A running state is a live snapshot or an interrupted monitor; check last_heartbeat_utc. Missing counters mean unavailable, not zero.\n"
        "Rotated logs retain the newest 12 MiB plus startup; capped metrics/events can be truncated (see session.json).\n";
    if (!entry("README.txt", readme)) return fail(zip.errorString());
    const quint32 start = quint32(zip.pos());
    if (zip.write(central) != central.size()) return fail(zip.errorString());
    QByteArray end;
    u32(end, 0x06054b50); u16(end, 0); u16(end, 0); u16(end, count); u16(end, count); u32(end, quint32(central.size())); u32(end, start); u16(end, 0);
    if (zip.write(end) != end.size() || !zip.commit()) return fail(zip.errorString());
    return out;
}

int SessionDiagnostics::run(const QStringList &args)
{
    if (args.size() == 3 && args[0] == "--export") {
        QString error; const auto output = exportZip(args[1], &error);
        if (output.isEmpty()) return 2;
        return QFile::copy(output, args[2]) ? (QFile::remove(output), 0) : 3;
    }
    if (args.size() != 4 || !validSession(args[0])) return 2;
    // Arguments: an owned session directory, runner, ELF and repository root. No shell is involved.
    Recorder r(args[0]);
    r.meta = readJson(r.dir + "/session.json");
    r.paths = {QDir::homePath(), QFileInfo(args[2]).absolutePath(), args[2], QFileInfo(args[1]).absolutePath(), args[3], QDir::tempPath()};
    std::sort(r.paths.begin(), r.paths.end(), [](const auto &a, const auto &b) { return a.size() > b.size(); });
    for (auto *file : {&r.runtime, &r.startup, &r.metrics, &r.events}) if (!file->open(QIODevice::WriteOnly | QIODevice::Truncate)) return 3;
    r.clock.start(); r.meta["state"] = "starting"; r.meta["launcher_version"] = QCoreApplication::applicationVersion();
    r.meta["os"] = QSysInfo::prettyProductName(); r.meta["kernel"] = QSysInfo::kernelVersion();
    r.meta["architecture"] = QSysInfo::currentCpuArchitecture(); r.meta["logical_cpus"] = QThread::idealThreadCount();
    r.meta["runner_sha256"] = sha(args[1]); r.meta["elf_sha256"] = sha(args[2]);
    r.meta["runtime_pin_sha256"] = sha(args[3] + "/engine/runtime.toml");
    r.meta["toolchain_manifest_sha256"] = sha(args[3] + "/tools/pipeline/toolchains.json");
    QFile pin(args[3] + "/engine/runtime.toml");
    if (pin.open(QIODevice::ReadOnly)) {
        const auto match = QRegularExpression("(?m)^commit\\s*=\\s*\"([a-f0-9]+)\"").match(QString::fromUtf8(pin.read(16384)));
        if (match.hasMatch()) r.meta["runtime_commit"] = match.captured(1);
    }
    QFile cache(QFileInfo(args[1]).dir().absoluteFilePath("../CMakeCache.txt"));
    if (cache.open(QIODevice::ReadOnly)) {
        QJsonObject build;
        const QStringList allowed{"CMAKE_BUILD_TYPE", "CMAKE_CXX_FLAGS", "CMAKE_CXX_FLAGS_RELEASE", "PS2X_RELEASE_LTCG", "PS2X_RELEASE_PDB", "PS2X_PGO_MODE", "PS2X_CPU_ARCH"};
        for (const auto &line : QString::fromUtf8(cache.read(2 * 1024 * 1024)).split('\n')) {
            const auto colon = line.indexOf(':'); const auto equals = line.indexOf('=');
            if (colon > 0 && equals > colon && allowed.contains(line.left(colon))) build[line.left(colon)] = redact(line.mid(equals + 1).trimmed(), r.paths);
        }
        r.meta["build_cache_snapshot"] = build;
    }
    QJsonObject patches;
    const QDir patchDir(args[3] + "/engine/patches");
    for (const auto &file : patchDir.entryInfoList({"*.patch"}, QDir::Files, QDir::Name)) patches[file.fileName()] = sha(file.filePath());
    r.meta["source_patch_sha256"] = patches;
    r.meta["source_snapshot_note"] = "Source/configuration at launch; runner_sha256 identifies the actual executable. Local edits may not be built.";
    QJsonObject env;
    for (const char *name : {"GOW_PERF_DIAG", "GOW_FRAME_DIAG", "GOW_PERF_FRAME_PC", "GOW_AUDIO", "GOW_AUDIO_STATS", "GOW_IOP_DRIFT",
         "GOW_VU1N_DIAG", "GOW_VU1N_X64", "GOW_VU1X_INLINE", "GOW_DISPATCH_FULL", "GOW_GS_FINISH_ASINCRONO",
         "GOW_VU1_EARLY_FINISH", "GOW_GS_EARLY_FINISH", "GOW_SYNC_DIAG", "PS2X_GS_WORKER_DIAG", "PS2X_GS_PIPELINE",
         "PS2X_GS_WORKER", "PS2X_GS_HW_SCALE", "TOBIICHI_VSYNC", "TOBIICHI_VENTANA_FPS"})
        if (qEnvironmentVariableIsSet(name)) env[name] = redact(qEnvironmentVariable(name).left(128), r.paths);
    r.meta["runtime_environment"] = env;
#ifdef Q_OS_WIN
    QSettings cpu("HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0", QSettings::NativeFormat);
    r.meta["cpu"] = cpu.value("ProcessorNameString").toString().trimmed();
    MEMORYSTATUSEX memory{}; memory.dwLength = sizeof(memory);
    if (GlobalMemoryStatusEx(&memory)) r.meta["physical_ram_bytes"] = qint64(memory.ullTotalPhys);
    QJsonArray adapters;
    for (DWORD i = 0; i < 16; ++i) {
        DISPLAY_DEVICEW device{}; device.cb = sizeof(device);
        if (!EnumDisplayDevicesW(nullptr, i, &device, 0)) break;
        if (device.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER) continue;
        QJsonObject adapter{{"name", QString::fromWCharArray(device.DeviceString)}, {"attached", bool(device.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)}};
        QString key = QString::fromWCharArray(device.DeviceKey);
        if (key.startsWith("\\Registry\\Machine\\", Qt::CaseInsensitive)) {
            QSettings driver("HKEY_LOCAL_MACHINE\\" + key.mid(18), QSettings::NativeFormat);
            adapter["driver_version"] = driver.value("DriverVersion").toString();
        }
        adapters.append(adapter);
    }
    r.meta["display_adapters_not_selected_renderer"] = adapters;
#endif
    r.persist();
    r.game.setProgram(args[1]); r.game.setArguments({args[2]});
    r.game.setProcessChannelMode(QProcess::MergedChannels);
    QObject::connect(&r.game, &QProcess::readyReadStandardOutput, &r, [&] { r.drain(); });
    QObject::connect(&r.game, &QProcess::started, &r, [&] { r.meta["state"] = "running"; r.meta["started_utc"] = utc(); r.event({{"type", "process_started"}}); r.sample(); });
    QObject::connect(&r.game, &QProcess::finished, &r, [&](int code, QProcess::ExitStatus status) { r.finish(code, status); });
    QObject::connect(&r.game, &QProcess::errorOccurred, &r, [&](QProcess::ProcessError error) {
        r.event({{"type", "process_error"}, {"message", redact(r.game.errorString(), r.paths)}, {"code", int(error)}});
        if (error == QProcess::FailedToStart) r.finish(-1, QProcess::CrashExit, "failed_to_start");
    });
    QObject::connect(&r.timer, &QTimer::timeout, &r, [&] {
        const QString marker = r.dir + "/marker.request";
        if (QFile::exists(marker)) { auto e = readJson(marker); e["type"] = "player_marker"; e["note"] = redact(e.value("note").toString(), r.paths); r.event(e); QFile::remove(marker); }
        if (QFile::exists(r.dir + "/stop.request") && !r.stopping) {
            QFile::remove(r.dir + "/stop.request"); r.stopping = true; r.event({{"type", "stop_requested"}}); r.game.terminate();
            QTimer::singleShot(5000, &r.game, [&] { if (r.game.state() != QProcess::NotRunning) { r.event({{"type", "forced_termination"}}); r.game.kill(); } });
        }
        if (r.clock.elapsed() - r.lastSample >= 5000) r.sample();
    });
    r.timer.start(500); r.game.start();
    if (r.done) return r.result;
    QCoreApplication::exec();
    return r.result;
}
