#include "regional_installations.h"
#include <QTemporaryDir>
#include <stdexcept>
#include <iostream>

static void require(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
static void write(const QString &path, const QByteArray &bytes) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile file(path);
    require(file.open(QIODevice::WriteOnly | QIODevice::Truncate), "create fixture");
    require(file.write(bytes) == bytes.size(), "write fixture");
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
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
        for (const auto *key : {"runner_sha256", "elf_sha256", "source", "framePc"}) {
            auto broken = row; broken[key] = "wrong"; bad = manifest; bad["builds"] = QJsonArray{broken}; publish(bad);
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
