"""Package the Linux launcher and tracked sources, never generated game data.

Run on the build host with --root pointing at the source checkout. The archive
uses host libraries; it is deliberately not advertised as a portable AppImage.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        parser.error('Package on the native x86-64 Linux build host')

    def git(*argv):
        return subprocess.check_output(['git', '-C', str(root), *argv]).decode()

    files = {}
    source_names = set(git('ls-files', '-z').split('\0'))
    source_names.add('tools/pipeline/package_linux.py')
    for name in sorted(source_names):
        if not name:
            continue
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or path.parts[0] == 'data'
                or name.startswith(('engine/runtime/', 'launcher/build', 'launcher/bin/'))
                or '/pgo/' in name):
            raise RuntimeError(f'Refusing generated or unsafe source path: {name}')
        source = root / name
        if source.is_symlink():
            raise RuntimeError(f'Refusing symlink: {name}')
        payload = source.read_bytes()
        if name.endswith('.sh'):
            payload = payload.replace(b'\r\n', b'\n')  # Windows working trees can retain CRLF shell scripts.
        files[name] = (payload, 0o755 if name.endswith('.sh') else 0o644)
    dependencies = {}
    for name in ('gow-launcher', 'gow-session'):
        binary = args.launcher / name
        payload = binary.read_bytes()
        if payload[:6] != b'\x7fELF\x02\x01' or payload[18:20] != b'\x3e\x00':
            raise RuntimeError(f'Not a Linux x86-64 ELF: {binary}')
        libraries = subprocess.check_output(['ldd', str(binary)], text=True)
        if 'not found' in libraries:
            raise RuntimeError(f'Missing dependencies for {name}: {libraries}')
        dependencies[name] = libraries.splitlines()
        files[f'launcher/bin/{name}'] = (payload, 0o755)
    files['start-linux.sh'] = (b'''#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$root/launcher/bin/gow-launcher" "$@"
''', 0o755)
    files['setup-linux.sh'] = (b'''#!/usr/bin/env bash
set -euo pipefail
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [[ $# == 0 ]]; then
    bash "$root/build.sh" --stages tools,fetch,launcher
else
    bash "$root/build.sh" "$@"
fi
''', 0o755)
    files['LEIA-ME-LINUX.txt'] = ('''LINUX EXPERIMENTAL - BIBLIOTECAS DO SISTEMA

Este pacote inclui launcher e coletor de diagnostico nativos, alem das fontes.
Veja linux-package.json para o sistema e bibliotecas usados na compilacao.
Nao e um AppImage universal: o binario Ubuntu 26.04 nao foi validado no SteamOS.

1. Extraia no filesystem Linux em uma pasta gravavel.
2. Instale as dependencias Qt/QML e SDL2 correspondentes (docs/linux.md).
3. Execute: bash start-linux.sh
4. Na aba Instalar, selecione sua propria ISO USA/Asia compativel e compile.

Para recompilar o launcher em outra distribuicao: bash setup-linux.sh
Depois abra data/build-linux/launcher/gow-launcher.
Para compilar tambem o jogo: bash setup-linux.sh --discs "/caminho/jogo.iso" --jobs 2

ISOs, saves, texturas, jogo recompilado e builds regionais Windows nao acompanham
o pacote. Europe/Japan precisam de builds Linux separadas. Demos sao excluidas.
Steam Deck requer validacao real de bibliotecas, controle, audio, suspensao e
Gaming Mode. Nao desative a protecao de escrita do SteamOS para instalar ferramentas.
Resultados e limites dos testes: docs/tested-hardware.md e docs/linux.md.
'''.encode(), 0o644)
    manifest = {
        'schema': 1, 'kind': 'experimental-linux-host-libraries',
        'commit': git('rev-parse', 'HEAD').strip(),
        'dirty': bool(git('status', '--porcelain', '--untracked-files=no').strip()),
        'build_os': platform.freedesktop_os_release(),
        'architecture': platform.machine(), 'libc': platform.libc_ver(),
        'dependencies': dependencies, 'contains_game_data': False,
        'steam_deck_validated': False,
        'files': {n: hashlib.sha256(p).hexdigest() for n, (p, _) in files.items()},
    }
    files['linux-package.json'] = ((json.dumps(manifest, indent=2) + '\n').encode(), 0o644)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(output.name + '.partial')
    try:
        with tarfile.open(pending, 'w:gz') as archive:
            for name, (payload, mode) in sorted(files.items()):
                member = tarfile.TarInfo('gow-native-pc/' + name)
                member.size, member.mode = len(payload), mode
                archive.addfile(member, io.BytesIO(payload))
        # Re-read every packaged byte and mode before publishing the archive.
        with tarfile.open(pending, 'r:gz') as archive:
            members = archive.getmembers()
            assert len(members) == len(files)
            for member in members:
                payload, mode = files[member.name.removeprefix('gow-native-pc/')]
                assert member.isfile() and member.mode == mode
                assert archive.extractfile(member).read() == payload
        os.replace(pending, output)
    finally:
        pending.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_name(output.name + '.sha256').write_text(f'{digest}  {output.name}\n')
    print(f'PASS: {len(files)} files verified; {output}; SHA256 {digest}')


if __name__ == '__main__':
    main()
