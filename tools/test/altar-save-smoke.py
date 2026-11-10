"""Private-card USA altar save/load/cancel/failure integration; inspect generated gameplay captures.

Requires a card whose first slot loads at an altar (the supplied local card does).
Uses the deployed collector for normal shutdown, never overwrites the source card.
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
    p.add_argument('--card',type=Path)
    p.add_argument('--mode',choices=('save','load','cancel','failure'),default='save')
    p.add_argument('--seconds',type=int,default=75)
    a=p.parse_args()
    if a.seconds<60 or a.seconds>180: p.error('Use 60–180 seconds')
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('ab',root/'tools/test/gs-run-ab.py')
    ab=importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
    profile=json.loads(subprocess.check_output([sys.executable,'-I',str(root/'tools/pipeline/profile.py'),'gow1']))
    source=a.disc.resolve(); card=(a.card or source/'Mcd001.ps2').resolve(); original=ab.worker.sha(card)
    run=a.output.resolve(); run.mkdir(parents=True,exist_ok=False)
    disc=run/'disc'; ab.private_disc(source,disc,profile); shutil.copyfile(card,disc/'Mcd001.ps2')
    script='5:start,12:abajo*0.15,18:x,24:x,30:x'
    if a.mode in ('save','failure'): script+=',g4:r2,g7:x,g9:x,g11:arriba*0.15,g12.5:x'
    elif a.mode=='cancel': script+=',g4:r2,g7:abajo*0.15,g9:x'
    env=ab.worker.environment(profile,run,argparse.Namespace(mode='fps',scale=1,hidden=False),0,pad_script=script)
    env.update(GOW_MC0=str(disc/'Mcd001.ps2'),GOW_SAVES_DIR=str(run/'saves'),TOBIICHI_PANTALLA='ventana',
               TOBIICHI_IDIOMA='pt',GOW_VU1_FAST='0',GOW_GS_EARLY_FINISH='1',GOW_PAD_TEST_NO_CAPTURE='0',
               GOW_PAD_CAPTURAS='g2,g8,g14,g18,g22')
    if a.mode=='failure': (run/'saves').write_text('destination is deliberately a file')
    session=run/'session'; session.mkdir()
    (session/'session.json').write_text(json.dumps({'schema':1,'id':run.name,'state':'prepared'}))
    proc=subprocess.Popen([str(a.collector.resolve()),str(session),str(a.runner.resolve()),
                           str(disc/profile['executable']['name']),str(run)],cwd=run,env=env)
    try:
        until=time.monotonic()+a.seconds
        while time.monotonic()<until and proc.poll() is None: time.sleep(0.25)
        (session/'stop.request').write_text('stop')
        assert proc.wait(timeout=25)==0, 'collector/child failed'
    finally:
        if proc.poll() is None:
            (session/'stop.request').write_text('stop'); proc.wait(timeout=25)
        assert ab.worker.sha(card)==original, 'source card changed'
    metadata=json.loads((session/'session.json').read_text(encoding='utf-8'))
    assert metadata.get('state')=='completed' and metadata.get('exit_code')==0, metadata
    copies=list((run/'saves').glob('*/Mcd001.ps2')) if a.mode!='failure' else []
    after=ab.worker.sha(disc/'Mcd001.ps2')
    if a.mode=='save':
        assert len(copies)==1 and ab.worker.sha(copies[0])==after and after!=original
        info=json.loads(copies[0].with_name('save.json').read_text(encoding='utf-8'))
        assert info['source']=='auto' and info['bytes']==copies[0].stat().st_size
    elif a.mode in ('load','cancel'): assert not copies and after==original
    else: assert not copies and after!=original and (run/'saves').is_file()
    assert list(run.glob('gow_pad_test_*.ppm')), 'missing gameplay capture'
    result={'mode':a.mode,'runner_sha256':ab.worker.sha(a.runner),'source_card_sha256':original,
            'final_card_sha256':after,'backups':len(copies),'exit_code':0}
    (run/'result.json').write_text(json.dumps(result,indent=2))
    print('PASS:',json.dumps(result))

if __name__=='__main__': main()
