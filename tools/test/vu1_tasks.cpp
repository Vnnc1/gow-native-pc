// Standalone replay of locally captured VU1 tasks. No ISO, renderer or save is needed for replay.
#include "runtime/ps2_vu1.h"
#include "runtime/ps2_vu1_native.h"
#include "runtime/gs/gs_frontend.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

static void env(const char *k, const char *v) {
#ifdef _WIN32
    _putenv_s(k, v);
#else
    setenv(k, v, 1);
#endif
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        std::fprintf(stderr, "Usage: gow_vu1_tasks --fixture <file|none> | --replay <file> [hybrid|jit|helper|sse|exact] [repetitions=5]\n");
        return 2;
    }
    env("GOW_VU1N_X64", "1");
    const std::string action = argv[1];
    if (action == "--fixture") {
        if (std::string(argv[2]) != "none") env("GOW_VU1_TASK_RECORD", argv[2]);
        env("GOW_VU1_TASK_LIMIT", "3"); env("GOW_VU1_TASK_STRIDE", "1");
        std::array<uint32_t, 4096> code{};
        std::array<uint8_t, 16384> data{};
        code[0] = (0x08u << 25) | (1u << 16) | 17u; // IADDIU vi1, vi0, 17
        code[1] = 0x2ffu;
        code[2] = (0x05u << 25) | (8u << 21) | (1u << 16) | 0x200u; // ISW.x vi1, 0x200(vi0)
        code[3] = 0x28u | (15u << 21) | (2u << 16) | (1u << 11) | (3u << 6); // ADD vf3,vf1,vf2
        code[4] = 0x800006fcu; code[5] = 0x2ffu; // XGKICK vi0: one packed NOP, safe without a graphics device.
        code[6] = 0x8000033cu; code[7] = 0x2ffu | (1u << 30);
        code[8] = 0x8000033cu; code[9] = 0x2ffu;
        const uint64_t tag[] = {0x1000000000008001ull, 0xfull};
        std::memcpy(data.data(), tag, sizeof(tag));
        GS gs;
        VU1Interpreter vu;
        uint64_t digest = 0;
        for (unsigned i = 0; i < 4; ++i) {
            for (unsigned lane = 0; lane < 4; ++lane) {
                vu.state().vf[1][lane] = float(i + lane);
                vu.state().vf[2][lane] = 1.0f;
            }
            vu.execute(reinterpret_cast<uint8_t *>(code.data()), 16384, data.data(), data.size(), gs, nullptr, 0, 0, 0, 200);
            uint32_t bits; std::memcpy(&bits, vu.state().vf[3], 4);
            digest = digest * 31 + bits + data[8192];
        }
        std::printf("fixture_digest=%016llx\n", (unsigned long long)digest);
        return 0;
    }
    if (action != "--replay") return 2;
    const std::string mode = argc > 3 ? argv[3] : "hybrid";
    if (mode != "hybrid" && mode != "jit" && mode != "helper" && mode != "sse" && mode != "exact") return 2;
    if (mode == "jit" || mode == "helper" || mode == "sse") env("GOW_VU1X_ONLY", "1");
    if (mode == "helper") env("GOW_VU1X_INLINE", "0");
    if (mode == "sse") env("GOW_VU1X_AVX", "0");
    char *end = nullptr;
    const unsigned long reps = argc > 4 ? std::strtoul(argv[4], &end, 10) : 5;
    if (!reps || reps > 100 || (end && *end)) return 2;
    return VU1NativeAccess::replayTasks(argv[2], unsigned(reps), mode == "exact");
}
