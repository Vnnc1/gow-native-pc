#include "runtime/gow_brand.h"
#include <cstdio>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
extern const unsigned char gowBrandImage[] = {0};
extern const std::size_t gowBrandImageSize = 0;
int main(int argc,char**argv) {
    if(argc!=3) return 2;
#ifdef _WIN32
    _setmode(_fileno(stdout),_O_BINARY);
#endif
    SetTraceLogLevel(LOG_NONE); SetConfigFlags(FLAG_WINDOW_HIDDEN);
    InitWindow(1280,720,"RatOne preview");
    Texture2D art=LoadTexture(argv[1]); if(!art.id) return 3;
    RenderTexture2D target=LoadRenderTexture(1280,720);
    for(int frame=0;frame<124;++frame) {
        BeginTextureMode(target); gow_brand::draw(art,frame/30.f,1280,720); EndTextureMode();
        Image image=LoadImageFromTexture(target.texture); ImageFlipVertical(&image);
        ImageFormat(&image,PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
        if(frame==90) ExportImage(image,argv[2]);
        const size_t written=std::fwrite(image.data,4,1280*720,stdout);
        UnloadImage(image); if(written!=1280*720) return 4;
    }
    UnloadRenderTexture(target); UnloadTexture(art); CloseWindow();
}
