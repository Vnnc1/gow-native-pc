"""Exercise production VFS and declarative patch consumers in fresh processes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

exe = Path(sys.argv[1]).resolve()
clean = {key: value for key, value in os.environ.items() if not key.startswith('GOW_MOD_')}
with tempfile.TemporaryDirectory(prefix='gow-mod-runtime-') as temporary:
    root = Path(temporary)
    payload = root / 'payload.bin'
    payload.write_bytes(b'synthetic')
    table = root / 'vfs.tsv'
    table.write_text(f'cdrom0:/synthetic.bin\t{payload}\n', encoding='utf-8')
    patches = root / 'patches.tsv'
    patches.write_text('0x100000\t1\t42\t0\t0\t0\n'
                       '0x100004\t1\t7\t0\t0\t1\n'
                       '0xfffffffc\t4\t255\t0\t0\t0\n'
                       '0xffffffff\t1\t255\t0\t0\t0\n'
                       '0x100008\t257\t255\t0\t0\t0\n'
                       '0x10000c\t4\t255oops\t0\t0\t0\n'
                       '0x100010\t4\t0x1000000ff\t0\t0\t0\n', encoding='utf-8')
    for active in (False, True, False):
        env = clean | ({'GOW_MOD_VFS_TABLE': str(table), 'GOW_MOD_PATCH_TABLE': str(patches)} if active else {})
        subprocess.run([str(exe), 'active' if active else 'off'], env=env, check=True, timeout=20)
        print('PASS: production mod consumers', 'active' if active else 'off')
