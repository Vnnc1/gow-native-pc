"""Visible installed-runner startup/menu smoke with a private card and normal collector shutdown."""
import argparse,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('runner','collector','disc','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--startup',action='store_true')
a=p.parse_args();root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ab',root/'tools/test/gs-run-ab.py');ab=importlib.util.module_from_spec(spec);spec.loader.exec_module(ab)
profile=json.loads(subprocess.check_output([sys.executable,'-I',str(root/'tools/pipeline/profile.py'),'gow1']))
run=a.output.resolve();run.mkdir(parents=True,exist_ok=False);source=a.disc.resolve();card=source/'Mcd001.ps2';original=ab.worker.sha(card)
ab.private_disc(source,run/'disc',profile);shutil.copyfile(card,run/'disc/Mcd001.ps2')
env=ab.worker.environment(profile,run,argparse.Namespace(mode='fps',scale=1,hidden=False),0,pad_script='5:start,12:abajo*0.15,18:x,24:x,30:x')
env.update(GOW_MC0=str(run/'disc/Mcd001.ps2'),GOW_SAVES_DIR=str(run/'saves'),TOBIICHI_PANTALLA='ventana',TOBIICHI_IDIOMA='pt',GOW_VU1_FAST='0',GOW_GS_EARLY_FINISH='1',GOW_AUDIO_STATS='1')
if a.startup:
    env.pop('GOW_PAD_TEST');env.pop('GOW_FAST_BOOT');env.pop('GOW_SKIP_FMV');env.pop('GOW_PAD_GUION')
else:
    env.update(TOBIICHI_TRUCOS_ABRIR_EN='42',TOBIICHI_MENU_PESTANA='3',GOW_HOST_SHOT='3000',TOBIICHI_TECLAS='li_arriba=87;li_abajo=83;li_izq=65;li_der=68;cross=32;circle=70;square=1000;triangle=1001;start=257;select=258')
session=run/'session';session.mkdir();(session/'session.json').write_text(json.dumps({'schema':1,'id':run.name,'state':'prepared'}))
proc=subprocess.Popen([str(a.collector.resolve()),str(session),str(a.runner.resolve()),str(run/'disc'/profile['executable']['name']),str(run)],cwd=run,env=env)
try:
    until=time.monotonic()+(25 if a.startup else 65)
    while time.monotonic()<until and proc.poll() is None:time.sleep(.25)
    (session/'stop.request').write_text('stop');assert proc.wait(timeout=30)==0
finally:
    if proc.poll() is None:(session/'stop.request').write_text('stop');proc.wait(timeout=30)
    assert ab.worker.sha(card)==original,'Original card changed'
meta=json.loads((session/'session.json').read_text(encoding='utf-8'));log=(session/'runtime.log').read_text(encoding='utf-8')
assert meta['state']=='completed' and meta['exit_code']==0,meta
assert ab.worker.sha(run/'disc/Mcd001.ps2')==original
assert '[SPU2]' in log,'No audio initialization evidence'
if not a.startup:
    assert '[gow-pad2:test] gameplay start' in log,'Gameplay not reached'
    assert (run/'host_shot.png').is_file(),'No final-host menu capture'
result={'startup':a.startup,'runner_sha256':ab.worker.sha(a.runner),'original_card_sha256':original,'private_card_unchanged':True,'exit_code':0,'audio_initialized':True}
(run/'result.json').write_text(json.dumps(result,indent=2));print('PASS:',json.dumps(result))
