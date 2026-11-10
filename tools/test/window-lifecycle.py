"""Windows real-game regression: private disc/card, minimize/restore, collector stop.

Requires a desktop/GPU and a prepared compatible disc. This is a lifecycle test,
not an FPS benchmark. The runner and collector must already be built.
"""
import argparse
import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--collector', type=Path, required=True)
    parser.add_argument('--disc', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=('visible', 'minimize', 'restore'), default='minimize')
    parser.add_argument('--warmup', type=int, default=40)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Windows desktop required')
    if args.warmup < 30:
        parser.error('warmup must be at least 30 seconds')
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('gs_ab', root / 'tools/test/gs-run-ab.py')
    ab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ab)
    profile = json.loads(subprocess.check_output([sys.executable, '-I', str(root / 'tools/pipeline/profile.py'), 'gow1']))
    source = args.disc.resolve()
    card = source / 'Mcd001.ps2'
    card_hash = ab.worker.sha(card)
    run = args.output.resolve()
    run.mkdir(parents=True, exist_ok=False)
    disc = run / 'disc'
    ab.private_disc(source, disc, profile)
    shutil.copyfile(card, disc / 'Mcd001.ps2')
    session = run / 'session'
    session.mkdir()
    (session / 'session.json').write_text(json.dumps({'schema': 1, 'id': run.name, 'state': 'prepared'}))
    settings = argparse.Namespace(mode='fps', scale=2, hidden=False)
    env = ab.worker.environment(profile, run, settings, 0,
                                pad_script=profile['diagnostics']['scenes']['ship_guard']['pad_script'])
    env.update(GOW_MC0=str(disc / 'Mcd001.ps2'), GOW_SAVES_DIR=str(disc / 'saves'),
               GOW_GS_EARLY_FINISH='1', GOW_ANISO='1', GOW_AUDIO_STATS='1',
               TOBIICHI_FXAA='1', TOBIICHI_PANTALLA='ventana', GOW_VU1_FAST='0',
               GOW_PLAYER_TRACE='1', GOW_GOD_MODE='1')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
    child = subprocess.Popen([str(args.collector.resolve()), str(session), str(args.runner.resolve()),
                              str(disc / profile['executable']['name']), str(run)], cwd=run, env=env)
    evidence = {'action': args.action, 'runner_sha256': ab.worker.sha(args.runner), 'events': []}
    started = time.monotonic()
    try:
        time.sleep(args.warmup)
        # Query only this collector's child; never act on a window by title.
        command = f'Get-CimInstance Win32_Process -Filter "ParentProcessId = {child.pid}" | Select-Object -ExpandProperty ProcessId'
        pid = int(subprocess.check_output(['powershell', '-NoProfile', '-Command', command]).strip())
        windows = []

        @callback
        def collect(handle, unused):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value == pid and user32.IsWindowVisible(handle):
                windows.append(handle)
            return True

        user32.EnumWindows(collect, 0)
        assert len(windows) == 1, f'Expected one visible child window, got {len(windows)}'
        window = windows[0]
        if args.action != 'visible':
            assert user32.ShowWindowAsync(window, 6), 'Minimize request failed'
            time.sleep(2)
            assert user32.IsIconic(window), 'Window did not minimize'
            evidence['events'].append({'action': 'minimized', 'seconds': time.monotonic() - started})
        for _ in range(20):
            time.sleep(0.5)
            if args.action != 'visible' and not user32.IsIconic(window):
                evidence['events'].append({'action': 'unexpected_restore', 'seconds': time.monotonic() - started})
                raise AssertionError('Window restored during the minimized test; discard this run')
        if args.action == 'restore':
            assert user32.ShowWindowAsync(window, 9), 'Restore request failed'
            time.sleep(2)
            assert not user32.IsIconic(window), 'Window did not restore'
            evidence['events'].append({'action': 'restored', 'seconds': time.monotonic() - started})
            time.sleep(10)
        evidence['events'].append({'action': 'stop_requested', 'seconds': time.monotonic() - started})
        (session / 'stop.request').write_text('stop')
        child.wait(timeout=30)
        meta = json.loads((session / 'session.json').read_text())
        events = [json.loads(line) for line in (session / 'events.jsonl').read_text().splitlines()]
        rows = [json.loads(line) for line in (session / 'metrics.jsonl').read_text().splitlines()]
        evidence.update(exit_code=meta.get('exit_code'), state=meta.get('state'),
                        forced=any(e['type'] == 'forced_termination' for e in events))
        evidence['present_windows'] = [r for r in rows if r.get('tag') == 'gow-present']
        assert ab.worker.sha(card) == card_hash, 'Original card changed'
        assert not evidence['forced'] and evidence['exit_code'] == 0, evidence
        assert evidence['present_windows'], 'No host acquisition reports'
        if args.action != 'visible':
            minimized_at = evidence['events'][0]['seconds']
            assert any(r['elapsed_ms'] / 1000 - r['values']['window'] >= minimized_at
                       and r['elapsed_ms'] / 1000 <= minimized_at + 10
                       for r in evidence['present_windows']), 'No complete host window while minimized'
        print('PASS:', args.action, 'normal exit and host progress; original card preserved')
    finally:
        if child.poll() is None:
            (session / 'stop.request').write_text('stop')
            child.wait(timeout=30)
        (run / 'result.json').write_text(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
