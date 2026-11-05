#pragma once
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStringList>
#include <algorithm>
#include <QMap>
#include <vector>

namespace SessionDiagnostics {
// Summarize bounded, already-redacted collector output; never inspect game files.
inline bool writeSummary(const QString &dir)
{
    auto read = [&](const QString &name, qint64 limit) {
        QFile f(dir + '/' + name);
        return !QFileInfo(f).isSymLink() && f.open(QIODevice::ReadOnly) && f.size() <= limit ? f.readAll() : QByteArray();
    };
    const auto meta = QJsonDocument::fromJson(read("session.json", 1024 * 1024)).object();
    if (meta.value("schema").toInt() != 1) return false;
    const bool detailed = meta.value("runtime_environment").toObject().value("GOW_PERF_DIAG").toString() == "1";
    double duration = 0, fpsSum = 0, minFps = 1e9, cpu = 0, freeRam = 1e30, privatePeak = 0;
    double lastPerf = 0, lastFrame = 0, over100 = 0, missBlocks = 0, unsupported = 0, audioMissing = 0;
    int windows = 0, cpuSamples = 0, batterySamples = 0, invalid = 0;
    bool nativeSeen=false, jitSeen=false, audioSeen=false, frameSeen=false;
    std::vector<double> p95;
    QJsonObject queues, scopes;
    const auto data = read("metrics.jsonl", 4 * 1024 * 1024);
    for (const auto &line : data.split('\n')) {
        if (line.trimmed().isEmpty()) continue;
        const auto r = QJsonDocument::fromJson(line).object();
        if (r.isEmpty()) { ++invalid; continue; }
        const auto v = r.value("values").toObject();
        const auto tag = r.value("tag").toString();
        const double elapsed = r.value("elapsed_ms").toDouble(), window = v.value("window").toDouble();
        const bool warm = window > 0 && elapsed - window * 1000 >= 30000;
        if (tag == "gow-perf") {
            lastPerf = elapsed;
            if (warm && v.contains("guest_flip_hz")) {
                const double fps = v.value("guest_flip_hz").toDouble();
                fpsSum += fps * window; duration += window; minFps = std::min(minFps, fps); ++windows;
                if (r.value("timing_scopes_enabled").toBool())
                    for (const QString &k : {"ee_ms", "vu_ms", "gs_ms", "iop_ms", "guest_wait_ms", "host_wait_ms"})
                        if (v.contains(k)) scopes[k] = scopes.value(k).toDouble() + v.value(k).toDouble();
            }
        }
        if (tag == "gow-frame") {
            lastFrame = elapsed;
            if (warm) { frameSeen=true; if (v.contains("p95_ms")) p95.push_back(v.value("p95_ms").toDouble()); over100 += v.value("over_100").toDouble(); }
        }
        if (tag == "gow-queue" && v.contains("waits")) {
            const QString id = QString::number(v.value("queue").toInt());
            auto q = queues.value(id).toObject();
            for (const QString &k : {"waits", "wait_ms"}) q[k] = q.value(k).toDouble() + v.value(k).toDouble();
            for (const QString &k : {"max_ms", "queued_peak"}) q[k] = std::max(q.value(k).toDouble(), v.value(k).toDouble());
            queues[id] = q;
        }
        if (tag == "vu1n" && v.contains("missBlocks")) { nativeSeen=true; missBlocks += v.value("missBlocks").toDouble(); }
        if (tag == "vu1x" && v.contains("unsupported")) { jitSeen=true; unsupported = std::max(unsupported, v.value("unsupported").toDouble()); }
        if (tag == "audio-stats" && v.contains("missing")) { audioSeen=true; audioMissing += v.value("missing").toDouble(); }
        if (r.value("type").toString() == "host_process" && r.value("process_running").toBool()) {
            if (r.value("ac_line_status").toInt(-1) == 0) ++batterySamples;
            if (r.contains("system_available_ram_bytes")) freeRam = std::min(freeRam, r.value("system_available_ram_bytes").toDouble());
            privatePeak = std::max(privatePeak, r.value("private_bytes").toDouble());
            if (elapsed >= 30000 && r.contains("cpu_percent_one_core")) { cpu += r.value("cpu_percent_one_core").toDouble(); ++cpuSamples; }
        }
    }
    QStringList flags;
    if (windows < 3) flags << "insufficient_fps_windows";
    if (lastFrame > lastPerf + 15000) flags << "fps_reporting_gap";
    if (meta.value("collection_truncated").toBool() || invalid || data.isEmpty()) flags << "incomplete_collection";
    if (meta.value("write_failure").toBool()) flags << "collection_write_failure";
    if (meta.value("state").toString() != "completed") flags << "session_not_completed";
    if (batterySamples) flags << "battery_power_observed";
    if (freeRam < 1024.0 * 1024 * 1024) flags << "low_available_ram_observed";
    if (duration && fpsSum / duration < 59) flags << "below_60_fps";
    if (over100) flags << "long_guest_intervals";
    if (missBlocks) flags << "native_block_misses";
    if (unsupported) flags << "unsupported_jit_blocks";
    if (audioMissing) flags << "audio_missing_frames";
    QJsonObject out{{"schema", 1}, {"warmup_seconds", 30}, {"detailed_timing", detailed}, {"fps_windows", windows},
        {"measured_seconds", duration}, {"flags", QJsonArray::fromStringList(flags)}, {"queues_whole_session", queues},
        {"scoped_ms_after_warmup", scopes}, {"battery_samples", batterySamples}};
    if(nativeSeen) out["native_miss_blocks"]=missBlocks;
    if(jitSeen) out["jit_unsupported_max_counter"]=unsupported;
    if(audioSeen) out["audio_missing_frames"]=audioMissing;
    if(frameSeen) out["guest_intervals_over_100ms"]=over100;
    if (duration) { out["guest_fps_mean"] = fpsSum / duration; out["guest_fps_min_window"] = minFps; }
    if (cpuSamples) out["cpu_percent_one_core_sample_mean"] = cpu / cpuSamples;
    if (freeRam < 1e30) out["minimum_available_ram_bytes"] = freeRam;
    if (privatePeak) out["private_bytes_peak_sample"] = privatePeak;
    if (!p95.empty()) { std::sort(p95.begin(), p95.end()); out["median_window_p95_ms"] = (p95[(p95.size()-1)/2] + p95[p95.size()/2]) / 2; }
    const QMap<QString,QString> descriptions{
        {"insufficient_fps_windows","Poucas janelas de FPS: jogue por pelo menos dois minutos."},
        {"fps_reporting_gap","O contador de FPS parou enquanto outros quadros eram registrados."},
        {"incomplete_collection","Coleta ausente, truncada ou com linhas inválidas."},
        {"collection_write_failure","Falha ao gravar o relatório."},
        {"session_not_completed","Sessão ainda aberta ou encerrada com erro; confira session.json."},
        {"battery_power_observed","Uso na bateria detectado."},
        {"low_available_ram_observed","Menos de 1 GiB de RAM disponível em alguma amostra."},
        {"below_60_fps","Média inferior a 59 FPS no trecho medido."},
        {"long_guest_intervals","Intervalos do jogo acima de 100 ms."},
        {"native_block_misses","Entradas VU1 sem código nativo registrado."},
        {"unsupported_jit_blocks","Blocos não suportados pelo JIT."},
        {"audio_missing_frames","Faltaram amostras de áudio."}};
    QStringList observations;
    for(const auto &flag:flags) observations << descriptions.value(flag,flag);
    QString text = QStringLiteral("GOD OF WAR — RESUMO DO TESTE\n\nModo: %1\nEstado: %2\nCPU: %3\nGPU do contexto GS: %4\n\n")
        .arg(detailed ? QStringLiteral("detalhado (altera o desempenho; não é benchmark)") : QStringLiteral("leve (FPS)"),
             meta.value("state").toString(), meta.value("cpu").toString(), meta.value("gs_renderer").toString("não identificada"));
    text += QStringLiteral("Janelas completas após 30 s: %1 (%2 s)\n").arg(windows).arg(duration, 0, 'f', 1);
    if (duration) text += QStringLiteral("FPS médio: %1 | menor janela: %2\n").arg(fpsSum/duration, 0, 'f', 2).arg(minFps, 0, 'f', 2);
    if (!p95.empty()) text += QStringLiteral("Mediana do p95 por janela: %1 ms (intervalos do jogo, não latência da tela)\n").arg(out["median_window_p95_ms"].toDouble(), 0, 'f', 2);
    if (cpuSamples) text += QStringLiteral("CPU média amostrada: %1%% (um processador lógico = 100%%)\n").arg(cpu/cpuSamples, 0, 'f', 1).replace("%%", "%");
    if (freeRam < 1e30) text += QStringLiteral("Menor RAM disponível: %1 MiB\n").arg(freeRam / 1048576, 0, 'f', 0);
    text += QStringLiteral("Amostras na bateria: %1\nIntervalos acima de 100 ms: %2\n\nObservações: %3\n")
        .arg(batterySamples).arg(frameSeen ? QString::number(over100) : QString::fromUtf8("indispon\u00edvel")).arg(observations.isEmpty() ? QString::fromUtf8("nenhum alerta autom\u00e1tico") : observations.join("\n"));
    for (auto it = queues.begin(); it != queues.end(); ++it) {
        const auto q = it.value().toObject();
        text += QStringLiteral("Fila %1: espera total %2 ms; maior espera %3 ms\n").arg(it.key()).arg(q["wait_ms"].toDouble(), 0, 'f', 2).arg(q["max_ms"].toDouble(), 0, 'f', 2);
    }
    text += QStringLiteral("\nFila 1: VU1 → GS; fila 2: backend GS. Tempos de espera incluem escalonamento.\n"
        "Tempos VU/GS e filas podem se sobrepor: não some como tempo de quadro ou de GPU.\n"
        "Ausência de uma métrica significa indisponível, não zero. Alertas são indícios, não causas confirmadas.\n"
        "Compare a mesma cena, máquina, modo e configuração. Marque a queda e exporte o ZIP completo.\n"
        "O ZIP não inclui ISO, arquivos do jogo ou cartões de memória.\n");
    auto save = [&](const QString &name, const QByteArray &bytes) { QSaveFile f(dir+'/'+name); if(QFileInfo(f).isSymLink()) return false; return f.open(QIODevice::WriteOnly) && f.write(bytes) == bytes.size() && f.commit(); };
    return save("summary.json", QJsonDocument(out).toJson()) && save("RESUMO.txt", text.toUtf8());
}
}
