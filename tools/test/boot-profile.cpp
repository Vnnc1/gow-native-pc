// gow-native.boot profiles: V2 (relative or absolute installation root) and the legacy V1 form, plus the missing disc the
// runtime refuses to start without. Parsing comes from the runtime's runtime/boot_profile.h, the same header main.cpp
// uses, so this runs without the runtime, a disc or a window.
#include "runtime/boot_profile.h"
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>

namespace fs = std::filesystem;

int main()
{
    using ps2x::boot::GuestElf;
    using ps2x::boot::Parse;
    using ps2x::boot::ResolvePath;

    int failures = 0;
    auto check = [&](bool ok, const char *what) { if (!ok) { std::fprintf(stderr, "FAIL: %s\n", what); ++failures; } };
    // generic_string() so a written "C:/..." and a native "C:\\..." path compare as the same location.
    auto same = [](const fs::path &a, const fs::path &b) { return a.generic_string() == b.generic_string(); };

    // A copy of an installation, the build folder beside it (where standalone launches start) and a player ISO elsewhere.
    std::error_code ignored;
    const auto base = fs::temp_directory_path() / "gow-boot-profile-test";
    fs::remove_all(base, ignored);
    const auto install = base / "games copy" / "God of War";
    const auto bootDir = base / "build" / "ps2xRuntime";
    const auto elf = install / "data/gow1/discs/usa/SCUS_973.99";
    const auto capture = install / "data/gow1/vu1_capture";
    const auto iso = base / "isos" / "God of War.iso";
    fs::create_directories(elf.parent_path());
    fs::create_directories(bootDir);
    fs::create_directories(iso.parent_path());
    std::ofstream(elf) << "elf";
    std::ofstream(iso) << "iso";
    const auto isoText = iso.generic_string();

    // V2 as the launcher writes it: the root relative to the profile's folder, so the text is location independent.
    const std::string relativeRoot = "../../games copy/God of War";
    const std::string v2 = "GOW_NATIVE_BOOT_V2\n" + relativeRoot + "\n@data/gow1/discs/usa/SCUS_973.99\n" +
                           "GOW_VU1_CAPTURA=@data/gow1/vu1_capture\nGOW_ISO=" + isoText +
                           "\nPS2X_GS_WORKER=1\nNOISE=ignored\n";
    const auto relative = Parse(v2);
    check(relative.has_value(), "a V2 profile parses");
    check(relative && !relative->legacy && same(relative->root, ps2x::boot::Utf8Path(relativeRoot)), "V2 keeps its recorded root");
    check(relative && relative->settings.size() == 3, "only TOBIICHI_/PS2X_/GOW_ settings are kept");
    check(relative && relative->settings[0].key == "GOW_VU1_CAPTURA" && relative->settings[1].key == "GOW_ISO" &&
              relative->settings[2].key == "PS2X_GS_WORKER", "settings keep their file order");
    const auto disc = relative ? GuestElf(*relative, bootDir) : std::optional<fs::path>();
    check(disc && same(*disc, elf), "a relative root finds the disc beside the profile");
    check(relative && same(ResolvePath(*relative, bootDir, relative->settings[0].value), capture),
          "an '@' setting resolves inside the installation");
    check(relative && same(ResolvePath(*relative, bootDir, relative->settings[1].value), iso),
          "a path outside the installation stays as written");
    check(relative && !ps2x::boot::IsRelativeValue(relative->settings[2].value), "a plain value is not a path");

    // V2 with an absolute root, as written when the two sides are on different drives; CRLF from a hand-edited file.
    const std::string absoluteV2 = "GOW_NATIVE_BOOT_V2\r\n" + install.generic_string() +
                                   "\r\n@data/gow1/discs/usa/SCUS_973.99\r\nGOW_VU1_CAPTURA=@data/gow1/vu1_capture\r\n";
    const auto absolute = Parse(absoluteV2);
    check(absolute.has_value(), "a V2 profile with an absolute root parses");
    check(absolute && same(absolute->root, install) && absolute->elf == "@data/gow1/discs/usa/SCUS_973.99",
          "CRLF and an absolute root keep the recorded values");
    const auto absoluteDisc = absolute ? GuestElf(*absolute, bootDir) : std::optional<fs::path>();
    check(absoluteDisc && same(*absoluteDisc, elf), "an absolute root finds the same disc");
    check(absolute && same(ResolvePath(*absolute, bootDir, absolute->settings[0].value), capture),
          "an '@' setting resolves against an absolute root too");

    // V1, still produced by an older launcher: absolute paths and no root line.
    const std::string v1 = "GOW_NATIVE_BOOT_V1\n" + elf.generic_string() + "\nGOW_VU1_CAPTURA=" +
                           capture.generic_string() + "\nGOW_MC0=" + (install / "Mcd001.ps2").generic_string() + "\n";
    const auto legacy = Parse(v1);
    check(legacy.has_value() && legacy->legacy, "a V1 profile is read as legacy");
    check(legacy && legacy->root.empty(), "V1 has no root line");
    const auto legacyDisc = legacy ? GuestElf(*legacy, bootDir) : std::optional<fs::path>();
    check(legacyDisc && same(*legacyDisc, elf), "a V1 absolute disc still starts");
    check(legacy && same(ResolvePath(*legacy, bootDir, legacy->settings[0].value), capture),
          "a V1 absolute setting stays as written");

    // A disc that is not there: the profile parses, but there is no ELF to start, which is what main.cpp reports.
    const std::string missingV2 = "GOW_NATIVE_BOOT_V2\n" + relativeRoot + "\n@data/gow1/discs/eur/SCES_531.33\n";
    const auto missing = Parse(missingV2);
    check(missing.has_value(), "a profile naming a missing disc still parses");
    check(missing && !GuestElf(*missing, bootDir), "a missing V2 disc is reported instead of resolved");
    const std::string missingV1 = "GOW_NATIVE_BOOT_V1\n" + (base / "gone.elf").generic_string() + "\n";
    const auto missingLegacy = Parse(missingV1);
    check(missingLegacy && !GuestElf(*missingLegacy, bootDir), "a missing V1 disc is reported the same way");

    // Anything else is not a profile the runtime may start from.
    check(!Parse(""), "an empty file is not a profile");
    check(!Parse("GOW_NATIVE_BOOT_V3\n.\n@data/gow1/discs/usa/SCUS_973.99\n"), "an unknown header is rejected");
    check(!Parse("GOW_NATIVE_BOOT_V2\n.\n"), "a profile without the guest ELF line is rejected");
    check(!Parse("GOW_NATIVE_BOOT_V1\n"), "a V1 profile without the guest ELF line is rejected");

    fs::remove_all(base, ignored);
    if (failures == 0)
        std::printf("PASS: boot profile reads V2 relative/absolute roots and legacy V1, and reports a missing disc\n");
    return failures == 0 ? 0 : 1;
}
