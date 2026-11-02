"""Shared disc helpers: ISO images read in place, extracted disc folders (.disc_layout), the game's TOC, ELF sections and
the PCSX2 game CRC. Used by identify.py and prepare.py; game-specific names come from the game profile.

Formats
- .disc_layout (written by iso_extract.py --layout): "sectors <n>", "layer1 <lsn>", "file <lsn> <size> <name>" lines.
  The runtime serves every listed file at its sector, so files can be added past the end of the disc.
- God of War TOC: 24-byte entries name[12], u32 part (0 = PART1.PAK, 1 = PART2.PAK), u32 size, u32 sector offset
  inside that PAK. The game reads its files only through it.
"""
import functools
import hashlib
import operator
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso_extract  # noqa: E402  (Waffle565's ISO9660 extractor, see its header)

SECTOR = 2048


def pcsx2_crc(elf: bytes) -> str:
    """PCSX2's game CRC: XOR of every little-endian 32-bit word of the ELF"""
    return '%08X' % functools.reduce(operator.xor, (w for (w,) in struct.iter_unpack('<I', elf[:len(elf) // 4 * 4])), 0)


def elf_sections(elf: bytes) -> dict:
    """{name: (file offset, size, vaddr)} of an ELF32 little-endian image"""
    e_shoff, = struct.unpack_from('<I', elf, 32)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', elf, 46)
    headers = [struct.unpack_from('<10I', elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    names = headers[e_shstrndx][4]
    return {elf[names + h[0]:elf.index(b'\0', names + h[0])].decode(): (h[4], h[5], h[3]) for h in headers}


def text_sha1(elf: bytes) -> str:
    off, size, _ = elf_sections(elf)['.text']
    return hashlib.sha1(elf[off:off + size]).hexdigest()


def boot_elf_name(system_cnf: bytes) -> str:
    """'SCUS_973.99' from 'BOOT2 = cdrom0:\\SCUS_973.99;1'"""
    for line in system_cnf.decode('latin1').splitlines():
        if line.strip().upper().startswith('BOOT2'):
            return line.split('\\')[-1].split(';')[0].strip()
    return ''


def parse_toc(raw: bytes) -> list:
    """[(byte offset, name, part, size, sector)]"""
    return [(i, raw[i:i + 12].split(b'\0')[0].decode('latin1')) + struct.unpack_from('<III', raw, i + 12)
            for i in range(0, len(raw) - 23, 24)]


def check_wad(data: bytes) -> bytes:
    """WAD = records {u32 tag, u32 size, char name[24], data[size] padded to 16}; tag 24 = value, no data"""
    pos = 0
    while pos + 32 <= len(data):
        tag, size = struct.unpack_from('<II', data, pos)
        pos += 32 + (((0 if tag == 24 else size) + 15) & ~15)
    if pos != len(data):
        raise ValueError('not a WAD')
    return data


class IsoDisc:
    """files of a PS2 DVD image, read in place"""

    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        try:
            files, self.layer1 = iso_extract.scan(self.f)
        except Exception:
            self.f.close()
            raise
        self.files = {name: (lba, size) for name, lba, size in files}

    def has(self, name):
        return name in self.files

    def read(self, name, limit=None):
        lba, size = self.files[name]
        self.f.seek(lba * SECTOR)
        return self.f.read(size if limit is None else min(size, limit))

    def pak_entry(self, toc, name):
        """data of a TOC entry, read from its PAK on the image (part 0 copy preferred)"""
        entries = sorted((e for e in toc if e[1] == name), key=lambda e: e[2])
        for _, _, part, size, sector in entries:
            pak = f'PART{part + 1}.PAK'
            if pak in self.files:
                self.f.seek((self.files[pak][0] + sector) * SECTOR)
                return self.f.read(size)
        raise KeyError(f'{name} not readable on {os.path.basename(self.path)}')


class FolderDisc:
    """an extracted disc folder (iso_extract.py --layout)"""

    def __init__(self, path):
        self.path = path
        self.head, self.layout = {}, []
        with open(os.path.join(path, '.disc_layout')) as layout:
            lines = layout.readlines()
        for line in lines:
            f = line.split()
            if f and f[0] == 'file':
                self.layout.append((int(f[1]), int(f[2]), ' '.join(f[3:])))
            elif f:
                self.head[f[0]] = f[1]

    def has(self, name):
        return os.path.isfile(os.path.join(self.path, name))

    def read(self, name, limit=None):
        with open(os.path.join(self.path, name), 'rb') as f:
            return f.read() if limit is None else f.read(limit)

    def lsn(self, name):
        for lsn, _, n in self.layout:
            if n == name:
                return lsn
        raise KeyError(name)

    def pak_entry(self, toc, name):
        entries = sorted((e for e in toc if e[1] == name), key=lambda e: e[2])
        for _, _, part, size, sector in entries:
            pak = os.path.join(self.path, f'PART{part + 1}.PAK')
            if os.path.isfile(pak):
                with open(pak, 'rb') as f:
                    f.seek(sector * SECTOR)
                    return f.read(size)
        raise KeyError(f'{name} not readable in {self.path}')


def open_disc(path):
    return FolderDisc(path) if os.path.isdir(path) else IsoDisc(path)
