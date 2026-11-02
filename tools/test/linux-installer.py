"""Check a generated .run installer in private directories, without game data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


installer = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='gow-installer-test-') as temporary:
    work = Path(temporary)
    target = work / 'installation with spaces'
    subprocess.run(['bash', str(installer), str(target)], check=True)
    manifest = json.loads((target / 'linux-package.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest, name
    assert manifest['version'] == '0.5.0'
    assert (target / 'launcher/bin/gow-launcher').stat().st_mode & 0o111
    sentinel = target / 'player-save-sentinel'
    sentinel.write_text('preserve')
    assert subprocess.run(['bash', str(installer), str(target)]).returncode != 0
    assert sentinel.read_text() == 'preserve'
    damaged = work / 'damaged.run'
    payload = bytearray(installer.read_bytes())
    payload[-20] ^= 1
    damaged.write_bytes(payload)
    rejected = work / 'must-not-exist'
    assert subprocess.run(['bash', str(damaged), str(rejected)]).returncode != 0
    assert not rejected.exists()
    subprocess.run(['bash', str(installer), '--help'], check=True)
print('PASS: installation hashes, executable modes, existing-directory protection and corrupt payload rejection')
