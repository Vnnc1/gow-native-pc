"""Check regional overlays against an explicit, unmodified pre-overlay baseline.

The default checks engine/runtime; --runtime selects an isolated historical baseline.
Neither mode updates hashes or accepts a source that differs from baseline.json.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'engine/runtime'


def copy_baseline(runtime, baseline, destination):
    for name, expected in baseline.items():
        relative = Path(name)
        if relative.is_absolute() or relative.drive or '..' in relative.parts:
            raise ValueError(f'Baseline path must stay relative: {name}')
        source = runtime / relative
        text = source.read_text(encoding='utf-8')
        actual = hashlib.sha256(text.encode()).hexdigest()
        if actual != expected:
            raise ValueError(f'Baseline mismatch: {source}: expected {expected}, got {actual}; '
                             'use the matching pre-overlay snapshot, not a newer USA runtime')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8', newline='\n')


class RegionalOverlays(unittest.TestCase):
    def test_baseline_copy_preserves_identity_gate(self):
        with tempfile.TemporaryDirectory(prefix='gow-baseline-fixture-') as temporary:
            source, target = Path(temporary) / 'source', Path(temporary) / 'copy'
            source.mkdir()
            file = source / 'fixture.cpp'
            file.write_bytes(b'line\r\n')
            baseline = {'fixture.cpp': hashlib.sha256(b'line\n').hexdigest()}
            copy_baseline(source, baseline, target)
            self.assertEqual((target / 'fixture.cpp').read_bytes(), b'line\n')
            self.assertEqual(file.read_bytes(), b'line\r\n')
            file.write_bytes(b'changed\n')
            with self.assertRaisesRegex(ValueError, 'Baseline mismatch'):
                copy_baseline(source, baseline, target)
            file.unlink()
            with self.assertRaises(FileNotFoundError):
                copy_baseline(source, baseline, target)
            with self.assertRaisesRegex(ValueError, 'must stay relative'):
                copy_baseline(source, {'../escape.cpp': 'ignored'}, target)

    def test_metadata_and_patch_baselines(self):
        profile = tomllib.loads((ROOT / 'games/gow1/game.toml').read_text(encoding='utf-8'))
        for region in profile['regions']:
            folder = ROOT / 'games/gow1/regions' / region['id']
            if not folder.exists():
                continue
            with self.subTest(region=region['id']):
                self.assertEqual(len(region['known_text_sha1']), 40)
                with (folder / 'functions.csv').open() as source:
                    ranges = [(int(row['Start'], 16), int(row['End'], 16)) for row in csv.DictReader(source)]
                self.assertTrue(ranges)
                self.assertEqual(ranges, sorted(ranges))
                for i, (start, end) in enumerate(ranges):
                    self.assertTrue(0x100000 <= start < end < 0x2000000)
                    self.assertEqual((start | end) % 4, 0)
                    if i:
                        self.assertLessEqual(ranges[i - 1][1], start)
                frame = int(region['experimental_frame_pc'], 0)
                self.assertTrue(any(start <= frame < end for start, end in ranges))
                entries = json.loads((folder / 'entries.json').read_text())
                for key in ('stubs', 'entry_points'):
                    addresses = [int(item.split('@')[1], 16) for item in entries[key]]
                    self.assertEqual(len(addresses), len(set(addresses)))
                    self.assertTrue(all(ranges[0][0] <= pc < ranges[-1][1] and pc % 4 == 0 for pc in addresses))
                baseline = json.loads((folder / 'baseline.json').read_text())
                with tempfile.TemporaryDirectory(prefix='gow-region-overlay-') as temporary:
                    copy_baseline(RUNTIME, baseline, Path(temporary))
                    subprocess.run(['git', 'apply', '--check', str(folder / 'runtime.patch')], cwd=temporary, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUNTIME,
                        help='Unmodified pre-overlay runtime snapshot; all baseline hashes remain mandatory')
    args, remaining = parser.parse_known_args()
    RUNTIME = args.runtime.resolve()
    unittest.main(argv=[sys.argv[0], *remaining])
