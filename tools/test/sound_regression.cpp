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

  // An exponential release must reach ENVX 0: 989snd only reuses a keyed-off voice once its envelope is silent. With the
  // step truncated toward zero (step * level / 0x8000) the level stopped above 0 and the voices piled up until hits and
  // other effects found no free voice (silent combat, sound back after an area change).
  for (unsigned rate : {0u, 4u, 8u, 11u, 13u, 15u}) {
  for (bool exponential : {true, false}) {
    SoundEngine sound;
    std::array<unsigned char,16> block{};
    block[1]=3; // end + repeat: the sample loops, only the envelope can stop the voice
    for (size_t i=2;i<block.size();++i) block[i]=0x77;
    sound.writeSampleRam(0,block.data(),block.size());
    sound.setParam(0x900,0x3fff); sound.setParam(0xa00,0x3fff);
    sound.setSwitch(0x1800,1); sound.setSwitch(0x1a00,1);
    sound.setParam(0x000,0x3fff); sound.setParam(0x100,0x3fff); sound.setParam(0x200,0x1000);
    sound.setParam(0x300,0x000f);                                        // fastest linear attack, sustain level max
    sound.setParam(0x400,static_cast<uint16_t>((exponential ? 0x20u : 0u) | rate)); // release rate, sustain held
    sound.setAddr(0x2000,0);
    sound.setSwitch(0x1500,1);
    uint64_t cycle=4800*SoundEngine::CyclesPerSample;                    // 0.1 s at full level
    sound.advanceTo(cycle);
    require(sound.getParam(0x500)>=0x7000,"attack reaches full level");
    sound.setSwitch(0x1600,1);
    for (unsigned second=0;second<10 && sound.getParam(0x500)!=0;++second) {
        cycle+=48000ull*SoundEngine::CyclesPerSample;
        sound.advanceTo(cycle);
        std::vector<int16_t> sink(96000);
        while (sound.drainOutput(sink.data(),48000)!=0) {}
    }
    if (sound.getParam(0x500)!=0) {
        std::fprintf(stderr,"release rate %u (%s) stops at ENVX %u\n",rate,exponential?"exponential":"linear",sound.getParam(0x500));
        require(false,"released voice must reach ENVX 0");
    }
  }
  }
    std::puts("PASS: linear and exponential releases reach ENVX 0");
}
