"""Production raylib menu with deterministic input; GPU screenshots, no game/card needed."""
import argparse, os, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for name in ('runtime','compiler','raylib','raylib-lib','art','background','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
source=a.output/'game-menu.cpp'
source.write_text(Path(__file__).with_suffix('.cpp.in').read_text(encoding='utf-8').replace('@MENU_SOURCE@',(a.runtime.resolve()/'src/lib/gow_trucos.cpp').as_posix()),encoding='utf-8')
brand=a.output/'brand.cpp';data=a.art.read_bytes()
brand.write_text('#include <cstddef>\nextern const unsigned char gowBrandImage[]={'+','.join(map(str,data))+'};\nextern const std::size_t gowBrandImageSize=sizeof(gowBrandImage);\n')
exe=a.output/'game-menu.exe'
env=os.environ.copy();env['PATH']=str(a.compiler.resolve().parent)+os.pathsep+env.get('PATH','');env['TOBIICHI_IDIOMA']='pt';env['GOW_ACTIVE_MODS']='example.texture @ 1.0;example.visual @ 2.0'
subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-static','-ffunction-sections','-fdata-sections','-Wno-deprecated-declarations','-I'+str(a.runtime/'include'),'-I'+str(a.runtime.parent/'ps2xIOP/include'),'-I'+str(a.raylib),str(source),str(brand),str(a.raylib_lib),'-Wl,--gc-sections','-lopengl32','-lgdi32','-lwinmm','-o',str(exe)],env=env,check=True)
subprocess.run([str(exe.resolve()),str(a.background.resolve()),str(a.output.resolve())],env=env,check=True)
