// Procedural VIF1 packets exercise the real worker barrier without graphics or game data.
#include "runtime/ps2_memory.h"
#include "runtime/gs/gs_stage.h"
#include "runtime/gs/gs_display.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <future>
#include <mutex>
#include <vector>

static void env(const char *key, const char *value)
{
#ifdef _WIN32
    _putenv_s(key, value ? value : "");
#else
    if (value) setenv(key, value, 1); else unsetenv(key);
#endif
}

static bool check(const char *early, const char *async, bool barrier, uint32_t packetBytes = 65536)
{
    using namespace std::chrono_literals;
    env("PS2X_GS_WORKER", "1");
    env("GOW_VU1_EARLY_FINISH", early);
    env("GOW_GS_FINISH_ASINCRONO", async);
    env("GOW_SYNC_DIAG", "1");
    PS2Memory mem;
    if (!mem.initialize()) return false;
    // Later environment changes must not alter an existing instance's decision.
    env("GOW_VU1_EARLY_FINISH", barrier ? "0" : "1");
    std::promise<void> entered, release, submitting;
    auto enteredFuture = entered.get_future();
    auto releaseFuture = release.get_future().share();
    mem.setVu1MscalCallback([&](uint32_t, uint32_t, uint32_t) {
        mem.syncGsWorker("worker self guard");
        entered.set_value();
        releaseFuture.wait();
    });
    const uint32_t mscal = 0x14000000u;
    std::memset(mem.getRDRAM() + 0x1000, 0, 16);
    std::memcpy(mem.getRDRAM() + 0x1000, &mscal, sizeof(mscal));
    std::memset(mem.getRDRAM() + 0x2000, 0, 65536); // NOP-only VIF packet
    mem.sendDma(PS2Memory::DmaPath::Vif1, 0x1000, 1);
    if (enteredFuture.wait_for(5s) != std::future_status::ready) {
        release.set_value();
        return false;
    }
    auto submit = std::async(std::launch::async, [&] {
        submitting.set_value();
        mem.sendDma(PS2Memory::DmaPath::Vif1, 0x2000, packetBytes / 16);
    });
    submitting.get_future().wait();
    const auto status = submit.wait_for(barrier ? 100ms : 5s);
    release.set_value(); // release even if the assertion fails, so cleanup cannot deadlock
    submit.get();
    mem.syncGsWorker("worker regression");
    const auto metrics = mem.syncMetrics();
    return metrics[0].calls == unsigned(barrier)
        && (!barrier || (metrics[0].workerWaits == 1 && metrics[0].workerNs >= 50000000u))
        && status == (barrier ? std::future_status::timeout : std::future_status::ready)
        && mem.dmaStartCount() == 2;
}

static bool stageOnly()
{
    using namespace std::chrono_literals;
    env("GOW_SYNC_DIAG", "1");
    PS2Memory mem;
    if (!mem.initialize()) return false;
    std::promise<void> entered, release;
    auto released = release.get_future().share();
    bool selfWait = true;
    ps2_gs_stage::start([&](GifPathId, const uint8_t *, uint32_t) {
        selfWait = ps2_gs_stage::waitIdle(); // Must not wait on itself.
        mem.syncGsWorker("stage self guard");
        entered.set_value(); released.wait();
    }, {});
    const uint8_t packet[16]{};
    ps2_gs_stage::push(GifPathId::Path1, packet, sizeof(packet));
    if (entered.get_future().wait_for(5s) != std::future_status::ready) {
        release.set_value(); return false;
    }
    auto waiter = std::async(std::launch::async, [&] { mem.syncGsWorker("stage-only test"); });
    const bool blocked = waiter.wait_for(100ms) == std::future_status::timeout;
    release.set_value(); waiter.get(); ps2_gs_stage::stop();
    const auto e = mem.syncMetrics()[2];
    env("GOW_SYNC_DIAG", "0");
    PS2Memory quiet;
    env("GOW_SYNC_DIAG", "1"); // Configuration is per instance, never a stale global snapshot.
    quiet.syncGsWorker();
    return blocked && !selfWait && e.calls == 1 && e.workerWaits == 0 && e.stageWaits == 1
        && e.stageNs >= 50000000u && quiet.syncMetrics()[2].calls == 0;
}

// Patch 40: a VIF1 packet whose DIRECT data writes FINISH (A+D 0x61) after an UNPACK and a decoy qword.
static std::vector<uint8_t> finishPacket()
{
    std::vector<uint8_t> v;
    auto word = [&](uint32_t w) { const uint8_t *b = reinterpret_cast<const uint8_t *>(&w); v.insert(v.end(), b, b + 4); };
    auto quad = [&](uint64_t lo, uint64_t hi) {
        const uint8_t *a = reinterpret_cast<const uint8_t *>(&lo), *b = reinterpret_cast<const uint8_t *>(&hi);
        v.insert(v.end(), a, a + 8); v.insert(v.end(), b, b + 8);
    };
    word(0x01000404u);              // STCYCL cl=4 wl=4
    word((0x6Cu << 24) | (2u << 16)); // UNPACK V4-32, 2 vectors
    quad(0x61u, 0xEull); quad(0, 0x61u); // UNPACK data that looks like a FINISH write must not count
    word(0); word(0); word(0);      // NOPs: align the DIRECT data to a qword
    word(0x50000002u);              // DIRECT 2 qwords
    quad(1ull | (1ull << 15) | (1ull << 60), 0xEull); // GIFtag NLOOP=1 EOP PACKED NREG=1, REGS=A+D
    quad(0, 0x61u);                 // A+D: FINISH
    return v;
}

static bool earlyFinish()
{
    using namespace std::chrono_literals;
    const std::vector<uint8_t> packet = finishPacket();
    uint32_t cycle = 0x0101u, left = 0u;
    if (PS2Memory::countPath2Finish(packet.data(), uint32_t(packet.size()), cycle, left) != 1u || left != 0u || cycle != 0x0404u)
        return false;
    // A DIRECT cut by the packet end is skipped in the next packet, not parsed as VIF codes.
    cycle = 0x0101u; left = 0u;
    const uint32_t cut = uint32_t(packet.size()) - 8u;
    // DIRECT data starts at byte 56: 24 of its 32 bytes fit before the cut, the last 8 open the next packet
    if (PS2Memory::countPath2Finish(packet.data(), cut, cycle, left) != 0u || left != 8u ||
        PS2Memory::countPath2Finish(packet.data() + cut, 8u, cycle, left) != 0u || left != 0u)
    {
        std::printf("early finish: cut scan left=%u\n", left);
        return false;
    }

    env("PS2X_GS_WORKER", "1");
    env("GOW_GS_EARLY_FINISH", "1");
    env("GOW_SYNC_DIAG", "0");
    PS2Memory mem;
    if (!mem.initialize() || !mem.gsEarlyFinish()) return false;
    std::promise<void> blocked, release;
    auto released = release.get_future().share();
    std::vector<uint32_t> markers; // type << 16 | value, in stage order
    std::mutex markerMutex;
    bool first = true;
    ps2_gs_stage::start([&](GifPathId path, const uint8_t *data, uint32_t size) {
        if (path != static_cast<GifPathId>(0) || size < 12) return;
        uint32_t type = 0, value = 0;
        std::memcpy(&type, data, 4); std::memcpy(&value, data + 8, 4);
        std::lock_guard<std::mutex> lock(markerMutex);
        markers.push_back((type << 16) | (value & 0xFFFFu));
        if (first) { first = false; blocked.set_value(); released.wait(); } // hold the drawing back
    }, {});
    std::memcpy(mem.getRDRAM() + 0x2000, packet.data(), packet.size());
    mem.sendDma(PS2Memory::DmaPath::Vif1, 0x2000, uint32_t((packet.size() + 15) / 16));
    const bool raised = (mem.gs().csr.load() & 2u) != 0u; // raised at submission, before any drawing
    if (blocked.get_future().wait_for(5s) != std::future_status::ready) { release.set_value(); ps2_gs_stage::stop(); return false; }
    // While the stage is held: CSR reads and display writes must not wait for it.
    auto quick = std::async(std::launch::async, [&] {
        const uint64_t csr = mem.gsStatusLoad();
        mem.gsDisplayStore(0x12000070u, 0x1234u); // DISPFB1
        return csr;
    });
    const bool noWait = quick.wait_for(2s) == std::future_status::ready;
    const bool shadowed = ps2_gs_display::display(mem).dispfb1 == 0x1234u && mem.gs().dispfb1 != 0x1234u;
    release.set_value();
    quick.get();
    mem.syncGsWorker("early finish test");
    ps2_gs_stage::stop();
    std::lock_guard<std::mutex> lock(markerMutex);
    // suppress 1 before the packet, suppress 0 after it, then the display write
    const bool order = markers.size() == 3 && markers[0] == ((2u << 16) | 1u) && markers[1] == (2u << 16) &&
                       (markers[2] >> 16) == 1u;
    env("GOW_GS_EARLY_FINISH", "0");
    if (!(raised && noWait && shadowed && order))
    {
        std::printf("early finish: raised=%d noWait=%d shadowed=%d order=%d markers=", raised, noWait, shadowed, order);
        for (uint32_t m : markers)
            std::printf("%08x ", m);
        std::puts("");
    }
    return raised && noWait && shadowed && order;
}

int main()
{
    const bool ok = check("1", "0", true) && check("0", "1", false)
        && check(nullptr, "1", false) && check(nullptr, "0", false)
        && check("1", "1", false, 65520) && stageOnly();
    std::puts(ok ? "PASS: VIF1 barrier, opt-out, async fallback, instance snapshot and small packets"
                 : "FAIL: VIF1 worker barrier");
    const bool early = earlyFinish();
    std::puts(early ? "PASS: early FINISH scan, raise at submission, unblocked CSR/display, stage marker order"
                    : "FAIL: early FINISH");
    return ok && early ? 0 : 1;
}
