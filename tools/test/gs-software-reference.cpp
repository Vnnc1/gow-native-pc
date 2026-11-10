#include "runtime/gs/gs_sw_backend.h"
#include <cstdlib>
#include <vector>

static void check(bool ok) { if (!ok) std::abort(); }
int main()
{
    std::vector<uint8_t> vram(4u * 1024u * 1024u);
    GSSwBackend backend;
    backend.Initialize(vram.data(), static_cast<uint32_t>(vram.size()));
    check(!backend.UsesSharedPresentation());
    GSContext context{};
    context.frame.fbw = 1;
    context.frame.psm = 0;
    context.scissor.x1 = 7;
    context.scissor.y1 = 7;
    check(backend.ClearFramebuffer(context, 0x80402010));
    for (unsigned y = 0; y < 8; ++y)
        for (unsigned x = 0; x < 8; ++x)
            check(backend.ReadVram(0, 0, 1, x, y) == 0x80402010);
    backend.WriteVram(0, 0, 1, 3, 4, 0x11223344);
    check(backend.ReadVram(0, 0, 1, 3, 4) == 0x11223344);
    check(backend.ReadVram(0, 0, 1, 4, 4) == 0x80402010);
    std::vector<uint8_t> snapshot;
    backend.SnapshotVram(snapshot);
    check(snapshot == vram);
    return 0;
}
