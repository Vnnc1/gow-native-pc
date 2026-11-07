"""Static contract check for the launcher -> runner settings chain.

Guards the "dead toggle" class of bugs that patch 81 v2 fixed:

  1. every key Lanzador::iniciar() reads from the play map must be supplied by
     Main.qml's jugar() map (a missing key silently reads as false);
  2. every environment variable the launcher writes must have a reader in the
     runtime sources (otherwise the switch does nothing);
  3. the three effect switches are wired end to end: QML key -> bandera() ->
     GOW_FX_* variable -> runtime getenv.

Run from anywhere: python tools/test/launcher-env-contract.py
No Qt, no game data and no build are needed; this is a source-only check.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPP = ROOT / 'launcher/src/lanzador.cpp'
QML = ROOT / 'launcher/qml/Main.qml'
# Optional --runtime <dir>: check another runtime checkout (a scratch copy with the patch chain applied).
RUNTIME = Path(sys.argv[sys.argv.index('--runtime') + 1]) if '--runtime' in sys.argv else ROOT / 'engine/runtime'

# GPU selectors written by aplicarTarjeta() are consumed by the OS/driver loader,
# not by any C++ source in the runtime.
PLATFORM_VARS = {
    'DRI_PRIME', '__NV_PRIME_RENDER_OFFLOAD', '__GLX_VENDOR_LIBRARY_NAME',
    'LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE',
}
EFFECTS = {
    'fxSinSombras': 'GOW_FX_NO_SHADOWS',
    'fxSinAditivos': 'GOW_FX_NO_ADDITIVE3D',
    'fxSinFiltrado': 'GOW_FX_NO_TEXTURE_FILTER',
}


def fail(message):
    print('FAIL: ' + message)
    raise SystemExit(1)


def main():
    cpp = CPP.read_text(encoding='utf-8')
    qml = QML.read_text(encoding='utf-8')

    # --- 1. iniciar() reads vs jugar() supplies -------------------------------------------------------
    start = cpp.index('bool Lanzador::iniciar(')
    following = cpp.find('\nQString ', start + 10)
    iniciar = cpp[start:following if following > 0 else len(cpp)]
    read_keys = set(re.findall(
        r'a\.value\(\s*(?:QStringLiteral|QLatin1String)\("([^"]+)"\)', iniciar))
    play = re.search(r'function jugar\(\).*?var a = \{(.*?)\n        \}', qml, re.S)
    if not play:
        fail('cannot locate the play map in Main.qml (jugar)')
    play_keys = set(re.findall(
        r'(?:^|[,{\n])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', play.group(1)))
    if len(read_keys) < 30 or len(play_keys) < 25:
        fail(f'parser looks incomplete: {len(read_keys)} read keys, {len(play_keys)} play keys')
    missing = sorted(read_keys - play_keys)
    if missing:
        fail('Settings keys read by iniciar() but missing from jugar(): ' + ', '.join(missing))

    # --- 2. written environment variables have a runtime reader --------------------------------------
    written = set(re.findall(r'bandera\(\s*"([A-Z0-9_]+)"', iniciar))
    written |= set(re.findall(r'entorno\.insert\(\s*QStringLiteral\("([A-Z0-9_]+)"\)', iniciar))
    written |= set(re.findall(r'\{\s*"([A-Z0-9_]+)"\s*,\s*"', cpp[:start]))  # kEntornoBase
    for loop in re.finditer(r'for \(const QString &key : \{(.*?)\}\)', iniciar, re.S):
        written |= set(re.findall(r'QStringLiteral\("([A-Z0-9_]+)"\)', loop.group(1)))
    files = [p for p in RUNTIME.rglob('*')
             if p.suffix in ('.cpp', '.h', '.inl', '.c', '.cc')
             and 'third_party' not in str(p)
             and 'launcher' not in p.relative_to(RUNTIME).parts]
    # verify can run before fetch, on a checkout without engine/runtime: the play-map contract above is
    # always meaningful, but a missing runtime must not be reported as 52 dead variables.
    if not (RUNTIME / 'PS2Recomp').is_dir():
        for key in EFFECTS:
            if key not in play_keys or f'bandera("{EFFECTS[key]}"' not in iniciar:
                fail(f'effect switch {key} is not wired through the play map and bandera()')
        print(f'PASS (launcher only): {len(read_keys)} play-map keys, {len(EFFECTS)} effect switches; '
              'runtime reader check SKIPPED (no engine/runtime checkout)')
        return
    corpus = '\n'.join(p.read_text(encoding='utf-8', errors='ignore') for p in files)
    unread = sorted(v for v in written - PLATFORM_VARS
                    if not re.search(r'"' + re.escape(v) + r'"', corpus))
    if unread:
        fail('environment variables written by the launcher with no runtime reader: ' + ', '.join(unread))

    # --- 3. effect switches end to end ---------------------------------------------------------------
    for key, variable in EFFECTS.items():
        if key not in play_keys:
            fail(f'effect switch {key} is not forwarded by jugar()')
        if f'bandera("{variable}"' not in iniciar:
            fail(f'effect switch {key} has no bandera("{variable}") in iniciar()')
        if not re.search(r'"' + re.escape(variable) + r'"', corpus):
            fail(f'{variable} has no reader in the runtime')
        if f'property bool {key}' not in qml:
            fail(f'effect switch {key} has no Settings property')

    print(f'PASS: {len(read_keys)} play-map keys, {len(written)} environment variables, '
          f'{len(EFFECTS)} effect switches, {len(files)} runtime sources checked')


if __name__ == '__main__':
    main()
