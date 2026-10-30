"""Exercise the real recompiler and pipeline with a tiny synthetic MIPS ELF (no game data)."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('recompile', ROOT / 'tools/pipeline/recompile.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def main(build):
    with tempfile.TemporaryDirectory(prefix='gow-synthetic-elf-') as temporary:
        root = Path(temporary)
        for folder in ('games/demo', 'engine/runtime/config', 'data/demo'):
            (root / folder).mkdir(parents=True)
        elf = root / 'synthetic.elf'
        image = bytearray(0x130 + 3 * 40)
        ident = b'\x7fELF' + bytes([1, 1, 1]) + bytes(9)
        image[:52] = struct.pack('<16sHHIIIIIHHHHHH', ident, 2, 8, 1, 0x100000, 52, 0x130,
                                 0x20924001, 52, 32, 1, 40, 3, 2)
        image[52:84] = struct.pack('<IIIIIIII', 1, 0x100, 0x100000, 0x100000, 12, 12, 5, 0x100)
        image[0x100:0x10c] = struct.pack('<III', 0x24020001, 0x03e00008, 0)  # addiu v0,zero,1; jr ra; nop
        names = b'\0.text\0.shstrtab\0'
        image[0x110:0x110 + len(names)] = names
        image[0x158:0x180] = struct.pack('<IIIIIIIIII', 1, 1, 6, 0x100000, 0x100, 12, 0, 0, 4, 0)
        image[0x180:0x1a8] = struct.pack('<IIIIIIIIII', 7, 3, 0, 0, 0x110, len(names), 0, 0, 1, 0)
        elf.write_bytes(image)
        (root / 'games/demo/game.toml').write_text(
            '[runtime]\nfunction_map="config/map.csv"\nrecompiler_template="config/template.toml"\noverrides=[]\n', encoding='utf-8')
        (root / 'engine/runtime/config/map.csv').write_text(
            'Name,Start,End,Size\nsynthetic,0x00100000,0x0010000C,12\n', encoding='utf-8')
        (root / 'engine/runtime/config/template.toml').write_text(
            '[general]\ninput="@ELF@"\nghidra_output="@MAP@"\noutput="@OUT@"\nsingle_file_output=false\n', encoding='utf-8')
        pipeline.atomic_json(root / 'data/demo/languages.json', {'recompile_elf': str(elf)})
        try:
            first = pipeline.generate(root, 'demo', build, 'locals')
            assert not first['cacheHit']
            synced = pipeline.synchronize(root, 'demo')
            assert synced['.cpp']['changed'] > 0
            output = root / 'data/demo/recomp/out'
            stamps = {p.name: p.stat().st_mtime_ns for p in output.glob('*.cpp')}
            assert pipeline.generate(root, 'demo', build, 'locals')['cacheHit']
            assert not pipeline.generate(root, 'demo', build, 'locals', force=True)['cacheHit']
            assert stamps == {p.name: p.stat().st_mtime_ns for p in output.glob('*.cpp')}
            assert all(v == {'changed': 0, 'removed': 0} for v in pipeline.synchronize(root, 'demo').values())
            assert not pipeline.generate(root, 'demo', build, 'classic')['cacheHit']
            print('PASS: real synthetic ELF generation, cache hit, forced deterministic output, no-op sync and classic mode')
        except BaseException:
            log = root / 'data/demo/logs/recomp.log'
            if log.exists():
                print(log.read_text(encoding='utf-8', errors='replace'))
            raise


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
