"""Generator cache/shard regression tests using a procedural micro-memory, never game data.

python -I tools/disc/vu1_analysis_cache_test.py --gen <vu1n_gen.py> <procedural.bin>
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gen', required=True)
    parser.add_argument('micro')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generator = root / 'generator.py'
        generator.write_bytes(Path(args.gen).read_bytes())
        source = root / 'micro.bin'
        source.write_bytes(Path(args.micro).read_bytes())
        cached, reference = root / 'cached', root / 'reference'

        def run(out, *flags):
            result = subprocess.run([sys.executable, '-I', str(generator), str(out), str(source),
                                     '--parts', '6', *flags], capture_output=True, text=True, check=True)
            return result.stdout

        def equal():
            for file in cached.glob('*.cpp'):
                assert file.read_bytes() == (reference / file.name).read_bytes(), file.name
                part = int(re.search(r'part(\d+)', file.name)[1])
                for key in re.findall(r'vu1nRegisterBlock\(0x([0-9a-f]+)ull', file.read_text()):
                    assert int(key, 16) % 6 == part, 'unstable shard'

        assert '0/1 images reused' in run(cached)
        run(reference, '--no-cache')
        before = {f.name: f.stat().st_mtime_ns for f in cached.glob('*.cpp')}
        assert '1/1 images reused' in run(cached)
        equal()
        assert before == {f.name: f.stat().st_mtime_ns for f in cached.glob('*.cpp')}
        (cached / 'vu1n-analysis.cache').write_bytes(b'corrupt\ncache')
        assert '0/1 images reused' in run(cached)
        equal()
        heads = root / 'heads.txt'
        heads.write_text('8\n')
        assert '0/1 images reused' in run(cached, '--heads', str(heads))
        run(reference, '--heads', str(heads), '--no-cache')
        equal()
        assert '1/1 images reused' in run(cached, '--heads', str(heads))
        generator.write_text(generator.read_text(encoding='utf-8') + '\n# changed implementation\n', encoding='utf-8')
        assert '0/1 images reused' in run(cached, '--heads', str(heads))
        equal()
        # Change an upper destination lane mask, keeping the opcode and control-flow bits intact.
        image = bytearray(source.read_bytes())
        for pos in range(0, len(image), 8):
            if any(image[pos + 4:pos + 8]):
                image[pos + 6] ^= 0x20
                break
        else:
            raise AssertionError('fixture needs an upper instruction')
        source.write_bytes(image)
        assert '0/1 images reused' in run(cached, '--heads', str(heads))
        run(reference, '--heads', str(heads), '--no-cache')
        equal()
    print('PASS: cached/reference equivalence, stable shards and timestamps, corruption, heads, generator and input invalidation')


if __name__ == '__main__':
    main()
