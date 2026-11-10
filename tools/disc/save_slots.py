"""Read USA God of War altar slots without changing a PS2 card.

The four index records, not directory enumeration, identify the current saves.
No load or restore operation is performed by this module.
"""
import datetime
import math
from pathlib import Path
import struct
import re
import zlib
import os
import tempfile


class CardError(ValueError):
    pass


class Card:
    def __init__(self, raw):
        if len(raw) == 8650752:
            raw = b''.join(raw[p:p + 512] for p in range(0, len(raw), 528))
        if len(raw) != 8388608 or not raw.startswith(b'Sony PS2 Memory Card Format '):
            raise CardError('Unsupported memory card')
        self.raw = raw
        if self.u16(40) != 512 or self.u16(42) != 2:
            raise CardError('Unsupported card geometry')
        self.base = self.u32(52)
        self.end = self.u32(56)
        if not 0 < self.base < 8192 or not 0 < self.end <= 8192 - self.base:
            raise CardError('Invalid allocation bounds')
        self.fat = []
        for i in range((self.end + 65535) // 65536):
            indirect = self.u32(80 + i * 4)
            if not 0 < indirect < self.base:
                raise CardError('Invalid indirect FAT')
            for j in range(min(256, (self.end + 255) // 256 - len(self.fat))):
                block = self.u32(indirect * 1024 + j * 4)
                if not 0 < block < self.base:
                    raise CardError('Invalid FAT')
                self.fat.append(block)

    def u16(self, p):
        return struct.unpack_from('<H', self.raw, p)[0]

    def u32(self, p):
        return struct.unpack_from('<I', self.raw, p)[0]

    def chain(self, cluster, size):
        if not 0 <= size <= len(self.raw):
            raise CardError('Invalid file size')
        result = bytearray()
        seen = set()
        while len(result) < size:
            if not 0 <= cluster < self.end or cluster in seen:
                raise CardError('Invalid or cyclic allocation chain')
            seen.add(cluster)
            nxt = self.u32(self.fat[cluster // 256] * 1024 + cluster % 256 * 4)
            if not nxt & 0x80000000:
                raise CardError('Unallocated cluster')
            p = (self.base + cluster) * 1024
            result.extend(self.raw[p:p + min(1024, size - len(result))])
            cluster = nxt & 0x7fffffff
        return bytes(result)

    def directory(self, cluster, count=None):
        if count is None:
            first = self.chain(cluster, 512)
            count = struct.unpack_from('<I', first, 4)[0]
        if not 1 <= count <= 1024:
            raise CardError('Invalid directory length')
        raw = self.chain(cluster, count * 512)
        entries = {}
        for p in range(0, len(raw), 512):
            mode, = struct.unpack_from('<H', raw, p)
            if not mode & 0x8000:
                continue
            name = raw[p + 64:p + 96].split(b'\0', 1)[0].decode('ascii', errors='strict')
            if name in entries:
                raise CardError('Duplicate directory entry')
            entries[name] = (mode, struct.unpack_from('<I', raw, p + 4)[0],
                             struct.unpack_from('<I', raw, p + 16)[0], raw[p + 24:p + 32])
        return entries


def slots(raw, directory):
    """Return occupied native slots in display order; directory comes from profile."""
    card = Card(raw)
    root = card.directory(card.u32(60))
    if directory not in root:
        return []
    entry = root[directory]
    if not entry[0] & 0x20:
        raise CardError('Save directory is not a directory')
    files = card.directory(entry[2], entry[1])
    if directory not in files or files[directory][1] != 68:
        raise CardError('Missing or invalid save index')
    index = card.chain(files[directory][2], 68)
    result = []
    used = set()
    for slot in range(4):
        file_id, magic, seconds, location, difficulty = struct.unpack_from('<iIfhB', index, slot * 16)
        if file_id < 0 or magic != 0xcafebad1:
            continue
        if file_id > 4 or file_id in used or not math.isfinite(seconds) or not 0 <= seconds <= 1e9 or not 1 <= location <= 99:
            raise CardError('Invalid save index record')
        used.add(file_id)
        file = files.get(f'data{file_id}.bin')
        if file is None or not file[0] & 0x10 or file[1] != 81920:
            raise CardError('Missing save payload')
        payload = card.chain(file[2], file[1])
        if struct.unpack_from('<I', payload)[0] != 0xcafebad1:
            raise CardError('Invalid save payload')
        _, second, minute, hour, day, month, year = struct.unpack('<6BH', file[3])
        try:
            timestamp = datetime.datetime(year, month, day, hour, minute, second).isoformat()
        except ValueError:
            timestamp = None
        result.append(dict(slot=slot, file=file_id, location=location, seconds=seconds,
                           difficulty=difficulty, time=timestamp,
                           zone=payload[8:16].split(b'\0', 1)[0].decode('ascii', errors='replace')))
    return result


def wad_resources(raw):
    if len(raw) > 16 * 1024 * 1024:
        raise CardError('Resource archive too large')
    result = {}
    p = 0
    while p < len(raw):
        if p + 32 > len(raw):
            raise CardError('Truncated resource header')
        tag, size = struct.unpack_from('<II', raw, p)
        name = raw[p + 8:p + 32].split(b'\0', 1)[0].decode('ascii', errors='replace')
        size = 0 if tag == 24 else size
        end = p + 32 + size
        if end > len(raw):
            raise CardError('Truncated resource')
        if size:
            result[name] = raw[p + 32:end]
        p = (end + 15) & ~15
    if p != len(raw):
        raise CardError('Truncated resource padding')
    return result


def preview_png(resources, location):
    """Decode the game's 128x80 indexed altar artwork, without image dependencies."""
    txr = resources.get(f'TXR_SavePt{location:02d}', b'')
    if len(txr) != 88 or struct.unpack_from('<I', txr)[0] != 7:
        raise CardError('Unsupported save preview texture')
    gfx, pal = (resources.get(txr[p:p + 24].split(b'\0')[0].decode('ascii'), b'') for p in (4, 28))
    if len(gfx) != 24 + 128 * 80 or struct.unpack_from('<6I', gfx) != (12, 128, 80, 0, 8, 1):
        raise CardError('Unsupported save preview image')
    if len(pal) != 24 + 1024 or struct.unpack_from('<6I', pal) != (12, 16, 16, 0, 32, 1):
        raise CardError('Unsupported save preview palette')
    scanlines = bytearray()
    for y in range(80):
        scanlines.append(0)
        for x in range(128):
            # PSMT8 column addressing; CLUT exchanges index bits 3 and 4.
            column = (((y & 12) // 2 + (y & 1)) % 8) * 256
            column += ((x + ((y + 2) // 4 % 2) * 4) % 8) * 4
            address = (y // 16) * 2048 + (x // 16) * 32 + column + (y // 2 % 2) + (x // 8 % 2) * 2
            index = gfx[24 + address]
            index = (index & ~24) | ((index & 8) << 1) | ((index & 16) >> 1)
            color = pal[24 + index * 4:28 + index * 4]
            scanlines.extend(color[:3] + bytes([min(255, color[3] * 255 // 128)]))
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', 128, 80, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


def location_names(raw, resource, base):
    text = wad_resources(raw).get(resource, b'').decode('latin1')
    messages = re.split(r'\*(\d+)\*\s*\n', text)
    names = {}
    for i in range(1, len(messages) - 1, 2):
        location = int(messages[i]) - base
        if 1 <= location <= 99:
            name = messages[i + 1].strip()
            if name and len(name) <= 160 and '\n' not in name:
                names[location] = name
    return names


def prepare_assets(folder, profile, language='en'):
    """Cache disc-owned previews next to the prepared edition; never touch its card."""
    import discfs
    spec = profile.get('saves')
    if not spec:
        return
    disc = discfs.FolderDisc(folder)
    toc = discfs.parse_toc(disc.read(profile['disc']['toc']))
    bounded = [entry for entry in toc if 0 < entry[3] <= 16 * 1024 * 1024]
    textures = wad_resources(disc.pak_entry(bounded, spec['preview_wad']))
    names = location_names(disc.pak_entry(bounded, spec['names_wad']), spec['names_resource'], spec['location_message_base'])
    output = Path(folder) / '.gow-save-slots'
    output.mkdir(exist_ok=True)
    def publish(name, data):
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=output)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(data)
            os.replace(temporary, output / name)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    for location, name in names.items():
        # This translation encodes accents as sequences for its custom game font.
        if language.lower().startswith('pt'):
            for old, new in [("'a", 'á'), ("'e", 'é'), ("'i", 'í'), ("'o", 'ó'), ("'u", 'ú'),
                             ('"a', 'ã'), ('"o', 'õ'), ('wa', 'â'), ('we', 'ê'), ('wo', 'ô'), (';a', 'à'), ('Y', 'ç')]:
                name = name.replace(old, new)
        publish(f'{location}.png', preview_png(textures, location))
        publish(f'{location}.name', name.encode('utf-8'))
    publish('directory', spec['directory'].encode('ascii'))


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card', type=Path, nargs='?')
    parser.add_argument('--directory')
    parser.add_argument('--prepare-data', type=Path)
    parser.add_argument('--game', default='gow1')
    args = parser.parse_args()
    if args.prepare_data:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
        import profile as profiles
        import discfs
        prof = profiles.load(args.game)
        base = args.prepare_data.resolve()
        manifest = base / 'languages.json'
        if manifest.is_file():
            if manifest.stat().st_size > 1024 * 1024: parser.error('Language manifest too large')
            for entry in json.loads(manifest.read_text(encoding='utf-8')).get('languages', [])[:64]:
                elf = Path(entry['elf']).resolve()
                if not elf.is_relative_to(base) or not elf.is_file() or elf.stat().st_size > 16 * 1024 * 1024:
                    continue
                if discfs.text_sha1(elf.read_bytes()) != prof['executable']['text_sha1']:
                    continue
                try:
                    prepare_assets(elf.parent, prof, entry['language'])
                    print('Save previews prepared:', entry['language'])
                except (OSError, ValueError, KeyError) as error:
                    print('Save previews unavailable:', error)
        raise SystemExit(0)
    if not args.card or not args.directory:
        parser.error('Specify a card and --directory, or --prepare-data')
    if args.card.stat().st_size not in (8388608, 8650752):
        parser.error('Unsupported memory card size')
    print(json.dumps(slots(args.card.read_bytes(), args.directory), ensure_ascii=False, indent=2))
