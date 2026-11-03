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
    sprite.state.context.tex0.tfx=1;
    sprite.state.context.tex0.tcc=1;
    sprite.vertices[0].r=sprite.vertices[0].g=sprite.vertices[0].b=128;
    sprite.vertices[0].a=128;
    sprite.vertices[1]=sprite.vertices[0];
    sprite.vertices[1].x=64; sprite.vertices[1].y=64;
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
      for(unsigned iteration=0;iteration<20;++iteration) {
        const uint8_t color[4]={uint8_t(iteration%2 ? 0 : 255),0,uint8_t(iteration%2 ? 255 : 0),128};
        GSTransferCommand transfer{};
        transfer.direction=0;
        transfer.bitbltbuf.dbp=8192; transfer.bitbltbuf.dbw=1;
        transfer.bitbltbuf.dpsm=format;
        transfer.trxreg={1,1};
        backend.BeginTransfer(transfer);
        const uint8_t index=iteration%2;
        backend.UploadImage(format==GS_PSM_CT32 ? color : &index,format==GS_PSM_CT32 ? 4 : 1);
        backend.Submit(sprite);
        const auto frame=backend.Present(request);
        assert(frame.width==64 && frame.height==64 && frame.pixels.size()>=640u*64u*4u);
        const size_t at=(32u*640u+32u)*4u;
        assert(frame.pixels[at]==color[0] && frame.pixels[at+1]==0 && frame.pixels[at+2]==color[2]);
      }
    }
    std::puts("PASS: real GS CT32/T8/T4 invalidation/re-upload produces alternating red and blue pixels");
}
