// Procedural VIF1 packets exercise the real worker barrier without graphics or game data.
#include "runtime/ps2_memory.h"
#include "runtime/gs/gs_stage.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <future>

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

int main()
{
    const bool ok = check("1", "0", true) && check("0", "1", false)
        && check(nullptr, "1", true) && check(nullptr, "0", false)
        && check("1", "1", false, 65520) && stageOnly();
    std::puts(ok ? "PASS: VIF1 barrier, opt-out, async fallback, instance snapshot and small packets"
                 : "FAIL: VIF1 worker barrier");
    return ok ? 0 : 1;
}
