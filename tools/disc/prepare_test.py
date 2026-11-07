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
    def test_widescreen_fallback_uses_remapped_entry(self):
        placeholder = b'placeholder' * 300
        cases = [('known placeholder', placeholder, 50000, True),
                 ('valid movie with formerly empty entry', b'v' * len(placeholder), 4, False),
                 ('empty current entry', b'\0' * 4, 50000, True)]
        for label, payload, old_size, replace in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                profile = {'disc': {'toc': 'INDEX', 'paks': ['PART0', 'PART1'],
                                   'widescreen_movie_ext': '.WIDE', 'movie_ext': '.MOV',
                                   'widescreen_placeholders': [{'size': len(placeholder),
                                       'sha256': hashlib.sha256(placeholder).hexdigest()}]}}
                original = b''.join(struct.pack('<12sIII', n, part, size, sector)
                                    for n, part, size, sector in [
                                        (b'A.MOV', 0, 9000, 10),
                                        (b'A.WIDE', 0, len(payload), 0),
                                        (b'A.WIDE', 1, old_size, 100)])
                (root / 'INDEX').write_bytes(original)
                (root / 'PART0').write_bytes(payload)
                prepare.normalise(tmp, profile)
                first = (root / 'INDEX').read_bytes()
                entries = prepare.discfs.parse_toc(first)
                expected = (0, 9000, 10) if replace else (0, len(payload), 0)
                self.assertEqual(entries[1][2:], expected)
                self.assertEqual(entries[2][2:], expected)
                self.assertEqual((root / 'INDEX.orig').read_bytes(), original)
                self.assertEqual((root / 'PART0').read_bytes(), payload)
                prepare.normalise(tmp, profile)
                self.assertEqual((root / 'INDEX').read_bytes(), first)

    def test_guest_irx_case_aliases_and_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'SIO2MAN.IRX').write_bytes(b'original module')
            modules = root / 'modules'
            modules.mkdir()
            (modules / 'unrelated.txt').write_bytes(b'keep')
            profile = {'disc': {'iop_modules_dir': 'modules'}}
            prepare.normalise(tmp, profile)
            self.assertEqual((modules / 'sio2man.irx').read_bytes(), b'original module')
            self.assertEqual((modules / 'SIO2MAN.IRX').read_bytes(), b'original module')
            (modules / 'sio2man.irx').write_bytes(b'local modification')
            prepare.normalise(tmp, profile)
            self.assertEqual((modules / 'sio2man.irx').read_bytes(), b'local modification')
            self.assertEqual((root / 'SIO2MAN.IRX').read_bytes(), b'original module')
            self.assertEqual((modules / 'unrelated.txt').read_bytes(), b'keep')

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


class BuildAliasTests(unittest.TestCase):
    def test_executable_gets_a_second_name_for_the_build_that_runs_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'SCAJ_973.99'
            source.write_bytes(b'\x7fELF' + bytes(64))
            self.assertTrue(prepare.expose_for_build(tmp, 'SCAJ_973.99', 'SLPM_670.10'))
            alias = Path(tmp) / 'SLPM_670.10'
            self.assertEqual(alias.read_bytes(), source.read_bytes())
            self.assertEqual(source.read_bytes(), alias.read_bytes())  # the disc's own name stays
            self.assertTrue(prepare.expose_for_build(tmp, 'SCAJ_973.99', 'SLPM_670.10'))  # idempotent
            self.assertEqual(len(list(Path(tmp).iterdir())), 2)

    def test_no_alias_without_a_second_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(prepare.expose_for_build(tmp, 'SCAJ_973.99', 'SLPM_670.10'))
            (Path(tmp) / 'SLPM_670.10').write_bytes(b'executable')
            self.assertFalse(prepare.expose_for_build(tmp, 'SLPM_670.10', 'SLPM_670.10'))
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
