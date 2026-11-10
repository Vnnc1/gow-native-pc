"""Real installer regression with GOW_SETUP_TEST_IDENTITY=ON; never use a release setup.

python -I tools/test/setup-build-location.py <test-identity gow-setup.exe>
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import winreg

setup = Path(sys.argv[1]).resolve()
assert 'God of War Setup Regression Test'.encode('utf-16-le') in setup.read_bytes(), 'Test-identity build required'
key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\gow-native-pc-setup-test'
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
        raise RuntimeError('An earlier installer fixture is registered; preserve it and investigate first')
except FileNotFoundError:
    pass
root = Path(os.environ['SystemDrive'] + '/') / ('gow-setup-' + uuid.uuid4().hex[:8])
root.mkdir()
app = root / 'app'
stage = root / 'stage'
stage.mkdir()
for name, content in [('games/gow1/game.toml', b'fixture'), ('launcher/bin/gow-launcher.exe', b'not an executable'),
                      ('engine/patches/00-fixture.patch', b'fixture')]:
    file = stage / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
packed = root / 'setup.exe'


def install(build=None, success=True):
    cmd = [str(packed), '/S', '/D=' + str(app)]
    if build is not None:
        cmd.append('/BUILDROOT=' + str(build))
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    assert (result.returncode == 0) == success, (cmd, result.returncode, result.stdout, result.stderr)


def chosen():
    return (app / 'data/build-root.txt').read_text(encoding='utf-8')


try:
    subprocess.run([str(setup), '--pack', str(stage), str(packed)], check=True, timeout=20)
    first = root / 'build'
    install(first)
    assert chosen() == str(first)
    cache = Path(str(first) + '-clang')
    cache.mkdir()
    owner = (app / 'engine/runtime/PS2Recomp').as_posix()
    (cache / 'CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL=' + owner + '\n')
    (cache / 'old-build.txt').write_text('keep this build')
    card = app / 'data/gow1/mc0/card.ps2'
    card.parent.mkdir(parents=True)
    card.write_bytes(b'player progress')
    second = root / 'build-\u00e1'
    install(second)
    assert chosen() == str(second)
    assert (app / 'data/needs-rebuild.txt').exists() and (app / 'data/pgo-stale.txt').exists()
    assert card.read_bytes() == b'player progress'
    assert (cache / 'old-build.txt').read_text() == 'keep this build'
    install()  # An update without a new choice must preserve it, including Unicode.
    assert chosen() == str(second)
    foreign = root / 'foreign'
    foreign_cache = Path(str(foreign) + '-clang')
    foreign_cache.mkdir()
    # A source with the right prefix is still a different source.
    (foreign_cache / 'CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL=' + owner + '-other\n')
    install(foreign, False)
    for invalid in ('relative', str(root) + '/x' * 30, str(app), os.environ['SystemDrive'] + '\\'):
        install(invalid, False)
        assert chosen() == str(second)
    assert card.read_bytes() == b'player progress'
    assert (foreign_cache / 'CMakeCache.txt').read_text().endswith('-other\n')
    subprocess.run([str(packed), '/uninstall-from', str(app), '/S'], check=True, timeout=20)
    assert card.read_bytes() == b'player progress'
    install()
    owned = Path(str(second) + '-clang')
    owned.mkdir()
    (owned / 'CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL=' + owner + '\n')
    subprocess.run([str(packed), '/uninstall-from', str(app), '/S', '/purge'], check=True, timeout=20)
    assert not owned.exists()
    assert (cache / 'old-build.txt').read_text() == 'keep this build'
    assert (foreign_cache / 'CMakeCache.txt').exists()
    print('PASS: install, Unicode relocation/rebuild, update retention, foreign/path rejection, save/build preservation and owned purge')
finally:
    # Only this test identity and the newly created, verified scratch directory are removable.
    if (app / 'uninstall.lst').exists():
        subprocess.run([str(packed), '/uninstall-from', str(app), '/S'], check=True, timeout=20)
    assert root.resolve().parent == Path(os.environ['SystemDrive'] + '/').resolve() and root.name.startswith('gow-setup-')
    shutil.rmtree(root)
