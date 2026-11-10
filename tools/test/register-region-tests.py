"""Registration rejects wrong code, shared data and USA builds before publication."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/pipeline'))
sys.path.insert(0, str(ROOT / 'tools/disc'))
import register_region
from import_test import elf as synthetic_elf


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = self.root / 'build/ps2xRuntime/game.exe'
        self.elf = self.root / 'region/disc/REGION.ELF'
        self.data = self.root / 'region'
        self.source = self.root / 'source/PS2Recomp'
        payload = synthetic_elf()
        self.write(self.runner, b'runner')
        self.write(self.elf, payload)
        self.write(self.elf.parent / '.disc_layout', b'layout')
        (self.elf.parent / 'IOP_MOD').mkdir()
        self.write(self.source.parent / 'src/gow_overrides.cpp', b'REGION.ELF')
        self.write(self.runner.parent.parent / 'CMakeCache.txt',
                   ('CMAKE_HOME_DIRECTORY:INTERNAL=' + self.source.as_posix()).encode())
        self.write(self.root / 'games/demo/regions/region/runtime.patch', b'overlay')
        self.write(self.root / 'games/demo/game.toml', f'''[executable]
name = "USA.ELF"
[[regions]]
id = "region"
elf = "REGION.ELF"
label = "Regional fixture"
known_crc = "{register_region.pcsx2_crc(payload)}"
known_text_sha1 = "{register_region.text_sha1(payload)}"
experimental_frame_pc = "0x100000"
'''.encode())
        self.manifest = self.root / 'data/demo/regional-builds.json'

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def register(self):
        return register_region.register(self.root, 'demo', 'region', self.runner, self.elf, self.data)

    def test_registration_is_idempotent_and_does_not_touch_primary_manifest(self):
        primary = self.root / 'data/demo/languages.json'
        self.write(primary, b'original manifest')
        self.register(); self.register()
        self.assertEqual(len(json.loads(self.manifest.read_text())['builds']), 1)
        self.assertEqual(primary.read_bytes(), b'original manifest')

    def test_wrong_elf_preserves_previous_registration(self):
        self.register()
        previous = self.manifest.read_bytes()
        changed = bytearray(self.elf.read_bytes()); changed[320] ^= 1
        self.elf.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.register()
        self.assertEqual(self.manifest.read_bytes(), previous)

    def test_primary_runtime_cannot_be_registered_as_regional(self):
        self.write(self.runner.parent.parent / 'CMakeCache.txt',
                   ('CMAKE_HOME_DIRECTORY:INTERNAL=' + (self.root / 'engine/runtime/PS2Recomp').as_posix()).encode())
        with self.assertRaisesRegex(ValueError, 'USA build'):
            self.register()
        self.assertFalse(self.manifest.exists())

    def test_shared_primary_data_is_rejected(self):
        self.data = self.root / 'data/demo'
        with self.assertRaisesRegex(ValueError, 'USA data'):
            self.register()
        self.assertFalse(self.manifest.exists())

    def test_build_cache_without_source_root_is_rejected(self):
        self.write(self.runner.parent.parent / 'CMakeCache.txt', b'CMAKE_CXX_COMPILER=clang++\n')
        with self.assertRaisesRegex(ValueError, 'CMAKE_HOME_DIRECTORY'):
            self.register()
        self.assertFalse(self.manifest.exists())


if __name__ == '__main__':
    unittest.main()
