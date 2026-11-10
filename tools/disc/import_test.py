"""Disc import regressions; optional real CHD round trips use only synthetic data.

python -I tools/disc/import_test.py [--chdman /path/to/chdman]
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chd
import discfs
import identify
import prepare

TOOL = None


def elf():
    data = bytearray(512)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<I', data, 32, 64)
    struct.pack_into('<HHH', data, 46, 40, 3, 1)
    names = b'\0.shstrtab\0.text\0'
    data[256:256 + len(names)] = names
    struct.pack_into('<10I', data, 104, 1, 3, 0, 0, 256, len(names), 0, 0, 1, 0)
    struct.pack_into('<10I', data, 144, 11, 1, 6, 0x100000, 320, 64, 0, 0, 4, 0)
    data[320:384] = bytes(range(64))
    return bytes(data)


def record(name, sector, size, directory=False):
    data = bytearray(33 + len(name) + (len(name) % 2 == 0))
    data[0] = len(data)
    struct.pack_into('<I', data, 2, sector)
    struct.pack_into('>I', data, 6, sector)
    struct.pack_into('<I', data, 10, size)
    struct.pack_into('>I', data, 14, size)
    data[25] = 2 if directory else 0
    data[28:32] = b'\x01\x00\x00\x01'
    data[32] = len(name)
    data[33:33 + len(name)] = name
    return data


def iso(path, boot='SCUS_973.99'):
    data = bytearray(64 * 2048)
    pvd = memoryview(data)[16 * 2048:17 * 2048]
    pvd[:7] = b'\x01CD001\x01'
    struct.pack_into('<I', pvd, 80, 64)
    struct.pack_into('>I', pvd, 84, 64)
    pvd[156:190] = record(b'\0', 20, 2048, True)
    data[17 * 2048:17 * 2048 + 7] = b'\xffCD001\x01'
    cnf = ('BOOT2 = cdrom0:\\' + boot + ';1\r\n').encode()
    files = [('SYSTEM.CNF', cnf), (boot, elf())]
    directory = record(b'\0', 20, 2048, True) + record(b'\x01', 20, 2048, True)
    for sector, (name, contents) in enumerate(files, 21):
        directory += record((name + ';1').encode(), sector, len(contents))
        data[sector * 2048:sector * 2048 + len(contents)] = contents
    data[20 * 2048:20 * 2048 + len(directory)] = directory
    path.write_bytes(data)
    return path


class TempTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='disc import ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class ImportTests(TempTests):
    def test_original_still_requires_code_hash(self):
        source = iso(self.root / 'USA.iso')
        profile = copy.deepcopy(identify.profiles.load('gow1'))
        with patch.object(identify.profiles, 'all_profiles', return_value=[profile]):
            self.assertFalse(identify.identify(source)['compatible'])
            profile['executable']['text_sha1'] = discfs.text_sha1(elf())
            self.assertTrue(identify.identify(source)['compatible'])

    def test_regions_and_demos_never_use_usa_map_even_if_text_matches(self):
        profile = copy.deepcopy(identify.profiles.load('gow1'))
        profile['executable']['text_sha1'] = discfs.text_sha1(elf())
        with patch.object(identify.profiles, 'all_profiles', return_value=[profile]):
            for region in profile['regions']:
                with self.subTest(region=region['id']):
                    source = iso(self.root / (region['id'] + '.iso'), region['elf'])
                    result = identify.identify(source)
                    self.assertFalse(result['compatible'])
                    self.assertEqual(result['edition'], region['id'])
                    self.assertEqual(result['reason_code'], 'demo_excluded' if region.get('demo') else 'region_not_ported')

    def test_region_with_code_reuses_that_build_only_when_the_bytes_match(self):
        profile = copy.deepcopy(identify.profiles.load('gow1'))
        profile['executable']['text_sha1'] = discfs.text_sha1(elf())
        region = next(r for r in profile['regions'] if r['id'] == 'asia-97399')
        with patch.object(identify.profiles, 'all_profiles', return_value=[profile]), \
                patch.object(identify, 'regional_builds', return_value=[]):
            # The recorded identity is the Japanese executable; the synthetic one is not it.
            result = identify.identify(iso(self.root / 'asia other code.iso', region['elf']))
            self.assertNotIn('code', result)
            self.assertEqual(result['reason_code'], 'region_not_ported')
            # Same disc, same serial: once its measured identity is the shared one it reuses that build.
            target = next(r for r in profile['regions'] if r['id'] == region['code'])
            target['known_crc'] = discfs.pcsx2_crc(elf())
            target['known_text_sha1'] = discfs.text_sha1(elf())
            result = identify.identify(iso(self.root / 'asia same code.iso', region['elf']))
            self.assertEqual(result['reason_code'], 'region_alias')
            self.assertEqual(result['code'], 'japan')
            self.assertEqual(result['label'], region['label'])
            self.assertFalse(result['compatible'])  # it still never enters the USA generation path
            self.assertNotIn('playable', result)     # nothing registered yet

    def test_registered_build_makes_the_disc_playable(self):
        profile = copy.deepcopy(identify.profiles.load('gow1'))
        region = next(r for r in profile['regions'] if r['id'] == 'asia-97399')
        target = next(r for r in profile['regions'] if r['id'] == region['code'])
        target['known_crc'] = discfs.pcsx2_crc(elf())
        target['known_text_sha1'] = discfs.text_sha1(elf())
        runner, prepared = self.root / 'runner.exe', self.root / 'SLPM_670.10'
        runner.write_bytes(b'runner')
        prepared.write_bytes(elf())
        build = {'region': region['id'], 'label': region['label'], 'runner': str(runner), 'elf': str(prepared),
                 'elf_crc': target['known_crc'], 'text_sha1': target['known_text_sha1']}
        profiles = patch.object(identify.profiles, 'all_profiles', return_value=[profile])
        registry = patch.object(identify, 'regional_builds', return_value=[build])
        with profiles, registry:
            result = identify.identify(iso(self.root / 'asia registered.iso', region['elf']))
            self.assertTrue(result['playable'])
            self.assertTrue(result['regional_installed'])
            self.assertEqual(result['reason_code'], 'regional_installed')
            self.assertEqual(result['regional_build'], region['id'])
            self.assertTrue(result['compatible'] is False)
            # A registered build whose files are gone is not offered: the registry records files, not promises.
            runner.unlink()
            result = identify.identify(iso(self.root / 'asia missing runner.iso', region['elf']))
            self.assertNotIn('playable', result)
            self.assertEqual(result['reason_code'], 'region_alias')

    def test_cli_returns_per_file_errors(self):
        bad = self.root / 'bad.iso'
        bad.write_bytes(b'bad')
        good = iso(self.root / 'japan.iso', 'SLPM_670.10')
        run = subprocess.run([sys.executable, '-I', str(Path(identify.__file__)), str(bad), str(good)],
                             capture_output=True, check=True)
        results = json.loads(run.stdout)
        self.assertEqual(results[0]['reason_code'], 'import_failed')
        self.assertEqual(results[1]['edition'], 'japan')
        bad.unlink()  # A failed ISO scan must not leak its Windows file handle.

    def test_invalid_chd_and_parent_rejected_without_tool(self):
        source = self.root / 'bad.CHD'
        source.write_bytes(b'not a CHD')
        with self.assertRaisesRegex(ValueError, 'CHDv5'):
            chd.resolve(source, self.root / 'cache')
        header = bytearray(124)
        header[:8] = b'MComprHD'
        struct.pack_into('>II', header, 8, 124, 5)
        header[104] = 1
        source.write_bytes(header)
        with self.assertRaisesRegex(ValueError, 'parent'):
            chd.resolve(source, self.root / 'cache')

    def test_download_rejects_wrong_hash_without_publication(self):
        source = self.root / 'download'
        source.write_bytes(b'wrong contents')
        target = self.root / 'tool.exe'
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            chd.download({'url': source.as_uri(), 'sha256': '0' * 64}, target)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix('.exe.partial').exists())

    def test_failed_subprocess_is_reported(self):
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            chd.run([sys.executable, '-c', 'import sys;print("failure");sys.exit(7)'])

    def test_extraction_handles_unicode_and_distinct_sources(self):
        source = iso(self.root / '\u65e5\u672c.iso')
        destination = self.root / 'prepared'
        prepare.extract(str(source), str(destination))
        with patch.object(prepare.subprocess, 'run', side_effect=AssertionError('must reuse same source')):
            prepare.extract(str(source), str(destination))
        other = iso(self.root / 'other.iso', 'SLPM_670.10')
        stamp = source.stat()
        os.utime(other, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        prepare.extract(str(other), str(destination))
        self.assertTrue((destination / 'SLPM_670.10').is_file())

    def test_concurrent_cache_writer_is_rejected(self):
        lock = self.root / 'cache.lock'
        code = 'import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import chd\nwith chd.locked(Path(sys.argv[2])): pass'
        with chd.locked(lock):
            result = subprocess.run([sys.executable, '-c', code, str(Path(chd.__file__).parent), str(lock)],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Another CHD import', result.stderr)
        with chd.locked(lock):
            pass


class RealChdTests(TempTests):
    def setUp(self):
        super().setUp()
        if not TOOL:
            self.skipTest('pass --chdman to run real synthetic CHD round trips')
        self.source = iso(self.root / 'synthetic disc.iso')
        self.image = self.root / 'synthetic disc.CHD'
        self.cache = self.root / 'cache'
        self.override = patch.dict(os.environ, {'GOW_CHDMAN': str(TOOL)})
        self.override.start()
        self.addCleanup(self.override.stop)

    def dvd(self):
        chd.run([TOOL, 'createdvd', '-i', self.source, '-o', self.image])

    def test_dvd_roundtrip_cache_and_repair(self):
        self.dvd()
        original_hash = chd.digest(self.image)
        output = Path(chd.resolve(self.image, self.cache))
        self.assertEqual(output.read_bytes(), self.source.read_bytes())
        with patch.object(chd, 'executable', side_effect=AssertionError('cache must avoid conversion')):
            self.assertEqual(chd.resolve(self.image, self.cache), str(output))
        output.write_bytes(b'broken cache')
        self.assertEqual(Path(chd.resolve(self.image, self.cache)).read_bytes(), self.source.read_bytes())
        self.assertEqual(chd.digest(self.image), original_hash)
        folder = prepare.extract(str(output), str(self.root / 'prepared'))
        self.assertEqual(discfs.FolderDisc(folder).read('SCUS_973.99'), elf())

    def test_legacy_mode1_roundtrip(self):
        cue = self.root / 'source.cue'
        cue.write_text('FILE "synthetic disc.iso" BINARY\n  TRACK 01 MODE1/2048\n    INDEX 01 00:00:00\n')
        chd.run([TOOL, 'createcd', '-i', cue, '-o', self.image])
        self.assertEqual(Path(chd.resolve(self.image, self.cache)).read_bytes(), self.source.read_bytes())

    def test_low_space_and_failed_extract_do_not_publish(self):
        self.dvd()
        usage = chd.shutil.disk_usage(self.root)
        with patch.object(chd.shutil, 'disk_usage', return_value=usage._replace(free=0)):
            with self.assertRaisesRegex(RuntimeError, 'space'):
                chd.resolve(self.image, self.cache)
        original_run = chd.run
        def failing(args):
            if args[1] == 'extractdvd':
                Path(args[-1]).write_bytes(b'partial')
                raise RuntimeError('interrupted extraction')
            return original_run(args)
        with patch.object(chd, 'run', side_effect=failing):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                chd.resolve(self.image, self.cache)
        self.assertFalse(list(self.cache.glob('*.iso')))
        self.assertFalse(list(self.cache.glob('*.json')))
        self.assertEqual([p for p in self.cache.iterdir() if p.is_dir()], [])

    def test_changed_source_is_rejected(self):
        self.dvd()
        original_run = chd.run
        def changing(args):
            result = original_run(args)
            if args[1] == 'extractdvd':
                stat = self.image.stat()
                os.utime(self.image, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10000000))
            return result
        with patch.object(chd, 'run', side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                chd.resolve(self.image, self.cache)
        self.assertFalse(list(self.cache.glob('*.iso')))

    def test_corrupt_chd_is_rejected(self):
        self.dvd()
        with open(self.image, 'r+b') as stream:
            stream.seek(64)
            value = stream.read(1)[0]
            stream.seek(64)
            stream.write(bytes([value ^ 255]))
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            chd.resolve(self.image, self.cache)
        self.assertFalse(list(self.cache.glob('*.iso')))

    def test_mixed_tracks_are_rejected(self):
        (self.root / 'audio.bin').write_bytes(bytes(2352 * 16))
        cue = self.root / 'mixed.cue'
        cue.write_text('FILE "synthetic disc.iso" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\n'
                       'FILE "audio.bin" BINARY\n TRACK 02 AUDIO\n INDEX 01 00:00:00\n')
        chd.run([TOOL, 'createcd', '-i', cue, '-o', self.image])
        with self.assertRaisesRegex(ValueError, 'one MODE1'):
            chd.resolve(self.image, self.cache)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--chdman')
    options, remaining = parser.parse_known_args()
    TOOL = Path(options.chdman).resolve() if options.chdman else None
    unittest.main(argv=[sys.argv[0]] + remaining)
