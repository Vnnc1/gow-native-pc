"""Compile the production load hooks with observing guest-call fixtures."""
import argparse
import importlib.util
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
for name in ('runtime','compiler','output'):
    p.add_argument('--' + name, required=True, type=Path)
a = p.parse_args()
spec = importlib.util.spec_from_file_location('extract', Path(__file__).with_name('render-delivery-tests.py'))
extract = importlib.util.module_from_spec(spec); spec.loader.exec_module(extract)
source = (a.runtime.parent.parent / 'src/gow_overrides.cpp').read_text(encoding='utf-8')
hooks = '\n'.join(extract.extract(source, 'void ' + name + '(') for name in ('nativeLoadGameplay','nativeLoadFrontend','nativeLoadUpdate'))
a.output.mkdir(parents=True, exist_ok=True)
cpp = a.output / 'native-load.cpp'; exe = a.output / 'native-load.exe'
cpp.write_text('''#include "runtime/gow_native_load.h"
#include <cassert>
#include <cstdio>
#include <cstring>
struct R5900Context {uint32_t pc=0,reg[32]{};};struct PS2Runtime{};
#define GPR_U32(c,i) ((c)->reg[i])
uint32_t readGuest32(const uint8_t*r,uint32_t p){uint32_t v;std::memcpy(&v,r+p,4);return v;}
void writeGuest32(uint8_t*r,uint32_t p,uint32_t v){std::memcpy(r+p,&v,4);}
int original=0,quit=0,loadResult=0,nativeLoadSlot=-1;
void sub_0021F3C8_0x21f3c8(uint8_t*,R5900Context*c,PS2Runtime*){++original;c->pc=c->reg[31];}
void sub_0021D868_0x21d868(uint8_t*,R5900Context*c,PS2Runtime*){++quit;c->pc=c->reg[31];}
void sub_0021EBF8_0x21ebf8(uint8_t*,R5900Context*c,PS2Runtime*){++original;c->pc=c->reg[31];}
void sub_0022F5E0_0x22f5e0(uint8_t*,R5900Context*c,PS2Runtime*){++original;c->pc=0x21EDE8;c->reg[2]=loadResult;}
''' + hooks + '''
int main(){std::vector<uint8_t> memory(32*1024*1024);auto r=memory.data();R5900Context c;PS2Runtime rt;
auto put=[&](uint32_t p,uint32_t v){writeGuest32(r,p,v);};auto get=[&](uint32_t p){return readGuest32(r,p);};
c.reg[31]=0x1234;put(0x29E560,12);put(0x29CB94,0x100000);gow_native_load::request.store(3);
c.pc=0x21F3C8;nativeLoadGameplay(r,&c,&rt);assert(!quit&&gow_native_load::request.load()==3);
put(0x29E560,11);put(0x1001a8,99);c.pc=0x21F3C8;nativeLoadGameplay(r,&c,&rt);
assert(quit==1&&nativeLoadSlot==2&&!gow_native_load::request.load()&&get(0x1001a8)==0&&c.pc==0x1234);
put(0x29E560,3);c.pc=0x21EBF8;nativeLoadFrontend(r,&c,&rt);assert(get(0x100278)==2&&get(0x10027c)==1);
put(0x100274,0);put(0x2A12B0,8);put(0x2A1290,0xffffffff);put(0x35BE80+32,2);put(0x35BE80+36,0xcafebad1);
c.pc=0x22F5E0;nativeLoadUpdate(r,&c,&rt);assert(get(0x2A1290)==3&&nativeLoadSlot==2);
put(0x2A1290,0xffffffff);c.pc=0x22FA70;nativeLoadUpdate(r,&c,&rt);assert(get(0x2A1290)==0xffffffff);
put(0x2A12A4,1);c.pc=0x22F5E0;nativeLoadUpdate(r,&c,&rt);assert(get(0x2A1290)==0);
put(0x2A12A4,0);put(0x2A1290,0xffffffff);
put(0x35BE80+36,0);c.pc=0x22F5E0;nativeLoadUpdate(r,&c,&rt);assert(get(0x2A1290)==0);
loadResult=-1;c.pc=0x22F5E0;nativeLoadUpdate(r,&c,&rt);assert(nativeLoadSlot==-1&&gow_native_load::status.load()==-1);
nativeLoadSlot=2;loadResult=1;c.pc=0x22F5E0;nativeLoadUpdate(r,&c,&rt);assert(nativeLoadSlot==-1&&gow_native_load::status.load()==2);
std::puts("PASS: gameplay gates, native teardown, frontend selection, index validation, resume delegation and completion/error status");}
''', encoding='utf-8')
subprocess.run([str(a.compiler.absolute()), '-std=c++17', '-O2', '-static', '-I' + str(a.runtime.resolve() / 'include'),
                str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe.resolve())], check=True)
