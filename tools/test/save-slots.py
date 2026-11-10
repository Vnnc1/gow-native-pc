"""Data-free regression tests for the read-only altar index and native previews."""
from pathlib import Path
import struct
import sys
import unittest
import zlib
import subprocess
import tempfile

COMPILER = None
if '--compiler' in sys.argv:
    p = sys.argv.index('--compiler')
    COMPILER = Path(sys.argv[p + 1]).absolute()  # Keep clang++'s driver name when it is a symlink.
    del sys.argv[p:p + 2]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'disc'))
from save_slots import CardError, slots, preview_png, wad_resources, location_names

NAME = 'test-save-directory'


def fixture():
    raw = bytearray(8388608)
    raw[:28] = b'Sony PS2 Memory Card Format '
    struct.pack_into('<HH', raw, 40, 512, 2)
    struct.pack_into('<III', raw, 52, 41, 8135, 0)
    struct.pack_into('<I', raw, 80, 8)
    for i in range(32):
        struct.pack_into('<I', raw, 8 * 1024 + i * 4, 9 + i)
    def chain(start, count):
        for c in range(start, start + count):
            struct.pack_into('<I', raw, (9 + c // 256) * 1024 + c % 256 * 4,
                             0xffffffff if c == start + count - 1 else 0x80000000 | (c + 1))
    def entry(cluster, offset, name, mode, size, first):
        p = (41 + cluster) * 1024 + offset * 512
        struct.pack_into('<H', raw, p, mode)
        struct.pack_into('<I', raw, p + 4, size)
        struct.pack_into('<I', raw, p + 16, first)
        raw[p + 24:p + 32] = struct.pack('<6BH', 0, 30, 20, 10, 9, 11, 2026)
        raw[p + 64:p + 64 + len(name)] = name.encode()
    chain(0, 1); chain(1, 2); chain(3, 1); chain(4, 80)
    entry(0, 0, '.', 0x8427, 2, 0)
    entry(0, 1, NAME, 0x8427, 3, 1)
    entry(1, 0, '.', 0x8427, 0, 0)
    entry(1, 1, NAME, 0x8417, 68, 3)
    entry(1, 2, 'data4.bin', 0x8417, 81920, 4)
    struct.pack_into('<iIfhBB', raw, 44 * 1024, 4, 0xcafebad1, 90.5, 12, 1, 0)
    for i in range(1, 4):
        struct.pack_into('<i', raw, 44 * 1024 + i * 16, -1)
    struct.pack_into('<I', raw, 45 * 1024, 0xcafebad1)
    raw[45 * 1024 + 8:45 * 1024 + 16] = b'Athn06C\0'
    return raw


class Tests(unittest.TestCase):
    @unittest.skipUnless(COMPILER, 'Pass --compiler to validate the production C++ reader')
    def test_production_cpp_reader(self):
        with tempfile.TemporaryDirectory(prefix='native-slots-') as tmp:
            work = Path(tmp)
            source = work / 'read.cpp'
            source.write_text('''#include "native_save_slots.h"
#include <iostream>
#include <cassert>
#include <cstdlib>
int main(int argc,char **argv) {
#ifdef _WIN32
 _putenv_s("TZ","UTC");_tzset();
#else
 setenv("TZ","UTC",1);tzset();
#endif
 assert(gow_native_saves::localTime({0,30,10,5,10,11,0xea,7})=="09/11/2026 20:10:30");
 assert(gow_native_saves::localTime({0,0,0,0,30,2,0xea,7}).empty());
 if(argc!=3)return 3;
 try {for(const auto &s:gow_native_saves::read(argv[1],argv[2]))
 std::cout<<s.slot<<":"<<s.file<<":"<<s.location<<"\\n";
 }catch(const std::exception &){return 2;}return 0;
}''')
            exe = work / 'read.exe'
            include = Path(__file__).resolve().parents[2] / 'launcher/src'
            build = subprocess.run([str(COMPILER), '-std=c++17', '-Wall', '-Wextra', '-Werror', '-static',
                                    '-I' + str(include), str(source), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            raw = fixture()
            cases = [raw, b''.join(raw[p:p + 512] + b'\xff' * 16 for p in range(0, len(raw), 512)), raw[:-1]]
            for offset, value in [(52, 9000), (80, 9000), (44 * 1024, 5), (45 * 1024, 0),
                                  (9 * 1024 + 4 * 4, 0x80000004)]:
                bad = bytearray(raw); struct.pack_into('<I', bad, offset, value); cases.append(bad)
            for i, data in enumerate(cases):
                card = work / f'{i}.ps2'; card.write_bytes(data)
                run = subprocess.run([str(exe), str(card), NAME], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0 if i < 2 else 2, run.stderr)
                if i < 2: self.assertEqual(run.stdout.strip(), '0:4:12')
                self.assertEqual(card.read_bytes(), data)

    def test_index_not_filename_order(self):
        result = slots(fixture(), NAME)
        self.assertEqual([(s['slot'], s['file'], s['location']) for s in result], [(0, 4, 12)])
        self.assertEqual(result[0]['time'], '2026-11-09T10:20:30')
        self.assertEqual(result[0]['seconds'], 90.5)

    def test_ecc_card_equivalence_and_no_mutation(self):
        raw = fixture(); before = bytes(raw)
        ecc = b''.join(raw[p:p + 512] + b'\xff' * 16 for p in range(0, len(raw), 512))
        self.assertEqual(slots(raw, NAME), slots(ecc, NAME))
        self.assertEqual(bytes(raw), before)

    def test_corruption_rejected(self):
        for offset, value in [(52, 9000), (80, 9000), (44 * 1024, 5),
                              (45 * 1024, 0), (9 * 1024 + 4 * 4, 0x80000004)]:
            with self.subTest(offset=offset):
                raw = fixture(); struct.pack_into('<I', raw, offset, value)
                with self.assertRaises(CardError): slots(raw, NAME)
        with self.assertRaises(CardError): slots(fixture()[:-1], NAME)

    def test_duplicate_slot_rejected(self):
        raw = fixture(); p = 44 * 1024
        raw[p + 16:p + 32] = raw[p:p + 16]
        with self.assertRaises(CardError): slots(raw, NAME)

    def test_absent_game_and_empty_slots(self):
        raw = fixture()
        self.assertEqual(slots(raw, 'other-game'), [])
        struct.pack_into('<i', raw, 44 * 1024, -1)
        self.assertEqual(slots(raw, NAME), [])

    def test_wad_bounds_and_names(self):
        data = b'1*\nEmpty\n\n*601*\nShip\n\n*602*\nHydra\n'
        raw = struct.pack('<II24s', 111, len(data), b'msgs_en.txt') + data
        raw += b'\0' * (-len(raw) % 16)
        self.assertEqual(location_names(raw, 'msgs_en.txt', 600), {1: 'Ship', 2: 'Hydra'})
        with self.assertRaises(CardError): wad_resources(raw[:-1])

    def test_preview_palette_and_dimensions(self):
        txr = struct.pack('<I24s24s24sIII', 7, b'image', b'palette', b'', 0, 0, 0)
        image = struct.pack('<6I', 12, 128, 80, 0, 8, 1) + bytes([8]) * 10240
        palette = bytearray(1024)
        palette[16 * 4:16 * 4 + 4] = bytes([11, 22, 33, 128])
        resources = {'TXR_SavePt01': txr, 'image': image,
                     'palette': struct.pack('<6I', 12, 16, 16, 0, 32, 1) + palette}
        png = preview_png(resources, 1)
        self.assertEqual(struct.unpack_from('>II', png, 16), (128, 80))
        length = struct.unpack_from('>I', png, 33)[0]
        decoded = zlib.decompress(png[41:41 + length])
        self.assertEqual(decoded, (b'\0' + bytes([11, 22, 33, 255]) * 128) * 80)
        resources['image'] = image[:-1]
        with self.assertRaises(CardError): preview_png(resources, 1)


if __name__ == '__main__':
    unittest.main()
