"""Render production prompt artwork/animated projection to a PNG using a hidden OpenGL window.

This is an explicit GPU check, not part of data-free verify or a combat QTE test.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
for name in ('runtime','compiler','raylib','raylib-lib','font-source','output'):
    p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('render-delivery-tests.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=(a.runtime/'src/lib/gow_iconos.cpp').read_text(encoding='utf-8')
types='\n'.join((s[s.index('    enum Boton'):s.index('    struct Pelicula')],
                 s[s.index('    enum Estilo'):s.index('    Font g_fuente')],
                 s[s.index('    struct Icono'):s.index('    std::mutex g_mutex')],
                 s[s.index('    struct Textura'):s.index('    const Textura &textura')]))
functions='\n'.join(m.extract(s,name) for name in (
    'uint32_t leer32(', 'float leerF(', 'bool valida(', 'bool worldCircleIcon(',
    'void cargarFuente(', 'Color colorXbox(', 'void textoCentrado(', 'void flecha(',
    'void dibujarRaton(', 'const Textura &textura(', 'void drawWorldBadge('))
a.output.mkdir(parents=True,exist_ok=True)
source=a.output/'render.cpp'
source.write_text(Path(__file__).with_suffix('.cpp.in').read_text(encoding='utf-8')
                  .replace('@TYPES@',types).replace('@FUNCTIONS@',functions),encoding='utf-8')
exe=a.output/'render.exe'
env=os.environ.copy();env['PATH']=str(a.compiler.resolve().parent)+os.pathsep+env.get('PATH','')
subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-static','-I'+str(a.raylib.resolve()),
                str(source),str(a.font_source.resolve()),str(a.raylib_lib.resolve()),
                '-lopengl32','-lgdi32','-lwinmm','-o',str(exe)],check=True,env=env,timeout=120)
subprocess.run([str(exe.resolve()),str((a.output/'xbox-style-sheet.png').resolve())],check=True,env=env,timeout=60)
