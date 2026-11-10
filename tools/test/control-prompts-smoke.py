"""Capture the final host image with mapped prompts, using a private card and scripted input.

Style selection is test-only: this validates rendering, not physical controller detection.
Inspect host_shot.png; guest GS captures do not include the prompt overlay.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('runner','collector','disc','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--style',choices=('keyboard','xbox','ps4','dualsense'),default='keyboard')
    p.add_argument('--seconds',type=int,default=25)
    p.add_argument('--shot',type=int,default=950)
    p.add_argument('--script',default='5:start')
    p.add_argument('--remap',action='store_true')
    p.add_argument('--require-gameplay',action='store_true')
    a=p.parse_args()
    if not 10<=a.seconds<=180 or not 0<=a.shot<=10000: p.error('Use 10–180 seconds and shot 0–10000')
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('ab',root/'tools/test/gs-run-ab.py')
    ab=importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
    profile=json.loads(subprocess.check_output([sys.executable,'-I',str(root/'tools/pipeline/profile.py'),'gow1']))
    source=a.disc.resolve(); original=ab.worker.sha(source/'Mcd001.ps2')
    run=a.output.resolve(); run.mkdir(parents=True,exist_ok=False)
    ab.private_disc(source,run/'disc',profile)
    shutil.copyfile(source/'Mcd001.ps2',run/'disc/Mcd001.ps2')
    env=ab.worker.environment(profile,run,argparse.Namespace(mode='fps',scale=1,hidden=False),0,pad_script=a.script)
    env.update(GOW_MC0=str(run/'disc/Mcd001.ps2'),GOW_SAVES_DIR=str(run/'saves'),TOBIICHI_PANTALLA='ventana',
               TOBIICHI_IDIOMA='pt',GOW_VU1_FAST='0',GOW_GS_EARLY_FINISH='1',GOW_HOST_SHOT=str(a.shot),
               GOW_PROMPT_TEST_STYLE=str(('keyboard','xbox','ps4','dualsense').index(a.style)+1))
    if a.remap:
        env.update(TOBIICHI_TECLAS='cross=75;circle=1001;square=1000;triangle=71;l1=341;r1=69;start=257;select=258',
                   TOBIICHI_MANDO='cross=5;circle=7;square=6;triangle=8;l1=12;r1=9;start=15;select=13')
    session=run/'session'; session.mkdir()
    (session/'session.json').write_text(json.dumps({'schema':1,'id':run.name,'state':'prepared'}))
    proc=subprocess.Popen([str(a.collector.resolve()),str(session),str(a.runner.resolve()),
                           str(run/'disc'/profile['executable']['name']),str(run)],cwd=run,env=env)
    try:
        until=time.monotonic()+a.seconds
        while time.monotonic()<until and proc.poll() is None: time.sleep(.25)
        (session/'stop.request').write_text('stop'); assert proc.wait(timeout=25)==0
    finally:
        if proc.poll() is None:
            (session/'stop.request').write_text('stop'); proc.wait(timeout=25)
        assert ab.worker.sha(source/'Mcd001.ps2')==original, 'source card changed'
    meta=json.loads((session/'session.json').read_text(encoding='utf-8'))
    assert meta.get('state')=='completed' and meta.get('exit_code')==0, meta
    assert (run/'host_shot.png').is_file(), 'missing host capture'
    if a.require_gameplay:
        assert '[gow-pad2:test] gameplay start' in (session/'runtime.log').read_text(encoding='utf-8'), 'gameplay not reached'
    result={'style':a.style,'remapped':a.remap,'script':a.script,'simulated_style':True,
            'runner_sha256':ab.worker.sha(a.runner),'source_card_sha256':original,'exit_code':0}
    (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS:',json.dumps(result))

if __name__=='__main__': main()
