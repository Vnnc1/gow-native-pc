"""Compile the production altar completion wrapper and real backup publisher without game data."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime',type=Path,required=True)
p.add_argument('--compiler',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('render-delivery-tests.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
source=(a.runtime.parent.parent/'src/gow_overrides.cpp').read_text(encoding='utf-8')
assert 'runtime.replaceFunction(0x0022E800u, gowAltarSaveWrite);' in source
wrapper=m.extract(source,'void gowAltarSaveWrite(')
a.output.mkdir(parents=True,exist_ok=True)
cpp=a.output/'altar-save.cpp'; exe=a.output/'altar-save.exe'
cpp.write_text(Path(__file__).with_name('altar-save.cpp.in').read_text(encoding='utf-8').replace('@WRAPPER@',wrapper),encoding='utf-8')
env=os.environ.copy(); env['PATH']=str(a.compiler.resolve().parent)+os.pathsep+env.get('PATH','')
subprocess.run([str(a.compiler.resolve()),'-std=c++17','-O2','-static','-I'+str(a.runtime.resolve()/'include'),str(cpp),'-o',str(exe)],check=True,env=env,timeout=120)
with tempfile.TemporaryDirectory(prefix='altar-save-') as temporary:
    subprocess.run([str(exe.resolve()),temporary],check=True,env=env,timeout=30)
menu=(a.runtime/'src/lib/gow_trucos.cpp').read_text(encoding='utf-8')
body=m.extract(menu,'void gowTrucosMenuDibujar()')
notice=body[:body.index('    if (!g_menuAbierto.load')].replace('gowTrucosMenuDibujar','drawNotification')+'}\n'
cpp=a.output/'save-notification.cpp'; exe=a.output/'save-notification.exe'
cpp.write_text(Path(__file__).with_name('save-notification.cpp.in').read_text(encoding='utf-8').replace('@NOTIFICATION@',notice),encoding='utf-8')
subprocess.run([str(a.compiler.resolve()),'-std=c++17','-O2','-static','-I'+str(a.runtime.resolve()/'include'),str(cpp),'-o',str(exe)],check=True,env=env,timeout=120)
subprocess.run([str(exe.resolve())],check=True,env=env,timeout=30)
