// Regression tests for runtime patches 28/29. No disc or graphics initialization required.
#include "ps2_runtime.h"
#include "runtime/ee_scheduler.h"
#include "runtime/ps2_perf.h"
#include "ps2recomp/code_generator.h"
#include "ps2recomp/r5900_decoder.h"
#include "ps2recomp/types.h"
#include <cstdlib>
#include <iostream>
#include <string>
#include <thread>

extern std::atomic<uint32_t> g_gowRingPos;
void reset_ps2_test_function_table();
namespace {
int failures = 0;
int checks = 0;
void check(bool ok, const std::string &name) {
    ++checks;
    if (!ok) { ++failures; std::cerr << "FAIL: " << name << '\n'; }
}
void env(const char *name, const char *value) {
#ifdef _WIN32
    _putenv_s(name, value ? value : "");
#else
    if (value) setenv(name, value, 1); else unsetenv(name);
#endif
}
uint64_t cycle(PS2Runtime &rt) {
    rt.eeScheduler().publishSnapshot();
    return rt.eeScheduler().snapshot().eeCycle;
}
void implicitReturn(uint8_t *, R5900Context *ctx, PS2Runtime *) {
    ctx->r[2] = _mm_set_epi64x(0, 42);
}
void overrideReturn(uint8_t *, R5900Context *ctx, PS2Runtime *) {
    ctx->r[2] = _mm_set_epi64x(0, 99);
}
void explicitReturn(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = 0x2008; }
void transfer(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = 0x4444; }
void zeroPc(uint8_t *, R5900Context *ctx, PS2Runtime *) { ctx->pc = 0; }
void stop(uint8_t *, R5900Context *, PS2Runtime *rt) { rt->requestStop(); }
void checkpoint(uint8_t *, R5900Context *, PS2Runtime *rt) {
    rt->eeScheduler().requestStop();
    rt->eeCheckpointDue();
}
void selfTail(uint8_t *ram, R5900Context *ctx, PS2Runtime *rt) {
    rt->dispatchGuestBranch(ram, ctx, 0x3000, 0x3010, 0,
                           PS2Runtime::GuestBranchKind::DirectJump, "J");
}
void nested(uint8_t *ram, R5900Context *ctx, PS2Runtime *rt) {
    if (!rt->callGuestFunction(ram, ctx, 0x4000, 0x3000, 0x3008)) return;
    ctx->pc = 0x2008;
}

void parity() {
    using Kind = PS2Runtime::GuestBranchKind;
    using Policy = PS2Runtime::MissingFunctionPolicy;
    struct Case { const char *name; PS2Runtime::RecompiledFunction fn; };
    const Case cases[] = {{"implicit", implicitReturn}, {"explicit", explicitReturn},
        {"transfer", transfer}, {"zero pc", zeroPc}, {"stop", stop},
        {"callee checkpoint", checkpoint}, {"self tail", selfTail}, {"nested", nested}};
    for (auto kind : {Kind::DirectCall, Kind::IndirectCall}) {
        for (const auto &c : cases) {
            bool result[2]{}; R5900Context out[2]{}; uint64_t cycles[2]{}; bool stopped[2]{};
            for (int fast = 0; fast < 2; ++fast) {
                reset_ps2_test_function_table();
                PS2Runtime rt;
                check(rt.registerFunction(0x3000, c.fn), "register callee");
                check(rt.registerFunction(0x4000, implicitReturn), "register nested callee");
                auto &ctx = out[fast]; ctx.pc = 0x2004;
                result[fast] = fast ? rt.callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008, kind, "test")
                    : rt.dispatchGuestBranch(nullptr, &ctx, 0x3000, 0x2000, 0x2008, kind, "test");
                cycles[fast] = cycle(rt);
                stopped[fast] = rt.isStopRequested();
            }
            const std::string name = std::string(c.name) + (kind == Kind::DirectCall ? " JAL" : " JALR");
            check(result[0] == result[1] && out[0].pc == out[1].pc &&
                  getRegU32(&out[0], 2) == getRegU32(&out[1], 2) &&
                  cycles[0] == cycles[1] && stopped[0] == stopped[1], name);
        }
        for (auto policy : {Policy::Stop, Policy::SkipCallDebug, Policy::ContinueToTarget}) {
            for (uint32_t target : {0x3210u, 0x3001u, 0x02000000u, 0xfffffffcu}) {
                bool results[2]{}; R5900Context out[2]{}; bool stopped[2]{}; uint64_t cycles[2]{};
                for (int fast = 0; fast < 2; ++fast) {
                    reset_ps2_test_function_table(); PS2Runtime rt; rt.setMissingFunctionPolicy(policy);
                    rt.registerFunction(0x3000, implicitReturn);
                    results[fast] = fast ? rt.callGuestFunction(nullptr, &out[fast], target, 0x2000, 0x2008, kind, "test")
                        : rt.dispatchGuestBranch(nullptr, &out[fast], target, 0x2000, 0x2008, kind, "test");
                    stopped[fast] = rt.isStopRequested(); cycles[fast] = cycle(rt);
                }
                check(results[0] == results[1] && out[0].pc == out[1].pc && stopped[0] == stopped[1] &&
                      cycles[0] == cycles[1], "invalid/missing target policy and cycle parity");
            }
        }
    }
    reset_ps2_test_function_table(); PS2Runtime rt; R5900Context ctx{};
    rt.registerFunction(0x3000, implicitReturn);
    const auto before = g_gowRingPos.load();
    check(rt.callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008), "lean call returns");
    check(g_gowRingPos.load() == before, "normal call actually bypasses full dispatch");
    check(rt.replaceFunction(0x3000, overrideReturn), "replace registered function");
    rt.callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008);
    check(getRegU32(&ctx, 2) == 99, "replacement is observed on next call");
    rt.eeScheduler().requestStop(); ctx.r[2] = _mm_setzero_si128();
    const auto cycles = cycle(rt);
    check(!rt.callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008), "entry checkpoint unwinds");
    check(ctx.pc == 0x3000 && getRegU32(&ctx, 2) == 0, "entry checkpoint does not run callee");
    check(cycle(rt) - cycles == 8, "entry checkpoint charges eight cycles");
}

void diagnostics(const std::string &mode) {
    // Set after main starts, just like gow-native.boot. Static initialization must not freeze these values.
    env("GOW_DISPATCH_FULL", nullptr); env("PS2X_GS_WORKER_TRACE", nullptr); env("GOW_PERF_FRAME_PC", nullptr);
    if (mode == "full") env("GOW_DISPATCH_FULL", "1");
    if (mode == "trace") env("PS2X_GS_WORKER_TRACE", "0");
    if (mode == "watch") { env("GOW_PERF_FRAME_PC", "0x3000"); env("GOW_PERF_DIAG", "1"); }
    reset_ps2_test_function_table(); PS2Runtime rt;
    const uint32_t target = mode == "trace" ? 0x1837b8u : 0x3000u;
    rt.registerFunction(target, implicitReturn); rt.registerFunction(0x4000, implicitReturn);
    for (auto kind : {PS2Runtime::GuestBranchKind::DirectCall, PS2Runtime::GuestBranchKind::IndirectCall}) {
        R5900Context ctx{}; const auto before = g_gowRingPos.load(); const auto frames = ps2_perf::guestFlips.load();
        check(rt.callGuestFunction(nullptr, &ctx, target, 0x2000, 0x2008, kind, "test"), "diagnostic call returns");
        check(g_gowRingPos.load() == before + 1, "late environment routes call through full dispatch");
        if (mode == "watch") {
            check(ps2_perf::guestFlips.load() == frames + 1, "watched call counts guest frame");
            const auto ring = g_gowRingPos.load();
            rt.callGuestFunction(nullptr, &ctx, 0x4000, 0x2000, 0x2008, kind, "test");
            check(g_gowRingPos.load() == ring, "unwatched call stays lean");
        }
    }
}

void traceClock() {
    // Run with PS2X_GS_WORKER_TRACE=0 inherited. The first dispatch starts the two-second window,
    // even when the first watched function only appears much later.
    reset_ps2_test_function_table(); PS2Runtime rt; R5900Context ctx{};
    rt.registerFunction(0x3000, implicitReturn); rt.registerFunction(0x1837b8, implicitReturn);
    rt.dispatchGuestBranch(nullptr, &ctx, 0x3000, 0x2000, 0x2008, PS2Runtime::GuestBranchKind::DirectCall, "JAL");
    std::this_thread::sleep_for(std::chrono::milliseconds(2200));
    rt.dispatchGuestBranch(nullptr, &ctx, 0x1837b8, 0x2000, 0x2008, PS2Runtime::GuestBranchKind::DirectCall, "JAL");
    check(ctx.pc == 0x2008, "trace timing does not change return behavior");
    // The test driver asserts stderr contains no [gsw-trace] records after the window has ended.
}

void instances() {
    // A boot profile may also clear an inherited flag. Each runtime keeps its own snapshot.
    env("GOW_DISPATCH_FULL", nullptr); env("PS2X_GS_WORKER_TRACE", nullptr); env("GOW_PERF_FRAME_PC", nullptr);
    reset_ps2_test_function_table();
    auto lean = std::make_unique<PS2Runtime>();
    env("GOW_DISPATCH_FULL", "1");
    auto full = std::make_unique<PS2Runtime>();
    lean->registerFunction(0x3000, implicitReturn); R5900Context ctx{};
    const auto before = g_gowRingPos.load();
    lean->callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008);
    check(g_gowRingPos.load() == before, "cleared inherited flag stays lean after constructing another runtime");
    full->callGuestFunction(nullptr, &ctx, 0x3000, 0x2000, 0x2008);
    check(g_gowRingPos.load() == before + 1, "second runtime uses its own diagnostic settings");
}

void codegen() {
    using namespace ps2recomp;
    const char *mode = std::getenv("PS2X_STATIC_CALLS");
    const bool full = mode && std::string(mode) == "dispatch";
    for (uint32_t opcode : {0x0c002c00u, 0x0080f809u}) { // JAL 0xb000; JALR $ra,$a0
        Function func{}; func.name = "test_call"; func.start = 0xa000; func.end = 0xa008; func.isRecompiled = true;
        Symbol symbol{}; symbol.name = "callee"; symbol.address = 0xb000; symbol.isFunction = true;
        const std::vector<Section> sections;
        R5900Decoder decoder; CodeGenerator gen({symbol}, sections);
        const auto source = gen.generateFunction(func, {decoder.decodeInstruction(0xa000, opcode),
            decoder.decodeInstruction(0xa004, 0x24040007u)}, false); // delay slot overwrites a0
        const auto helper = full ? "runtime->dispatchGuestBranch" : "runtime->callGuestFunction";
        check(source.find(helper) != std::string::npos, "selected call backend emitted");
        check(source.find("0xA000u, 0xA008u") != std::string::npos, "call-site and resume PCs preserved");
        check(source.find("SET_GPR_U32(ctx, 31, 0xA008u)") != std::string::npos, "link register preserved");
        if (opcode == 0x0080f809u) {
            check(source.find("IndirectCall") != std::string::npos, "JALR kind preserved");
            const auto capture = source.find("const uint32_t jumpTarget = GPR_U32(ctx, 4)");
            // There is also a separate delay-slot resume block before the normal call path.
            const auto delay = source.find("SET_GPR_S32(ctx, 4", capture);
            check(capture != std::string::npos && delay != std::string::npos && delay < source.find(helper, capture),
                  "JALR snapshots target before delay slot overwrite");
        }
    }
}
}
int main(int argc, char **argv) {
    const std::string mode = argc > 1 ? argv[1] : "parity";
    if (mode == "parity") parity(); else if (mode == "codegen") codegen();
    else if (mode == "trace-clock") traceClock(); else if (mode == "instances") instances(); else diagnostics(mode);
    std::cout << mode << ": " << checks << " checks, " << failures << " failures\n";
    return failures ? 1 : 0;
}
