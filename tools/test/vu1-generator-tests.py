"""Exercise the built production VU1 generator without game data."""
import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile


def outputs(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.glob('programa*.cpp')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generator', required=True, type=Path)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    generator = args.generator.resolve()
    with tempfile.TemporaryDirectory(prefix='gow-vu1-generator-') as temporary:
        root = Path(temporary)
        captures = root / 'captures'
        captures.mkdir()
        # NOP pairs followed by an E-bit pair and its delay slot.
        image = bytearray(16384)
        for i in range(4):
            struct.pack_into('<II', image, i * 8, 0x8000033c,
                             0x400002ff if i == 2 else 0x000002ff)
        (captures / 'a.bin').write_bytes(image)
        (captures / 'b.bin').write_bytes(bytes(16384))
        out = root / 'output'
        out.mkdir()

        def run(exe, destination, *inputs, success=True):
            result = subprocess.run([str(exe), str(destination), *map(str, inputs)],
                                    capture_output=True, text=True, timeout=30)
            assert (result.returncode == 0) == success, result.stdout + result.stderr
            return result

        run(generator, out, captures)
        expected = outputs(out)
        assert len(expected) == 13
        times = {p.name: p.stat().st_mtime_ns for p in out.glob('*.cpp')}
        run(generator, out, captures)
        assert times == {p.name: p.stat().st_mtime_ns for p in out.glob('*.cpp')}
        explicit = root / 'explicit'
        explicit.mkdir()
        run(generator, explicit, captures / 'a.bin', captures / 'b.bin')
        assert outputs(explicit) == expected
        if args.reference:
            reference = root / 'reference'
            reference.mkdir()
            run(args.reference.resolve(), reference, captures)
            assert outputs(reference) == expected

        for size in (0, 16383, 16385, 1024 * 1024 * 1024):
            invalid = root / 'invalid.bin'
            with invalid.open('wb') as stream:
                stream.truncate(size)
            result = run(generator, out, captures / 'a.bin', invalid, success=False)
            assert '16384' in result.stderr
            assert outputs(out) == expected  # Failed input never publishes partial output.
        run(generator, out, root / 'missing.bin', success=False)
        assert outputs(out) == expected
    print('PASS: VU1 generator output parity, directory/explicit inputs, restat, '
          'missing/truncated/oversized inputs and output preservation')


if __name__ == '__main__':
    main()
