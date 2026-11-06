"""Check regional metadata and apply overlays only to temporary source copies."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RegionalOverlays(unittest.TestCase):
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
                    for name, expected in baseline.items():
                        relative = Path(name)
                        self.assertFalse(relative.is_absolute())
                        self.assertNotIn('..', relative.parts)
                        source = ROOT / 'engine/runtime' / relative
                        self.assertTrue(source.is_file(), 'Fetch the pinned, patched runtime first')
                        text = source.read_text(encoding='utf-8')
                        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), expected, name)
                        target = Path(temporary) / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text, encoding='utf-8', newline='\n')
                    subprocess.run(['git', 'apply', '--check', str(folder / 'runtime.patch')], cwd=temporary, check=True)


if __name__ == '__main__':
    unittest.main()
