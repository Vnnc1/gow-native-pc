// Deterministic command/vertex parity through the production frontend and worker queue.
// No GL context, game data or player memory card is used.
#include "runtime/gs/gs_frontend.h"
#include "runtime/gs/gs_threaded_backend.h"
#include "runtime/ps2_memory.h"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void require(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
void setting(const char *name, const char *value) {
#ifdef _WIN32
    _putenv_s(name, value);
#else
    setenv(name, value, 1);
#endif
}
struct Trace {
    std::vector<std::string> events;
    std::vector<GSPrimitiveBatch> draws;
    unsigned runs = 0;
};
class Recorder final : public GSRasterBackend {
    Trace &trace;
public:
    explicit Recorder(Trace &t) : trace(t) {}
    void Initialize(uint8_t *, uint32_t) override {}
    void Reset() override { trace.events.emplace_back("reset"); }
    void Submit(const GSPrimitiveBatch &b) override { trace.events.emplace_back("draw"); trace.draws.push_back(b); }
    void SubmitRun(const GSDrawState &s, const GSVertex *v, const uint8_t *c, uint32_t n) override {
        ++trace.runs;
        GSRasterBackend::SubmitRun(s, v, c, n);
    }
    void LoadClut(const GSTex0Reg &, const GSTexClutReg &) override { trace.events.emplace_back("clut"); }
    void BeginTransfer(const GSTransferCommand &) override { trace.events.emplace_back("transfer"); }
    void UploadImage(const uint8_t *data, uint32_t n) override {
        std::string event = "upload:";
        for (uint32_t i = 0; i < n; ++i) event += std::to_string(data[i]) + ",";
        trace.events.push_back(event);
    }
    void Flush() override { trace.events.emplace_back("flush"); }
    void TextureFlush() override { trace.events.emplace_back("texflush"); }
    void Sync(GSSyncReason r) override { trace.events.push_back("sync:" + std::to_string(static_cast<int>(r))); }
    PresentationFrame Present(const GSPresentationRequest &) override { trace.events.emplace_back("present"); return {}; }
    bool ClearFramebuffer(const GSContext &, uint32_t) override { trace.events.emplace_back("clear"); return false; }
    uint32_t ConsumeLocalToHostBytes(uint8_t *, uint32_t) override { trace.events.emplace_back("consume"); return 0; }
    uint32_t ReadVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) const override { trace.events.emplace_back("read"); return 0; }
    void WriteVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) override { trace.events.emplace_back("write"); }
    void SnapshotVram(std::vector<uint8_t> &out) const override { trace.events.emplace_back("snapshot"); out.assign(4 * 1024 * 1024, 0); }
    GSTransferSnapshot GetTransferSnapshot() const override { return {}; }
};
bool equal(const GSVertex &a, const GSVertex &b) {
    return a.x == b.x && a.y == b.y && a.z == b.z && a.r == b.r && a.g == b.g && a.b == b.b &&
        a.a == b.a && a.q == b.q && a.s == b.s && a.t == b.t && a.u == b.u && a.v == b.v && a.fog == b.fog;
}
void compare(const Trace &a, const Trace &b) {
    require(a.events == b.events, "backend command order changed");
    require(a.draws.size() == b.draws.size(), "primitive count changed");
    for (size_t i = 0; i < a.draws.size(); ++i) {
        const auto &x = a.draws[i]; const auto &y = b.draws[i];
        require(x.state == y.state && x.vertexCount == y.vertexCount, "draw state/count changed");
        for (unsigned v = 0; v < 3; ++v) require(equal(x.vertices[v], y.vertices[v]), "vertex field changed");
    }
}
Trace queue(bool grouped, bool compact) {
    setting("PS2X_GS_COMPACT_QUEUE", compact ? "1" : "0");
    setting("PS2X_GS_QUEUE_CHUNKS", "1");
    Trace trace;
    {
        GSThreadedBackend backend(std::make_unique<Recorder>(trace));
        backend.Initialize(nullptr, 0);
        std::array<GSVertex, 129 * 3> vertices{};
        std::array<uint8_t, 129> counts{};
        for (unsigned i = 0; i < counts.size(); ++i) {
            counts[i] = static_cast<uint8_t>(i % 4);
            for (unsigned v = 0; v < counts[i]; ++v) {
                vertices[i * 3 + v].x = float(i * 3 + v);
                vertices[i * 3 + v].q = 2;
            }
        }
        for (unsigned pass = 0; pass < 20; ++pass) { // Exceed the real 64 KiB publication boundary.
            GSDrawState state{}; state.colclamp = pass % 2;
            if (grouped) backend.SubmitRun(state, vertices.data(), counts.data(), 129);
            else for (unsigned i = 0; i < counts.size(); ++i) {
                GSPrimitiveBatch b{}; b.state = state; b.vertexCount = counts[i];
                std::copy_n(vertices.data() + i * 3, 3, b.vertices.data());
                backend.Submit(b);
            }
            backend.LoadClut({}, {});
            backend.BeginTransfer({});
            const uint8_t pixels[] = {1, 7, 19, 31};
            backend.UploadImage(pixels, sizeof(pixels));
            backend.TextureFlush();
            backend.WriteVram(0, 0, 1, 0, 0, pass);
            backend.ReadVram(0, 0, 1, 0, 0);
            backend.Present({});
        }
        backend.Flush();
    }
    return trace;
}
void append64(std::vector<uint8_t> &out, uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) out.push_back(static_cast<uint8_t>(value >> (i * 8)));
}
Trace frontend(bool grouped, bool threaded, bool compact, bool defaultSetting = false) {
    setting("PS2X_GS_RUN", defaultSetting ? "" : (grouped ? "1" : "0"));
    setting("PS2X_GS_COMPACT_QUEUE", compact ? "1" : "0");
    Trace trace;
    std::vector<uint8_t> vram(4 * 1024 * 1024);
    GSRegisters registers{};
    {
        GS gs;
        std::unique_ptr<GSRasterBackend> backend = std::make_unique<Recorder>(trace);
        if (threaded) backend = std::make_unique<GSThreadedBackend>(std::move(backend));
        gs.setRasterBackend(std::move(backend));
        gs.init(vram.data(), static_cast<uint32_t>(vram.size()), &registers);
        auto draw = [&](unsigned prim, unsigned count) {
            gs.writeRegister(0x00, prim);
            gs.writeRegister(0x01, 0x3f80000080402010ull);
            for (unsigned i = 0; i < count; ++i)
                gs.writeRegister(0x05, uint64_t(16 + i) | (uint64_t(32 + i) << 16) | (uint64_t(i + 1) << 32));
        };
        for (unsigned prim : {0u, 1u, 3u, 6u}) {
            draw(prim, 210);
            gs.writeRegister(0x46, prim & 1); // State change flushes before the next primitive.
            draw(prim, 6);
            gs.writeRegister(0x06, uint64_t(1) << 61); // CLUT load, CLD=1.
            draw(0, 1); gs.writeRegister(0x3f, 0); // TEXFLUSH.
            draw(0, 1); gs.writeRegister(0x53, 0); // Transfer start.
            draw(0, 1);
            const uint8_t pixels[] = {9, 8, 7, 6};
            gs.uploadImageNative(uint64_t(1) << 48, 0, 1ull | (1ull << 32), 0, pixels, sizeof(pixels));
            draw(0, 1); gs.writeRegister(0x61, 0); // FINISH.
            draw(0, 1); gs.ReadVram(0, 0, 1, 0, 0);
            draw(0, 1); gs.WriteVram(0, 0, 1, 0, 0, 7);
            draw(0, 1); gs.refreshDisplaySnapshot();
            draw(0, 1); gs.latchHostPresentationFrame();
            draw(0, 1); gs.clearActiveFramebuffer(0);
        }
        // A+D GIF packet split across calls: a point followed by TEXFLUSH, then packet boundary.
        std::vector<uint8_t> packet;
        append64(packet, 3ull | (1ull << 15) | (1ull << 60)); append64(packet, 0xe);
        append64(packet, 0); append64(packet, 0x00);
        append64(packet, 32ull | (48ull << 16) | (1ull << 32)); append64(packet, 0x05);
        append64(packet, 0); append64(packet, 0x3f);
        gs.processGIFPacket(packet.data(), 35, GifPathId::Path1);
        gs.processGIFPacket(packet.data() + 35, static_cast<uint32_t>(packet.size() - 35), GifPathId::Path1);
        packet.clear();
        append64(packet, 71ull | (1ull << 15) | (1ull << 60)); append64(packet, 0xe);
        append64(packet, 0); append64(packet, 0x00);
        for (unsigned i = 0; i < 70; ++i) {
            append64(packet, (32ull + i) | (48ull << 16) | (1ull << 32)); append64(packet, 0x05);
        }
        require(gs.processNativePackedGIFPacket(packet.data(), static_cast<uint32_t>(packet.size()), GifPathId::Path2),
                "native packed GIF route was not exercised");
        gs.setRasterBackend(nullptr); // Flush the last group before detaching its backend.
    }
    require(trace.draws.size() > 400, "frontend did not exercise draw path");
    for (const char *event : {"clut", "transfer", "texflush", "present", "snapshot", "read", "write"})
        require(std::find(trace.events.begin(), trace.events.end(), event) != trace.events.end(), "missing boundary coverage");
    if (grouped && (!threaded || compact)) require(trace.runs > 0, "grouped path was not exercised");
    if (!grouped) require(trace.runs == 0, "individual/default path unexpectedly grouped primitives");
    return trace;
}
}
int main() {
    try {
        const auto reference = queue(false, true);
        compare(reference, queue(true, true));
        compare(reference, queue(true, false));
        for (bool threaded : {false, true}) for (bool compact : {false, true})
            compare(frontend(false, threaded, compact), frontend(true, threaded, compact));
        compare(frontend(false, true, true), frontend(false, true, true, true));
        std::cout << "PASS: production Run encoding/decoding, publication boundaries, frontend state/transfer/CLUT/FINISH/readback ordering\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
