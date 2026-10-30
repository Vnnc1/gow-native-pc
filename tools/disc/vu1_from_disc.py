"""VU1 microcode straight from the disc: micro-memory images for the native VU1 build without playing.

usage: python -I tools/disc/vu1_from_disc.py --game gow1 --gen <vu1n_gen.py> <iso or extracted folder> <out dir>
       [--max-images N] [--compare <recorded micro-memory dir>]

--compare: how many of the blocks recorded while playing (data/<game>/vu1_capture, its disc_*.bin left out) the disc scan
found: at the same micro-memory address (what the build can use as is) and anywhere (same words at another address: the
game loads that program elsewhere at run time).

The game uploads VU1 microcode with VIF MPG commands (code 0x4A: NUM 64-bit instructions to micro memory address
IMMEDIATE * 8) that sit in its files as prebuilt DMA/VIF packets. This scans the boot ELF and every file of the game's TOC
for them, applies the uploads of each file in order to a 16 KB micro-memory image and keeps a snapshot each time an
upload holds a program end (E bit). The snapshots are cut down to the ones that add VU1 blocks not seen yet (block = the
runtime's key: entry pc + words, see vu1n_gen.py), so the build compiles each distinct block once, and written as
<out>/disc_<hash>.bin, the same format as the recorded micro memories (data/<game>/vu1_capture).

A block built from a snapshot whose neighbouring code differs from what the game really has resident only costs
compile time: the runtime looks blocks up by their exact words, so such a block never runs. Blocks the scan cannot see
(microcode built at run time, entries through a register) still come from the recording and the background compiler.
Heuristic, prototype: an MPG header is accepted when its data is 64-bit aligned, fits the 16 KB micro memory and decodes as
VU instructions (see plausible()). Output is game data: it stays in data/ and is never published.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'pipeline'))
import discfs  # noqa: E402

CODE_SIZE = 16384
VIF_MPG = 0x4A


def load_gen(path):
    spec = importlib.util.spec_from_file_location('vu1n_gen', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Every valid VU lower instruction (the upper side is checked with the generator's decoder): opcodes, the 0x40 group's
# integer ops and the 0x40 group's special codes ((l & 3) | ((l >> 4) & 0x7C)): moves, loads/stores, FDIV, random, EFU,
# XTOP/XITOP/XGKICK, MFP.
LOWER_OPS = {0x00, 0x01, 0x04, 0x05, 0x08, 0x09, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x1A, 0x1B, 0x1C,
             0x20, 0x21, 0x24, 0x25, 0x28, 0x29, 0x2C, 0x2D, 0x2E, 0x2F}
LOWER_40_INT = {0x30, 0x31, 0x32, 0x34, 0x35}
LOWER_40_SPECIAL = set(range(0x30, 0x44)) | {0x64, 0x68, 0x69, 0x6C, 0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x78, 0x79,
                                              0x7A, 0x7B, 0x7C, 0x7D, 0x7E}
MIN_PROGRAM_PAIRS = 8


def valid_pair(gen, lower, upper):
    if (upper >> 25) & 3 or gen.classify(upper)[0] == 'other':   # bits 25-26 are zero in every upper instruction
        return False
    if upper >> 31:                                                  # I bit: the lower word is a float immediate
        return True
    op = lower >> 25
    if op == 0x40:
        fn = lower & 0x3F
        return fn in LOWER_40_INT if fn < 0x3C else ((lower & 3) | ((lower >> 4) & 0x7C)) in LOWER_40_SPECIAL
    return op in LOWER_OPS


def plausible(gen, code):
    """Every pair is a valid VU instruction pair (all-zero padding aside) and there are at least a few. EE code is full of
    words whose top byte is 0x4A (COP2 / VU0 macro instructions), so a looser test took MIPS code for microcode."""
    real = 0
    for i in range(len(code) // 8):
        lower, upper = struct.unpack_from('<II', code, i * 8)
        if lower == 0 and upper == 0:      # padding between programs
            continue
        if not valid_pair(gen, lower, upper):
            return False
        real += 1
    return real >= 4


def uploads(gen, data):
    """(header offset, end offset, micro memory address, code) of the plausible MPG uploads in one file, in file order."""
    out = []
    # IRQ is bit 7 of the command byte; both MPG and MPG|IRQ are legal.
    consumed = 0
    for match in re.finditer(rb'[\x4a\xca]', data):
        p = match.start()
        if p < max(3, consumed):
            continue
        w = p - 3                                    # the code byte is the word's top byte (little endian)
        if w % 4 == 0 and w + 4 <= len(data):
            word, = struct.unpack_from('<I', data, w)
            if (word >> 24) & 0x7F == VIF_MPG:
                num = (word >> 16) & 0xFF or 256
                addr = (word & 0xFFFF) * 8
                start, end = w + 4, w + 4 + num * 8
                if start % 8 == 0 and addr + num * 8 <= CODE_SIZE and end <= len(data):
                    code = data[start:end]
                    if plausible(gen, code):
                        out.append((w, end, addr, code))
                        consumed = end + 3
                        continue
    return out


def scan(gen, data):
    """Snapshots (16 KB images) of the MPG uploads in one file: uploads that follow each other in the VIF stream (only
    VIF NOPs between them) are one program load; after each load that holds a program end (E bit) the image is kept."""
    image = bytearray(CODE_SIZE)
    snaps = []
    ups = uploads(gen, data)
    has_end = False
    pairs = 0
    for k, (w, end, addr, code) in enumerate(ups):
        image[addr:addr + len(code)] = code
        n = len(code) // 8
        pairs += n
        # a program ends with an E bit followed by its delay pair
        has_end = has_end or any((struct.unpack_from('<I', code, i * 8 + 4)[0] >> 30) & 1 for i in range(n - 1))
        nxt = ups[k + 1][0] if k + 1 < len(ups) else None
        joined = nxt is not None and nxt - end <= 8 and data[end:nxt] == bytes(nxt - end)
        if not joined:
            if has_end and pairs >= MIN_PROGRAM_PAIRS:
                snaps.append(bytes(image))
            has_end = False
            pairs = 0
    return snaps


def block_keys(gen, image, words_only=None):
    """the runtime's block keys (pc + words) of an image; words_only (a set) also receives the keys of the words alone"""
    keys = set()
    for pc in gen.heads_of(image, set()):
        pairs = gen.extent(image, pc)
        if pairs:
            words = [x for pr in pairs for x in pr]
            keys.add(gen.fnv_block(pc, words))
            if words_only is not None:
                words_only.add(gen.fnv_block(0, words))
    return keys


def compare(gen, disc_keys, disc_words, recorded_dir):
    rec_keys, rec_words = {}, {}
    files = [f for f in sorted(os.listdir(recorded_dir)) if f.endswith('.bin') and not f.startswith('disc_')]
    for k, f in enumerate(files):
        img = open(os.path.join(recorded_dir, f), 'rb').read()
        if len(img) != CODE_SIZE:
            continue
        for pc in gen.heads_of(img, set()):
            pairs = gen.extent(img, pc)
            if pairs:
                words = [x for pr in pairs for x in pr]
                rec_keys[gen.fnv_block(pc, words)] = gen.fnv_block(0, words)
        if k % 500 == 0:
            print(f'@@status comparing with the recording: {k}/{len(files)} micro memories', flush=True)
    same_pc = sum(1 for key in rec_keys if key in disc_keys)
    anywhere = sum(1 for w in rec_keys.values() if w in disc_words)
    n = max(1, len(rec_keys))
    print(f'[vu1-disc] recorded: {len(files)} micro memories, {len(rec_keys)} distinct blocks; found on the disc at the '
          f'same address: {same_pc} ({100 * same_pc / n:.1f} %), same code at any address: {anywhere} ({100 * anywhere / n:.1f} %)')


def disc_files(disc, prof):
    """(name, bytes) of the boot ELF and of every TOC entry"""
    elf = prof['executable']['name']
    if disc.has(elf):
        data = bytearray(disc.read(elf))
        try:                                         # the EE code itself (.text) holds no VIF packets
            off, size, _ = discfs.elf_sections(bytes(data))['.text']
            data[off:off + size] = bytes(size)
        except (KeyError, struct.error, ValueError):
            pass
        yield elf, bytes(data)
    toc_name = prof['disc']['toc']
    if disc.has(toc_name):
        toc = discfs.parse_toc(disc.read(toc_name))
        seen = set()
        for _, name, _, _, _ in toc:
            if name in seen:
                continue
            seen.add(name)
            try:
                yield name, disc.pak_entry(toc, name)
            except KeyError:
                pass


def source_signature(path, prof, generator):
    """Local cache identity: source metadata, profile and both implementations. No game bytes in the report."""
    names = [path] if os.path.isfile(path) else [os.path.join(path, n) for n in
             [prof['executable']['name'], prof['disc']['toc'], *prof['disc']['paks'], '.disc_layout']]
    sources = []
    for name in names:
        if os.path.isfile(name):
            st = os.stat(name)
            sources.append((os.path.abspath(name), st.st_size, st.st_mtime_ns))
    return hashlib.sha256(json.dumps([sources, prof,
        hashlib.sha256(open(__file__, 'rb').read()).hexdigest(),
        hashlib.sha256(open(generator, 'rb').read()).hexdigest()], sort_keys=True).encode()).hexdigest()


def read_cached(report_path, signature, out):
    try:
        report = json.load(open(report_path, encoding='utf-8'))
        if report['signature'] != signature or not report['complete']:
            return None
        actual = {name for name in os.listdir(out) if re.fullmatch(r'disc_[0-9a-f]{16}\.bin', name)}
        if actual != set(report['outputs']):
            return None
        for name, digest in report['outputs'].items():
            if not re.fullmatch(r'disc_[0-9a-f]{16}\.bin', name):
                return None
            if hashlib.sha256(open(os.path.join(out, name), 'rb').read()).hexdigest() != digest:
                return None
        return report
    except (OSError, ValueError, KeyError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default='gow1')
    ap.add_argument('--gen', required=True, help='vu1n_gen.py of the runtime')
    ap.add_argument('--max-images', type=int, default=0)
    ap.add_argument('--compare', default='')
    ap.add_argument('--force', action='store_true', help='rescan even when source metadata and outputs match')
    ap.add_argument('disc')
    ap.add_argument('out')
    a = ap.parse_args()
    import profile as game_profile  # tools/pipeline/profile.py
    prof = game_profile.load(a.game)
    gen = load_gen(a.gen)
    os.makedirs(a.out, exist_ok=True)
    signature = source_signature(a.disc, prof, a.gen)
    report_path = os.path.join(a.out, 'disc-report.json')
    cached = None if a.force or a.max_images or a.compare else read_cached(report_path, signature, a.out)
    if cached:
        print(f"[vu1-disc] cache hit: {cached['files']} files, {cached['kept']} images, {cached['blocks']} blocks")
        return
    disc = discfs.open_disc(a.disc)
    started = time.monotonic()
    outputs = {}
    seen_images, keys, words = set(), set(), set()
    last = None
    files = uploads = kept = 0
    for name, data in disc_files(disc, prof):
        files += 1
        snaps = scan(gen, data)
        uploads += len(snaps)
        for img in snaps:
            h = hashlib.sha1(img).hexdigest()[:16]
            if h in seen_images:
                continue
            seen_images.add(h)
            new = block_keys(gen, img, words) - keys
            if not new:
                continue
            keys |= new
            name_out = f'disc_{h}.bin'
            path = os.path.join(a.out, name_out)
            # Preserve timestamps of identical outputs: Ninja then keeps its compiled VU1 objects.
            if not os.path.exists(path) or open(path, 'rb').read() != img:
                with open(path + '.tmp', 'wb') as f:
                    f.write(img)
                os.replace(path + '.tmp', path)
            outputs[name_out] = hashlib.sha256(img).hexdigest()
            kept += 1
            if a.max_images and kept >= a.max_images:
                break
        if (kept, len(keys)) != last or files % 100 == 0:   # one line when something changed (not one per file)
            last = (kept, len(keys))
            print(f'@@status VU1 microcode: {files} files read, {kept} images, {len(keys)} blocks', flush=True)
        if a.max_images and kept >= a.max_images:
            break
    complete = not (a.max_images and kept >= a.max_images)
    if complete:
        # Only prune this scanner's files after a completed scan. Recordings remain untouched.
        for name in os.listdir(a.out):
            if re.fullmatch(r'disc_[0-9a-f]{16}\.bin', name) and name not in outputs:
                os.remove(os.path.join(a.out, name))
    report = dict(signature=signature, complete=complete, files=files, uploads=uploads, kept=kept,
                  blocks=len(keys), seconds=round(time.monotonic() - started, 3), outputs=outputs)
    with open(report_path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    os.replace(report_path + '.tmp', report_path)
    print(f'[vu1-disc] {files} files, {uploads} program uploads, {len(seen_images)} distinct images, '
          f'{kept} kept, {len(keys)} distinct blocks -> {a.out}')
    if not kept:
        print('@@status No usable VU1 uploads found; use the runtime JIT or recorded code. Disc coverage is not guaranteed.')
    if a.compare:
        compare(gen, keys, words, a.compare)


if __name__ == '__main__':
    main()
