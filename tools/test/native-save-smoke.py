"""Load native slots through the host request bridge, with a private card/disc.

Includes startup selection and a request while the host menu pauses gameplay.
Never restores or writes the player's source card.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

p = argparse.ArgumentParser(description=__doc__)
for name in ('runner', 'collector', 'disc', 'output'):
    p.add_argument('--' + name, required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ab', root / 'tools/test/gs-run-ab.py')
ab = importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
sys.path.insert(0, str(root / 'tools/disc'))
import save_slots
profile = json.loads(subprocess.check_output([sys.executable, '-I', str(root / 'tools/pipeline/profile.py'), 'gow1']))
run = a.output.resolve(); run.mkdir(parents=True, exist_ok=False)
source = a.disc.resolve(); original = (source / 'Mcd001.ps2').read_bytes()
assert [s['slot'] for s in save_slots.slots(original, profile['saves']['directory'])] == [0, 1, 2, 3], 'Four occupied slots required'
ab.private_disc(source, run / 'disc', profile)
(run / 'disc/Mcd001.ps2').write_bytes(original)
save_slots.prepare_assets(run / 'disc', profile, 'pt-br')
settings = run / 'menu-settings'; settings.mkdir()
(settings / 'load.request').write_bytes(b'0\n')
env = ab.worker.environment(profile, run, argparse.Namespace(mode='fps', scale=1, hidden=False), 0, pad_script='5:start')
env.update(GOW_MC0=str(run / 'disc/Mcd001.ps2'), GOW_SAVES_DIR=str(run / 'saves'),
           GOW_SAVE_ASSETS=str(run / 'disc/.gow-save-slots'), GOW_MENU_SETTINGS=str(settings),
           TOBIICHI_PANTALLA='ventana', TOBIICHI_IDIOMA='pt', GOW_PLAYER_TRACE='1',
           GOW_AUDIO_STATS='1', TOBIICHI_TRUCOS_ABRIR_EN='48', TOBIICHI_MENU_PESTANA='2', GOW_HOST_SHOT='8000')
session = run / 'session'; session.mkdir()
(session / 'session.json').write_text(json.dumps({'schema':1,'id':run.name,'state':'prepared'}))
proc = subprocess.Popen([str(a.collector.resolve()), str(session), str(a.runner.resolve()),
                         str(run / 'disc' / profile['executable']['name']), str(run)], cwd=run, env=env)
begin = time.monotonic(); requests = [(55, 2), (95, 3), (130, 0)]
try:
    while proc.poll() is None and time.monotonic() - begin < 175:
        if requests and time.monotonic() - begin >= requests[0][0]:
            _, slot = requests.pop(0)
            temp = settings / 'pending'; temp.write_bytes(f'{slot}\n'.encode('ascii')); temp.replace(settings / 'load.request')
        time.sleep(.25)
finally:
    if proc.poll() is None:
        (session / 'stop.request').write_text('stop')
        proc.wait(timeout=30)
meta = json.loads((session / 'session.json').read_text())
log = (session / 'runtime.log').read_text(encoding='utf-8')
assert meta['state'] == 'completed' and meta['exit_code'] == 0, meta
assert (source / 'Mcd001.ps2').read_bytes() == original, 'Source card changed'
assert (run / 'disc/Mcd001.ps2').read_bytes() == original, 'Private card changed'
assert log.count('[native-load] result 1') == 4, 'Not all four loads completed'
assert log.count('[native-load] quit gameplay to native frontend') == 3, 'Gameplay transitions missing'
assert '[SPU2]' in log and 'state=11' in log, 'Gameplay/audio evidence missing'
result = {'loads':4,'exit_code':0,'private_and_source_card_unchanged':True,
          'runner_sha256':hashlib.sha256(a.runner.read_bytes()).hexdigest()}
(run / 'result.json').write_text(json.dumps(result, indent=2))
print('PASS:', result)
