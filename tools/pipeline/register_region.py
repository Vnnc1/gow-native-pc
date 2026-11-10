"""Register an already built, isolated regional installation without changing USA data."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/disc'))
sys.path.insert(0, str(ROOT / 'tools/pipeline'))
from discfs import text_sha1, pcsx2_crc
from recompile import atomic_json, digest


def register(root, game, region_id, runner, elf, data):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', game) or not re.fullmatch(r'[a-zA-Z0-9_-]+', region_id):
        raise ValueError('Invalid game or region identifier')
    root, runner, elf, data = (Path(p).resolve() for p in (root, runner, elf, data))
    profile_path = root / 'games' / game / 'game.toml'
    profile = tomllib.loads(profile_path.read_text(encoding='utf-8'))
    region = next(r for r in profile['regions'] if r['id'] == region_id)
    # A region with `code` carries that region's executable (the Asia SCAJ-97399 disc boots the Japanese copy
    # byte for byte): it shares the named region's overlay, build and measured identity, and keeps its own disc,
    # runner registration and saves.
    target = next((r for r in profile['regions'] if r['id'] == region.get('code')), None) if region.get('code') else None
    build = target or region
    if region.get('demo') or not (root / 'games' / game / 'regions' / build['id'] / 'runtime.patch').is_file():
        raise ValueError('No validated regional overlay for this edition')
    payload = elf.read_bytes()
    if (elf.name != build['elf'] or text_sha1(payload) != build['known_text_sha1']
            or pcsx2_crc(payload) != build['known_crc']):
        raise ValueError('Regional ELF identity mismatch')
    if not (elf.parent / '.disc_layout').is_file() or not (elf.parent / 'IOP_MOD').is_dir():
        raise ValueError('Prepare and normalize the regional disc before registration')
    cache = (runner.parent.parent / 'CMakeCache.txt').read_text(encoding='utf-8')
    source = next((Path(line.split('=', 1)[1]).resolve() for line in cache.splitlines()
                   if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL=')), None)
    if source is None:
        raise ValueError('Build cache has no CMAKE_HOME_DIRECTORY; reconfigure the regional build before registering')
    if source == (root / 'engine/runtime/PS2Recomp').resolve():
        raise ValueError('A regional ELF must never use the USA build')
    overrides = (source.parent / 'src/gow_overrides.cpp').read_text(encoding='utf-8')
    if build['elf'] not in overrides or profile['executable']['name'] in overrides:
        raise ValueError('Build source does not match the selected region')
    manifest_path = root / 'data' / game / 'regional-builds.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'schema': 1, 'owner': root.as_posix(), 'builds': []}
    if Path(manifest['owner']).resolve() != root:
        raise ValueError('Regional registry belongs to another checkout')
    if data == (root / 'data' / game).resolve():
        raise ValueError('Regional saves and captures must not share the USA data directory')
    for existing in manifest['builds']:
        if existing['region'] != region_id and any(Path(existing[key]).resolve() == path
                for key, path in (('dataDir', data), ('runner', runner), ('elf', elf))):
            raise ValueError('Regional installations must use separate runners, discs and data')
    entry = dict(region=region_id, label=region['label'], elf=elf.as_posix(), runner=runner.as_posix(),
                 source=source.as_posix(), dataDir=data.as_posix(),
                 framePc=build.get('experimental_frame_pc') or region.get('experimental_frame_pc'),
                 elf_crc=build['known_crc'], text_sha1=build['known_text_sha1'],
                 runner_sha256=digest(runner), elf_sha256=hashlib.sha256(payload).hexdigest(), quality='original')
    if target:
        entry['code'] = target['id']
    manifest['builds'] = [r for r in manifest['builds'] if r['region'] != region_id] + [entry]
    manifest['profile_sha256'] = digest(profile_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    atomic_json(manifest_path, manifest)
    return entry


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', default='gow1')
    parser.add_argument('--region', required=True)
    parser.add_argument('--runner', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(register(ROOT, args.game, args.region, args.runner, args.elf, args.data), indent=2))
    except (ValueError, OSError) as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(1)
