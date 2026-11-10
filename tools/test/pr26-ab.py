"""Exploratory same-binary PR 26 A/B, with private cards and frames-only timing.

This does not certify scene equivalence, whole-game support, or another PC's FPS.
Captures and intrusive audio counters belong to a separate smoke run.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location('worker', Path(__file__).with_name('worker-ab.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

SWITCHES = ('GOW_GS_HW_RING', 'GOW_GS_STATE_CACHE', 'GOW_GS_TEXREUSE',
            'PS2X_GS_RUN', 'PS2X_GS_RUN_STATE_FAST', 'PS2X_GS_COMPACT_QUEUE',
            'GOW_VU1_CHAIN_WARM')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runner', type=Path, required=True)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--helper', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--game', default='gow1')
    p.add_argument('--switch', choices=SWITCHES + ('bundle',), default='bundle')
    p.add_argument('--pairs', type=int, default=3)
    p.add_argument('--seconds', type=int, default=100)
    p.add_argument('--warmup', type=int, default=50)
    p.add_argument('--scale', type=float, default=1)
    p.add_argument('--hidden', action='store_true')
    p.add_argument('--smoke', action='store_true', help='One visible/audio/capture run, not an FPS comparison')
    a = p.parse_args()
    if not (1 <= a.pairs <= 10 and 30 <= a.warmup < a.seconds - 20 <= 580 and 0.25 <= a.scale <= 4):
        p.error('Require 1-10 pairs, >=30 s warmup, >20 s measurement, <=600 s total, scale 0.25-4')
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(subprocess.check_output([sys.executable, '-I', str(root / 'tools/pipeline/profile.py'), a.game]))
    region = worker.region_for_elf(profile, a.elf)
    pc = (region or {}).get('experimental_frame_pc') or profile['diagnostics']['frame_pc']
    script = worker.regional_pad_script(profile['optimize']['pad_script'], (region or {}).get('experimental_menu_confirm'))
    identity = {name: worker.sha(path) for name, path in [('runner', a.runner), ('elf', a.elf), ('helper', a.helper)]}
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    report = {'identity': identity, 'settings': vars(a), 'scope': __doc__, 'runs': []}
    def save():
        (a.output / 'summary.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    save()
    a.mode = 'fps'
    variants = [1] if a.smoke else [v for i in range(a.pairs) for v in ((0, 1) if i % 2 == 0 else (1, 0))]
    for index, variant in enumerate(variants):
        if worker.sha(a.runner) != identity['runner'] or worker.sha(a.elf) != identity['elf']:
            raise RuntimeError('Binary or ELF changed during the comparison')
        run = a.output / f'{index+1:02d}-{variant}'
        session = run / 'session'
        session.mkdir(parents=True)
        env = worker.environment(profile, run, a, 1, pc, script)
        env.update(GOW_GS_EARLY_FINISH='1', GOW_VU1_FAST='0')
        keys = SWITCHES if a.switch == 'bundle' else (a.switch,)
        env.update({key: str(variant) for key in keys})
        if a.smoke:
            env.update(GOW_PAD_TEST_NO_CAPTURE='0', GOW_PAD_CAPTURAS='10,80',
                       GOW_AUDIO_STATS='1', GOW_IOP_DRIFT='1')
        settings = {'variant': variant, 'switches': {key: env[key] for key in keys}, 'smoke': a.smoke}
        (session / 'session.json').write_text(json.dumps({'schema': 1, 'id': run.name, 'state': 'prepared', 'settings': settings}))
        print(f'Run {index+1}/{len(variants)}: {settings}, {a.seconds}s', flush=True)
        proc = subprocess.Popen([str(a.helper.resolve()), str(session), str(a.runner.resolve()), str(a.elf.resolve()), str(root)], cwd=run, env=env)
        try:
            deadline = time.monotonic() + a.seconds
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.25)
        finally:
            if proc.poll() is None:
                (session / 'stop.request').write_text('stop')
                proc.wait(timeout=25)
        meta = json.loads((session / 'session.json').read_text())
        rows = [json.loads(line) for line in (session / 'metrics.jsonl').read_text().splitlines()]
        events = [json.loads(line) for line in (session / 'events.jsonl').read_text().splitlines()]
        log = '\n'.join(path.read_text(encoding='utf-8', errors='replace') for path in session.glob('runtime*.log'))
        summary = worker.summarize(rows, a.warmup)
        frame_rows = [r['values'] for r in rows if r.get('tag') == 'gow-frame' and
                      r['elapsed_ms'] / 1000 - r['values'].get('window', 0) >= a.warmup]
        summary['median_window_p99_ms'] = statistics.median(v['p99_ms'] for v in frame_rows) if frame_rows else None
        checks = {'exit_zero': meta.get('exit_code') == 0,
                  'graceful': not any(e['type'] == 'forced_termination' for e in events),
                  'gameplay': bool(re.search(r'state=11\b.*levelReady=1|gameplay start at', log)),
                  'windows': summary['windows'] >= 3}
        report['runs'].append({'directory': str(run), **settings, **summary, 'checks': checks})
        save()
        print(json.dumps(report['runs'][-1]), flush=True)
        if not all(checks.values()):
            raise RuntimeError(f'Run did not satisfy gameplay gates: {checks}')
    report['completed'] = True
    if not a.smoke:
        report['mean_run_guest_fps'] = {str(v): statistics.mean(r['guest_fps'] for r in report['runs'] if r['variant'] == v) for v in (0, 1)}
    save()


if __name__ == '__main__':
    main()
