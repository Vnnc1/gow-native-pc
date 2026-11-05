// Optional real-OpenGL check: run explicitly on the validation GPU, never as a headless CI test.
#undef NDEBUG
#include "runtime/gs/gs_hw_backend.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <vector>

int main()
{
#ifdef _WIN32
    _putenv_s("PS2X_GS_HW_SCALE", "1");
#else
    setenv("PS2X_GS_HW_SCALE", "1", 1);
#endif
    std::vector<uint8_t> vram(4u*1024u*1024u);
    GSHwBackend backend;
    backend.Initialize(vram.data(), static_cast<uint32_t>(vram.size()));
    GSPrimitiveBatch sprite{};
    sprite.vertexCount=2;
    sprite.state.prim.type=GS_PRIM_SPRITE;
    sprite.state.prim.tme=true;
    sprite.state.prim.fst=true;
    sprite.state.context.frame.fbw=1;
    sprite.state.context.scissor={0,63,0,63};
    sprite.state.context.zbuf.zmask=true;
    sprite.state.context.test=1ull<<17;
    sprite.state.colclamp=1;
    sprite.state.context.tex0.tbp0=8192;
    sprite.state.context.tex0.tbw=1;
    sprite.state.textureWidth=sprite.state.textureHeight=2;
    sprite.state.context.tex0.tw=sprite.state.context.tex0.th=1;
    sprite.state.context.tex0.tfx=1;
    sprite.state.context.tex0.tcc=1;
    sprite.vertices[0].r=sprite.vertices[0].g=sprite.vertices[0].b=128;
    sprite.vertices[0].a=128;
    sprite.vertices[1]=sprite.vertices[0];
    sprite.vertices[1].x=64; sprite.vertices[1].y=64;
    sprite.vertices[1].u=64; sprite.vertices[1].v=64;
    GSPresentationRequest request{};
    request.pmode=1; request.dispfb1=1ull<<9;
    request.display1=(63ull<<32)|(63ull<<44);
    for(const uint8_t format : {uint8_t(GS_PSM_CT32),uint8_t(GS_PSM_T8),uint8_t(GS_PSM_T4)}) {
      sprite.state.context.tex0.psm=format;
      sprite.state.context.tex0.cbp=10000;
      sprite.state.context.tex0.cld=1;
      backend.WriteVram(GS_PSM_CT32,10000,1,0,0,0x800000ff);
      backend.WriteVram(GS_PSM_CT32,10000,1,1,0,0x80ff0000);
      backend.LoadClut(sprite.state.context.tex0,{});
      for(unsigned iteration=0;iteration<128;++iteration) {
        if (iteration % 8 == 0)
        {
            const uint32_t colors[4] = {iteration % 16 ? 0x800000ffu : 0x80ff0000u, 0x4000ff00u, 0xffffffffu, 0x00000000u};
            const uint8_t indices[4] = {0,1,1,0}, packed[2] = {0x10,0x01};
            GSTransferCommand transfer{};
            transfer.direction=0;
            transfer.bitbltbuf.dbp=8192; transfer.bitbltbuf.dbw=1;
            transfer.bitbltbuf.dpsm=format;
            transfer.trxreg={2,2};
            backend.BeginTransfer(transfer);
            backend.UploadImage(format==GS_PSM_CT32 ? reinterpret_cast<const uint8_t*>(colors) : format==GS_PSM_T8 ? indices : packed,
                                format==GS_PSM_CT32 ? 16 : format==GS_PSM_T8 ? 4 : 2);
        }
        sprite.state.context.zbuf.zbp = iteration % 8 == 7 ? 0 : 32;
        sprite.state.prim.abe = iteration % 16 == 14;
        sprite.state.context.alpha = 0x54; // Destination-alpha blending exercises the full shader.
        sprite.state.linearFilter = (iteration & 1u) != 0;
        sprite.state.context.clamp = (iteration & 2u) ? 5u : 0u;
        sprite.state.context.tex0.tfx = (iteration >> 2) & 3u;
        sprite.state.context.tex0.tcc = (iteration >> 4) & 1u;
        sprite.state.context.test = (1ull << 17) | (1ull << 16) | (iteration % 8 == 6 ? 1ull << 14 : 0ull) | 1u | (((iteration >> 4) & 7u) << 1) | (128u << 4) | (1u << 12);
        sprite.vertices[0].a = sprite.vertices[1].a = (iteration & 8u) ? 64 : 192;
        backend.Submit(sprite);
        backend.Submit(sprite); // Repeated texture state without an intervening upload.
        const auto frame=backend.Present(request);
        assert(frame.width==64 && frame.height==64 && frame.pixels.size()>=640u*64u*4u);
        uint64_t hash = 14695981039346656037ull;
        for (const auto byte : frame.pixels) hash = (hash ^ byte) * 1099511628211ull;
        std::printf("CASE %u %u %016llx\n", unsigned(format), iteration, (unsigned long long)hash);
      }
    }
    std::puts("PASS: 384 real GL frames covering texture formats, reuploads, sampler changes, TFX/TCC and alpha passes");
}
