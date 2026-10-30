"""Test of vu1_from_disc.py without game data: a fake extracted disc (SYSTEM files, a TOC, PART1.PAK) whose one TOC file
holds random bytes (with stray MPG-looking words) around VIF packets that upload a given micro memory in chunks of up to
256 instructions. The extractor must give back exactly the blocks of that micro memory.

usage: python -I tools/disc/vu1_from_disc_test.py --gen <vu1n_gen.py> <micro memory.bin>
       (e.g. the one written by the runtime's tests/vu1_jit_test --write)
"""
import argparse
import json
import os
import random
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vu1_from_disc  # noqa: E402


def vif_upload(code):
    """VIF stream: NOP padding so each MPG's data is 64-bit aligned, MPG (0x4A) headers, the instructions."""
    out = bytearray()
    used = [i for i in range(len(code) // 8) if code[i * 8:i * 8 + 8] != bytes(8)]
    if not used:
        return out
    first, last = used[0], used[-1] + 1
    pc = first
    while pc < last:
        num = min(256, last - pc)
        while (len(out) + 4) % 8:
            out += struct.pack('<I', 0)                    # VIF NOP
        out += struct.pack('<I', (0x4A << 24) | ((num & 0xFF) << 16) | pc)
        out += code[pc * 8:(pc + num) * 8]
        pc += num
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gen', required=True)
    ap.add_argument('micro')
    a = ap.parse_args()
    code = open(a.micro, 'rb').read()
    gen = vu1_from_disc.load_gen(a.gen)
    want = vu1_from_disc.block_keys(gen, code)
    packet = bytes(vif_upload(code))
    irq_packet = bytearray(packet)
    for offset, _, _, _ in vu1_from_disc.uploads(gen, packet):
        irq_packet[offset + 3] |= 0x80
    assert vu1_from_disc.scan(gen, bytes(irq_packet)) == vu1_from_disc.scan(gen, packet), 'MPG IRQ changes extraction'
    rng = random.Random(7)
    noise = bytearray(rng.getrandbits(8) for _ in range(64 * 1024))
    for _ in range(200):                                   # stray words that look like MPG headers
        p = rng.randrange(0, len(noise) - 8) & ~3
        noise[p + 3] = 0x4A
    wad = bytes(noise[:32768]) + bytes(vif_upload(code)) + bytes(noise[32768:])
    with tempfile.TemporaryDirectory() as disc, tempfile.TemporaryDirectory() as out:
        open(os.path.join(disc, '.disc_layout'), 'w').write('sectors 0\n')
        open(os.path.join(disc, 'SCUS_973.99'), 'wb').write(bytes(noise[:4096]))
        toc = b'TEST.WAD'.ljust(12, b'\0') + struct.pack('<III', 0, len(wad), 1)
        open(os.path.join(disc, 'GODOFWAR.TOC'), 'wb').write(toc)
        open(os.path.join(disc, 'PART1.PAK'), 'wb').write(bytes(2048) + wad)
        r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'vu1_from_disc.py'), '--game', 'gow1', '--gen', a.gen,
                            disc, out], capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr)
        if r.returncode:
            print(r.stderr)
            return 1
        manifest_path = os.path.join(out, 'disc-report.json')
        report = json.load(open(manifest_path, encoding='utf-8'))
        assert report['complete'] and report['blocks'] == len(want)
        times = {f: os.stat(os.path.join(out, f)).st_mtime_ns for f in report['outputs']}
        args = [sys.executable, '-I', os.path.join(HERE, 'vu1_from_disc.py'), '--gen', a.gen, disc, out]
        cached = subprocess.run(args, capture_output=True, text=True, check=True)
        assert 'cache hit' in cached.stdout
        assert times == {f: os.stat(os.path.join(out, f)).st_mtime_ns for f in times}
        victim = next(iter(report['outputs']))
        open(os.path.join(out, victim), 'wb').write(b'broken')
        repaired = subprocess.run(args, capture_output=True, text=True, check=True)
        assert 'cache hit' not in repaired.stdout
        assert os.path.getsize(os.path.join(out, victim)) == vu1_from_disc.CODE_SIZE
        # A forced identical scan must not touch the source files consumed by Ninja.
        stamp = os.stat(os.path.join(out, victim)).st_mtime_ns
        subprocess.run(args + ['--force'], capture_output=True, text=True, check=True)
        assert os.stat(os.path.join(out, victim)).st_mtime_ns == stamp
        limited = subprocess.run(args + ['--max-images', '1'], capture_output=True, text=True, check=True)
        assert not json.load(open(manifest_path, encoding='utf-8'))['complete']
        assert 'cache hit' not in subprocess.run(args, capture_output=True, text=True, check=True).stdout
        got = set()
        images = [f for f in os.listdir(out) if f.endswith('.bin')]
        for f in images:
            got |= vu1_from_disc.block_keys(gen, open(os.path.join(out, f), 'rb').read())
    missing, extra = want - got, got - want
    print(f'blocks in the micro memory: {len(want)}, extracted: {len(got)} from {len(images)} images, '
          f'missing {len(missing)}, extra {len(extra)}')
    print('PASS: IRQ uploads, cache reuse, output corruption recovery, stable timestamps, limited scan invalidation')
    return 0 if not missing and not extra else 1


if __name__ == '__main__':
    sys.exit(main())
