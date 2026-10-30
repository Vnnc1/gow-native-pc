"""Synthetic disc normalization regressions; no game data required."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare


class MovieFallbackTests(unittest.TestCase):
    def test_exact_placeholder_only_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b'placeholder' * 300
            profile = {'disc': {'toc': 'INDEX', 'paks': ['ARCHIVE'],
                               'widescreen_movie_ext': '.WIDE', 'movie_ext': '.MOV',
                               'widescreen_placeholders': [{'size': len(payload),
                                   'sha256': hashlib.sha256(payload).hexdigest()}]}}
            rows = [('A.MOV', 9000, 10), ('A.WIDE', len(payload), 0),
                    ('B.MOV', 9000, 20), ('B.WIDE', len(payload), 2),
                    ('C.WIDE', len(payload), 0),  # No replacement available.
                    ('D.MOV', 9000, 30), ('D.WIDE', 4, 4)]
            original = b''.join(struct.pack('<12sIII', n.encode(), 0, size, sector)
                                for n, size, sector in rows)
            (root / 'INDEX').write_bytes(original)
            (root / 'ARCHIVE').write_bytes(payload + bytes(4096 - len(payload))
                                          + b'v' * len(payload))
            prepare.normalise(tmp, profile)
            first = (root / 'INDEX').read_bytes()
            entries = {e[1]: e[2:] for e in prepare.discfs.parse_toc(first)}
            self.assertEqual(entries['A.WIDE'], entries['A.MOV'])
            self.assertEqual(entries['B.WIDE'], (0, len(payload), 2))
            self.assertEqual(entries['C.WIDE'], (0, len(payload), 0))
            self.assertEqual(entries['D.WIDE'], entries['D.MOV'])
            self.assertEqual((root / 'INDEX.orig').read_bytes(), original)
            prepare.normalise(tmp, profile)
            self.assertEqual((root / 'INDEX').read_bytes(), first)


if __name__ == '__main__':
    unittest.main()
