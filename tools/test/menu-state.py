"""Compile and run production menu persistence/pause helpers with isolated Qt settings."""
import argparse, os, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('runtime','compiler','qt','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[2];a.output.mkdir(parents=True,exist_ok=True)
exe=a.output/'menu-state.exe'
env=os.environ|{'PATH':str(a.compiler.resolve().parent)+os.pathsep+str(a.qt.resolve()/'bin')+os.pathsep+os.environ.get('PATH','')}
subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-Wno-deprecated-declarations','-Wno-ignored-attributes','-I'+str(root/'launcher/src'),'-I'+str(a.runtime.resolve()/'include'),'-I'+str(a.qt.resolve()/'include'),'-I'+str(a.qt.resolve()/'include/QtCore'),str(root/'tools/test/menu-state.cpp'),'-L'+str(a.qt.resolve()/'lib'),'-lQt6Core','-o',str(exe)],env=env,check=True)
subprocess.run([str(exe.resolve())],env=env,check=True,timeout=20)

import importlib.util
spec=importlib.util.spec_from_file_location('extract',root/'tools/test/render-delivery-tests.py')
extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
callback=extract.extract((a.runtime/'src/lib/ps2_runtime.cpp').read_text(encoding='utf-8'),'void spu2AudioCallback(')
cpp=a.output/'menu-audio.cpp';cpp.write_text((root/'tools/test/menu-audio.cpp.in').read_text(encoding='utf-8').replace('@CALLBACK@',callback),encoding='utf-8')
exe=a.output/'menu-audio.exe'
subprocess.run([str(a.compiler.resolve()),'-std=c++20','-O2','-static','-I'+str(a.runtime.resolve()/'include'),str(cpp),'-o',str(exe)],env=env,check=True)
subprocess.run([str(exe.resolve())],env=env,check=True,timeout=20)
