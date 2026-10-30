// Standalone deterministic mixer tests; link the patched runtime's sound_engine.cpp.
#include "sound_engine.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <vector>
using ps2x::iop::detail::SoundEngine;
static void require(bool ok, const char *message) { if (!ok) { std::fprintf(stderr, "FAIL: %s\n", message); std::exit(1); } }
int main() {
  for (bool negative : {false,true}) {
  for (unsigned voices=1;voices<=24;++voices) {
    SoundEngine sound;
    std::array<unsigned char,16> block{};
    block[1]=3;
    for (size_t i=2;i<block.size();++i) block[i]=negative ? 0x99 : 0x77;
    sound.writeSampleRam(0,block.data(),block.size());
    for (unsigned core=0;core<2;++core) {
        sound.setParam(0x900|core,0x3fff); sound.setParam(0xa00|core,0x3fff);
        sound.setSwitch(0x1800|core,0xffffff); sound.setSwitch(0x1a00|core,0xffffff);
        for (unsigned voice=0;voice<24;++voice) {
            unsigned v=(voice<<1)|core;
            sound.setParam(v,0x3fff); sound.setParam(0x100|v,0x3fff);
            sound.setParam(0x200|v,0x1000); sound.setParam(0x300|v,0xf);
            sound.setParam(0x400|v,0); sound.setAddr(0x2000|v,0);
        }
        sound.setSwitch(0x1500|core,(1u<<voices)-1);
    }
    sound.advanceTo(256*SoundEngine::CyclesPerSample);
    std::vector<int16_t> out(512);
    require(sound.drainOutput(out.data(),256)==256,"full batch drain");
    for (size_t i=64;i<out.size();++i) require(out[i]==(negative ? -32768 : 32767),"loud mix must saturate without wrapping polarity");
    require(sound.pendingFrames()==0,"queue drained");
  }
  }
    std::puts("PASS: 2-48 voice positive/negative saturation and queue drain");
}
