#include "runtime/mod_vfs_table.h"
#include "runtime/gow_mod_patches.h"
#include <cstdlib>
#include <cstring>
#include <vector>

static void check(bool ok) { if (!ok) std::abort(); }
int main(int argc, char **argv)
{
    check(argc == 2);
    const bool active = std::strcmp(argv[1], "active") == 0;
    const auto &table = gow::mods::ModVfsTable::instance();
    std::filesystem::path result;
    check(table.active() == active);
    check(table.lookup("CDROM0:\\SYNTHETIC.BIN;1", result) == active);
    if (active) check(result.filename() == "payload.bin");
    check(!table.lookup("cdrom0:/missing.bin", result));
    std::vector<uint8_t> ram(32u * 1024u * 1024u, 0);
    gow::mods::dataPatchesVBlank(ram.data());
    check(ram[0x100000] == (active ? 42 : 0));
    check(ram[0x100004] == (active ? 7 : 0));
    // Invalid addresses, malformed values and narrowed widths must not be applied.
    check(ram.back() == 0 && ram[ram.size()-4] == 0);
    check(ram[0x100008] == 0 && ram[0x10000C] == 0 && ram[0x100010] == 0);
    ram[0x100004] = 9;
    gow::mods::dataPatchesVBlank(ram.data());
    check(ram[0x100004] == 9); // once-only patch does not repeat
    return 0;
}
