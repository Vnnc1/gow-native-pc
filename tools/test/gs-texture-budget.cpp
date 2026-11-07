#undef NDEBUG
#include "runtime/gs/gs_texture_budget.h"
#include <cassert>
#include <unordered_map>

struct Texture { uint64_t allocatedBytes, lastUse; };
int main()
{
    std::unordered_map<int, Texture> textures{{1,{40,1}}, {2,{40,2}}, {3,{0,3}}};
    uint64_t bytes=80; int released=0;
    auto release=[&](Texture &) { ++released; };
    auto *active=&textures.at(3);
    gsReserveTextureBytes(textures,*active,bytes,40,100,release);
    assert(bytes==80 && released==1 && !textures.contains(1) && &textures.at(3)==active);
    // Re-upload replaces accounting instead of accumulating it; never evicts itself.
    gsReserveTextureBytes(textures,*active,bytes,20,100,release);
    assert(bytes==60 && released==1);
    gsReserveTextureBytes(textures,*active,bytes,120,100,release);
    assert(bytes==120 && released==2 && textures.size()==1);
    gsReserveTextureBytes(textures,*active,bytes,0,100,release);
    assert(bytes==0 && released==2);
    // Repeated unique large uploads stay bounded without waiting for a count threshold.
    for(int i=4;i<10000;++i) {
        auto &current=textures[i]; current.lastUse=i;
        gsReserveTextureBytes(textures,current,bytes,16,100,release);
        assert(bytes<=100 && current.allocatedBytes==16 && textures.size()<=8);
    }
}
