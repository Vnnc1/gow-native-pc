"""Compile production input/label regressions and the existing QTE input suite."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
for name in ('runtime','compiler','raylib','output'): p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('render-delivery-tests.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s=(a.runtime/'src/lib/gow_iconos.cpp').read_text(encoding='utf-8')
labels='\n'.join((s[s.index('    enum Boton'):s.index('    enum Variante')],
                  s[s.index('    enum Variante'):s.index('    struct Pelicula')],
                  s[s.index('    enum Estilo'):s.index('    Font g_fuente')],
                  m.extract(s,'std::string nombreTecla('),m.extract(s,'std::string rotulo('),
                  m.extract(s,'bool colorDeBoton('),m.extract(s,'bool rotuloDeBoton('),
                  s[s.index('    struct Icono'):s.index('    void anotar(')],m.extract(s,'void anotar('),
                  'bool g_activo=true; int g_anterior=0; void cerrarRotulo() {}',m.extract(s,'void gowIconosFrame(')))
a.output.mkdir(parents=True,exist_ok=True)
cpp=a.output/'control-prompts.cpp'
cpp.write_text(Path(__file__).with_name('control-prompts.cpp.in').read_text(encoding='utf-8').replace('@LABELS@',labels),encoding='utf-8')
env=os.environ.copy(); env['PATH']=str(a.compiler.resolve().parent)+os.pathsep+env.get('PATH','')
for source,modes in ((cpp,['default','custom']),(Path(__file__).with_name('qte_input_test.cpp'),['off','shake','rotate','smoke'])):
    exe=a.output/(source.stem+'.exe')
    subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-static',
                    '-I'+str(a.runtime.resolve()/'include'),'-I'+str(a.raylib.resolve()),
                    str(source),str(a.runtime/'src/lib/ps2_pad.cpp'),'-o',str(exe)],check=True,env=env,timeout=120)
    for mode in modes: subprocess.run([str(exe.resolve()),mode],check=True,env=env,timeout=30)
visibility=a.output/'control-prompt-visibility.cpp'
visibility.write_text(Path(__file__).with_name('control-prompt-visibility.cpp.in').read_text(encoding='utf-8').replace('@DRAW@',m.extract(s,'void dibujarForma(')),encoding='utf-8')
exe=a.output/'control-prompt-visibility.exe'
subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-static',str(visibility),'-o',str(exe)],check=True,env=env,timeout=120)
subprocess.run([str(exe.resolve())],check=True,env=env,timeout=30)
