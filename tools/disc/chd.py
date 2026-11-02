"""CHD import boundary: verified tool download, locked cache and atomic ISO publication.

DVD CHDv5 and single-track MODE1/2048 CD CHDv5 are accepted. Cache identity uses
source metadata; the extracted ISO's SHA-256 is checked before reuse. Original
images are never modified. Cache files are local game data, never distributable.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def status(message):
    print(message, file=sys.stderr, flush=True)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+b') as stream:
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError('Another CHD import is using this cache; retry when it finishes') from error
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def run(args):
    # Tools can be noisy; bound captured output without risking pipe deadlocks.
    with tempfile.TemporaryFile() as log:
        result = subprocess.run([str(a) for a in args], stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        log.seek(0, 2)
        log.seek(max(0, log.tell() - 16384))
        output = log.read().decode('utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed ({result.returncode}): {output.strip()}')
    return output


def download(spec, target):
    if target.is_file() and digest(target) == spec['sha256']:
        return
    status('Downloading CHD import tool: ' + target.name)
    partial = target.with_suffix(target.suffix + '.partial')
    try:
        with urllib.request.urlopen(spec['url'], timeout=60) as source, open(partial, 'wb') as dest:
            shutil.copyfileobj(source, dest)
        if digest(partial) != spec['sha256']:
            raise RuntimeError('CHD tool download failed SHA-256 verification')
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def executable():
    override = os.environ.get('GOW_CHDMAN')
    if override:
        found = shutil.which(override)
        if not found:
            raise RuntimeError('GOW_CHDMAN does not name an executable')
        return Path(found)
    if os.name != 'nt':
        found = shutil.which('chdman')
        if not found:
            raise RuntimeError('CHD import requires chdman (MAME tools); install it or set GOW_CHDMAN')
        return Path(found)
    specs = json.loads((ROOT / 'tools/pipeline/toolchains.json').read_text(encoding='utf-8'))['disc_import']
    tools = ROOT / 'data/_tools'
    dest = tools / specs['chdman']['dir']
    exe = dest / specs['chdman']['exe']
    with locked(tools / 'chdman.lock'):
        if exe.is_file() and digest(exe) == specs['chdman']['exe_sha256']:
            return exe
        archive = tools / specs['chdman']['url'].rsplit('/', 1)[1]
        extractor = tools / specs['extractor']['exe']
        download(specs['chdman'], archive)
        download(specs['extractor'], extractor)
        with tempfile.TemporaryDirectory(prefix='chdman-', dir=tools) as scratch:
            run([extractor, 'x', archive, '-o' + scratch, '-y', 'chdman.exe', 'COPYING'])
            if not (Path(scratch) / 'chdman.exe').is_file():
                raise RuntimeError('chdman missing from verified MAME archive')
            if digest(Path(scratch) / 'chdman.exe') != specs['chdman']['exe_sha256']:
                raise RuntimeError('Extracted chdman failed SHA-256 verification')
            dest.mkdir(exist_ok=True)
            shutil.copy2(Path(scratch) / 'COPYING', dest / 'COPYING')
            os.replace(Path(scratch) / 'chdman.exe', exe)
        archive.unlink(missing_ok=True)
    return exe


def identity(path):
    stat = path.stat()
    return [str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def resolve(source, cache=None):
    path = Path(source).resolve(strict=True)
    if path.suffix.lower() != '.chd' or path.is_dir():
        return str(path)
    with open(path, 'rb') as stream:
        header = stream.read(124)
    if len(header) != 124 or header[:8] != b'MComprHD' or struct.unpack_from('>II', header, 8) != (124, 5):
        raise ValueError('Expected a CHDv5 image; older versions must be converted with chdman first')
    if any(header[104:124]):
        raise ValueError('Differential CHDs require a parent; import a standalone CHD instead')
    logical_bytes = struct.unpack_from('>Q', header, 32)[0]
    if not logical_bytes:
        raise ValueError('CHD has no disc data')
    stamp = identity(path)
    key = hashlib.sha256(json.dumps(stamp).encode()).hexdigest()
    cache = Path(cache) if cache else ROOT / 'data/imports/chd'
    cache.mkdir(parents=True, exist_ok=True)
    iso, marker = cache / (key + '.iso'), cache / (key + '.json')
    with locked(cache / (key + '.lock')):
        try:
            saved = json.loads(marker.read_text(encoding='utf-8'))
            if saved['source'] == stamp and iso.stat().st_size == saved['size'] and digest(iso) == saved['sha256']:
                status('Using verified CHD extraction: ' + path.name)
                return str(iso)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if shutil.disk_usage(cache).free < logical_bytes + 64 * 1024 * 1024:
            raise RuntimeError(f'Not enough free space to extract CHD: need at least {logical_bytes} bytes plus 64 MiB')
        tool = executable()
        info = run([tool, 'info', '-i', path])
        if "Tag='DVD '" in info:
            command = 'extractdvd'
        else:
            tracks = re.findall(r'TRACK:\d+ TYPE:\S+ SUBTYPE:\S+ FRAMES:\d+[^\r\n]*', info)
            if len(tracks) != 1 or not tracks[0].startswith('TRACK:1 TYPE:MODE1 SUBTYPE:NONE ') or re.search(r'(?:PRE|POST)GAP:[1-9]', tracks[0]):
                raise ValueError('CHD must contain a DVD or one MODE1/2048 track without gaps; audio/mixed/raw tracks are unsupported')
            command = 'extractcd'
        status('Verifying CHD: ' + path.name)
        verification = run([tool, 'verify', '-i', path])
        # chdman 0.289 returns zero even for a SHA-1 mismatch. Require both confirmations.
        if not all(message in verification for message in
                   ('Raw SHA1 verification successful', 'Overall SHA1 verification successful')):
            raise RuntimeError('CHD integrity verification failed: ' + verification.strip())
        with tempfile.TemporaryDirectory(prefix=key + '-', dir=cache) as scratch:
            partial = Path(scratch) / 'disc.iso'
            status('Extracting CHD: ' + path.name)
            if command == 'extractdvd':
                run([tool, command, '-i', path, '-o', partial])
            else:
                run([tool, command, '-i', path, '-o', Path(scratch) / 'disc.cue', '-ob', partial])
            with open(partial, 'rb') as stream:
                stream.seek(16 * 2048)
                if stream.read(7) != b'\x01CD001\x01':
                    raise ValueError('Extracted CHD is not a 2048-byte-sector ISO9660 disc')
            if partial.stat().st_size % 2048:
                raise ValueError('Extracted ISO has incomplete sectors')
            if identity(path) != stamp:
                raise RuntimeError('CHD changed during import; retry with a stable source')
            record = {'source': stamp, 'size': partial.stat().st_size, 'sha256': digest(partial)}
            pending = Path(scratch) / 'disc.json'
            pending.write_text(json.dumps(record), encoding='utf-8')
            os.replace(partial, iso)
            os.replace(pending, marker)
        return str(iso)
