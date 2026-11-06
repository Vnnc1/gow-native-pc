#include "regional_installations.h"
#include <QTemporaryDir>
#include <stdexcept>
#include <iostream>

static QStringList warnings;
static void require(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
static void write(const QString &path, const QByteArray &bytes) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile file(path);
    require(file.open(QIODevice::WriteOnly | QIODevice::Truncate), "create fixture");
    require(file.write(bytes) == bytes.size(), "write fixture");
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler([](QtMsgType type, const QMessageLogContext &, const QString &message) {
        if (type == QtWarningMsg && message.contains("regional build")) warnings << message;
    });
    try {
        QTemporaryDir temporary;
        require(temporary.isValid(), "temporary directory");
        const auto root = temporary.path();
        const auto runner = root + "/build/ps2xRuntime/game.exe";
        const auto elf = root + "/region/disc/ELF";
        const auto profile = root + "/games/gow1/game.toml";
        write(runner, "runner"); write(elf, "elf"); write(profile, "profile");
        write(root + "/region/disc/.disc_layout", "layout");
        write(root + "/build/CMakeCache.txt", "CMAKE_HOME_DIRECTORY:INTERNAL=" + (root + "/source").toUtf8() + '\n');
        QJsonObject row{{"region", "fixture"}, {"runner", runner}, {"elf", elf}, {"dataDir", root + "/region"},
            {"source", root + "/source"}, {"framePc", "0x1838a8"},
            {"runner_sha256", RegionalInstallations::sha256(runner)}, {"elf_sha256", RegionalInstallations::sha256(elf)}};
        QJsonObject manifest{{"schema", 1}, {"owner", root}, {"profile_sha256", RegionalInstallations::sha256(profile)},
            {"builds", QJsonArray{row}}};
        const auto publish = [&](const QJsonObject &data) { write(root + "/data/gow1/regional-builds.json", QJsonDocument(data).toJson()); };
        publish(manifest);
        auto entries = RegionalInstallations::read(root);
        require(entries.size() == 1, "valid installation accepted");
        require(entries[0].toMap().value("language") == "region:fixture", "unique selection identity");
        require(entries[0].toMap().value("card") == root + "/region/Mcd001.ps2", "private regional card");
        auto bad = manifest; bad["owner"] = root + "/other"; publish(bad);
        require(RegionalInstallations::read(root).isEmpty(), "foreign checkout rejected");
        bad = manifest; bad["profile_sha256"] = "wrong"; publish(bad);
        require(RegionalInstallations::read(root).isEmpty(), "stale profile rejected");
        // A stale fingerprint is the case that looked like "the launcher lost my game": it must say so, name the
        // region, and stay out of the way enough to hide no paths or hashes.
        warnings.clear();
        const QString forged = QString(64, QLatin1Char('0'));
        auto broken = row; broken["runner_sha256"] = forged;
        bad = manifest; bad["builds"] = QJsonArray{broken}; publish(bad);
        require(RegionalInstallations::read(root).isEmpty(), "mismatched runner rejected");
        const auto diagnostic = warnings.join("\n");
        require(diagnostic.contains("fingerprint mismatch"), "fingerprint mismatch explained");
        require(diagnostic.contains("fixture"), "diagnostic names the region");
        require(!diagnostic.contains(runner) && !diagnostic.contains(forged), "diagnostic hides paths and hashes");
        QFile logFile(root + "/data/gow1/logs/launcher.log");
        require(logFile.open(QIODevice::ReadOnly), "diagnostic log created");
        const auto logged = QString::fromUtf8(logFile.readAll());
        require(logged.contains("fingerprint mismatch") && !logged.contains(runner), "diagnostic logged without paths");
        require(RegionalInstallations::read(root).isEmpty(), "repeat read still rejected");
        const auto loggedAgain = [&] { QFile again(root + "/data/gow1/logs/launcher.log");
            return again.open(QIODevice::ReadOnly) ? QString::fromUtf8(again.readAll()) : QString(); }();
        require(loggedAgain.count("fingerprint mismatch") == 1, "diagnostic not repeated");
        for (const auto *key : {"source", "framePc"}) {
            auto other = row; other[key] = "wrong"; bad = manifest; bad["builds"] = QJsonArray{other}; publish(bad);
            require(RegionalInstallations::read(root).isEmpty(), "mismatched build rejected");
        }
        bad = manifest; bad["builds"] = QJsonArray{row, row}; publish(bad);
        require(RegionalInstallations::read(root).size() == 1, "duplicate selection removed");
        publish(manifest); write(runner, "changed runner");
        require(RegionalInstallations::read(root).isEmpty(), "binary modification invalidates cached hash");
        write(runner, "runner"); write(elf, "changed elf");
        require(RegionalInstallations::read(root).isEmpty(), "wrong ELF rejected");
        std::cout << "PASS: regional selection, ownership, hashes, saves and cache invalidation\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
