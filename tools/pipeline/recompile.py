"""Content-addressed EE generation and ownership-aware synchronization. Never cache game data outside data/.

The PowerShell pipeline holds the checkout lock. A successful generation is published as a directory transaction;
failed generation leaves the last usable output intact. Digests, not timestamps, decide reuse.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def replace_file(source, destination):
    # Windows scanners/indexers can briefly deny replacement despite writable files.
    # Keep the previous file intact and bound retries; persistent access errors still fail.
    for attempt in range(6):
        try:
            Path(source).replace(destination)
            return
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                raise
            time.sleep(0.05 * (2 ** attempt))


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    replace_file(temporary, path)


def inventory(folder):
    return {p.name: digest(p) for p in sorted(Path(folder).glob('*')) if p.is_file() and p.suffix in ('.cpp', '.h')}


def child(folder, name):
    folder = Path(folder).resolve()
    if Path(name).name != name or name in ('', '.', '..') or '\\' in name:
        raise ValueError(f'Unsafe generated filename: {name!r}')
    result = folder / name
    if result.is_symlink() or not result.resolve().is_relative_to(folder):
        raise ValueError(f'Generated path leaves its output directory: {result}')
    return result


def cache_valid(output, key):
    state = read_json(Path(output) / '.gow-recomp.json')
    return (state.get('schema') == 1 and state.get('key') == key and
            bool(state.get('outputs')) and state['outputs'] == inventory(output))


def publish(pending, output, key):
    pending, output = Path(pending), Path(output)
    if any(p.is_symlink() or p.is_junction() for p in (pending, output)) or pending.resolve().parent != output.resolve().parent:
        raise ValueError('Output publication requires ordinary sibling directories')
    files = inventory(pending)
    if not files or 'register_functions.cpp' not in files or 'ps2_recompiled_functions.h' not in files:
        raise RuntimeError('Recompiler output is incomplete; previous output was preserved')
    previous = inventory(output) if output.exists() else {}
    # Carry migration ownership until sync consumes it, including files removed by multiple recomp-only runs.
    retired = read_json(output / '.gow-recomp.json').get('previousOutputs', {}) | previous
    for name, value in files.items():
        if previous.get(name) == value:
            shutil.copystat(child(output, name), child(pending, name))
    atomic_json(pending / '.gow-recomp.json', dict(schema=1, key=key, outputs=files, previousOutputs=retired))
    backup = output.with_name(output.name + '.previous')
    if backup.exists():
        raise RuntimeError(f'Interrupted publication needs recovery: {backup}')
    if output.exists():
        output.rename(backup)
    try:
        pending.rename(output)
    except BaseException:
        if backup.exists():
            backup.rename(output)
        raise
    if backup.exists():
        # Exact sibling created above; reject junctions/symlinks before any recursive cleanup.
        if backup.is_symlink() or backup.is_junction() or backup.resolve().parent != output.resolve().parent:
            raise RuntimeError('Refusing to remove an output directory outside the generation root')
        shutil.rmtree(backup)


def generate(root, game, build, codegen, force=False):
    root = Path(root).resolve()
    profile_path = root / 'games' / game / 'game.toml'
    profile = tomllib.loads(profile_path.read_text(encoding='utf-8'))
    data = root / 'data' / game
    runtime = root / 'engine/runtime'
    folder = data / 'recomp'
    folder.mkdir(parents=True, exist_ok=True)
    elf = Path(read_json(data / 'languages.json')['recompile_elf']).resolve()
    compiler = Path(build).resolve() / 'ps2xRecomp/ps2_recomp.exe'
    function_map = runtime / profile['runtime']['function_map']
    template_path = runtime / profile['runtime']['recompiler_template']
    environment = {k: v for k, v in os.environ.items() if k.startswith('PS2X_')}
    environment['PS2X_CODEGEN'] = codegen
    inputs = [elf, compiler, function_map, template_path, profile_path, Path(__file__)]
    if environment.get('PS2X_CODEGEN_FUNCS'):
        filter_path = Path(environment['PS2X_CODEGEN_FUNCS']).resolve()
        environment['PS2X_CODEGEN_FUNCS'] = str(filter_path)
        inputs.append(filter_path)
    key_data = dict(files={str(p): digest(p) for p in inputs}, environment=environment)
    key = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    output = folder / 'out'
    start = time.perf_counter()
    if not force and cache_valid(output, key):
        print('@@status recompiler inputs and output hashes unchanged; generation skipped', flush=True)
        return dict(cacheHit=True, seconds=time.perf_counter() - start, files=len(inventory(output)))
    pending = Path(tempfile.mkdtemp(prefix='out.pending-', dir=folder))
    try:
        config = template_path.read_text(encoding='utf-8').replace('@ELF@', elf.as_posix())
        config = config.replace('@MAP@', function_map.as_posix()).replace('@OUT@', pending.as_posix() + '/')
        config_path = folder / 'recomp.toml'
        config_path.write_text(config, encoding='utf-8')
        logs = data / 'logs'
        logs.mkdir(exist_ok=True)
        print(f'@@status generating EE code ({codegen})', flush=True)
        with (logs / 'recomp.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(compiler), str(config_path)], env=os.environ | environment, cwd=folder,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        publish(pending, output, key)
    finally:
        if pending.exists() and pending.resolve().parent == folder.resolve() and not pending.is_junction() and not pending.is_symlink():
            shutil.rmtree(pending)
    return dict(cacheHit=False, seconds=time.perf_counter() - start, files=len(inventory(output)))


def sync_owned(sources, destination, state_path, previous=None):
    destination, state_path = Path(destination).resolve(), Path(state_path)
    destination.mkdir(parents=True, exist_ok=True)
    state = read_json(state_path)
    old = state.get('files', {}) if state.get('destination') == str(destination) else (previous or {})
    desired = {name: digest(path) for name, path in sources.items()}
    # Validate all removals before making changes. Never delete a hand-edited or foreign file.
    for name in old.keys() - desired.keys():
        path = child(destination, name)
        if path.exists() and digest(path) != old[name]:
            raise RuntimeError(f'Refusing to remove modified generated file: {path}')
    changed = 0
    for name, source in sources.items():
        target = child(destination, name)
        if target.exists() and digest(target) == desired[name]:
            continue
        temporary = target.with_name(target.name + '.gow-tmp')
        shutil.copy2(source, temporary)
        replace_file(temporary, target)
        changed += 1
    removed = 0
    for name in old.keys() - desired.keys():
        path = child(destination, name)
        if path.exists():
            path.unlink()
            removed += 1
    atomic_json(state_path, dict(schema=1, destination=str(destination), files=desired))
    return dict(changed=changed, removed=removed)


def synchronize(root, game):
    root = Path(root).resolve()
    folder = root / 'data' / game / 'recomp'
    output = folder / 'out'
    state = read_json(output / '.gow-recomp.json')
    if not state or inventory(output) != state.get('outputs'):
        raise RuntimeError('Generated output is missing or modified; run recomp before sync')
    runtime = root / 'engine/runtime'
    profile = tomllib.loads((root / 'games' / game / 'game.toml').read_text(encoding='utf-8'))
    result = {}
    for suffix, subdir in [('.cpp', 'src/runner'), ('.h', 'include')]:
        sources = {p.name: p for p in output.glob('*' + suffix)}
        if suffix == '.cpp':
            sources.update({Path(p).name: runtime / p for p in profile['runtime']['overrides']})
        previous = {k: v for k, v in state.get('previousOutputs', {}).items() if k.endswith(suffix)}
        result[suffix] = sync_owned(sources, runtime / 'PS2Recomp/ps2xRuntime' / subdir,
                                   folder / ('sync' + suffix + '.json'), previous)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['recomp', 'sync'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--game', default='gow1')
    parser.add_argument('--build', type=Path)
    parser.add_argument('--codegen', choices=['classic', 'locals'], default='locals')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if args.action == 'recomp':
        if not args.build:
            parser.error('--build is required for recomp')
        result = generate(args.root, args.game, args.build, args.codegen, args.force)
    else:
        result = synchronize(args.root, args.game)
    print(json.dumps(result))
    logs = args.root / 'data' / args.game / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    atomic_json(logs / (args.action + '-metrics.json'), result)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
