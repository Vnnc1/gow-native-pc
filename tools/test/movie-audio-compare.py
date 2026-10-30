"""Compare a raw SPU2 mix with a PCM16 stereo PS2 movie (requires numpy).

Use a bounded search interval containing the movie in the raw recording. This is a diagnostic,
not a pass/fail test: music mixed under a movie can legitimately change correlation and gain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def source_audio(path):
    data = Path(path).read_bytes()
    payload = bytearray()
    pos = 0
    while True:
        at = data.find(b'\0\0\1\xbd', pos)
        if at < 0:
            break
        size = int.from_bytes(data[at + 4:at + 6], 'big')
        end = at + 6 + size
        start = at + 9 + data[at + 8]
        if end > len(data) or start + 4 > end:
            raise ValueError('Truncated private-stream packet')
        if data[start:start + 4] != b'\xff\xa0\0\0':
            raise ValueError('Unsupported audio substream')
        payload.extend(data[start + 4:end])
        pos = end
    if payload[:4] != b'SShd' or payload[32:36] != b'SSbd':
        raise ValueError('Missing PCM stream header')
    if struct.unpack_from('<5I', payload, 4) != (24, 1, 48000, 2, 512):
        raise ValueError('Only 48 kHz stereo PCM16 with 512-byte channel blocks is supported')
    size = struct.unpack_from('<I', payload, 36)[0]
    if size > len(payload) - 40 or size % 1024:
        raise ValueError('Incomplete channel block pairs')
    blocks = np.frombuffer(payload[40:40 + size], dtype='<i2').reshape(-1, 2, 256)
    return blocks.transpose(0, 2, 1).reshape(-1, 2).astype(float), hashlib.sha256(payload).hexdigest()


def compare(movie, raw, start, end, template_second):
    src, digest = source_audio(movie)
    recording = np.fromfile(raw, dtype='<i2').reshape(-1, 2).astype(float)
    base = int(start * 48000)
    data = recording[base:int(end * 48000), 0]
    template_start = int(template_second * 48000)
    template = src[template_start:template_start + 48000, 0]
    if len(template) != 48000 or len(data) <= len(template):
        raise ValueError('Search/template interval too short')
    n = 1 << (len(data) + len(template) - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(data, n) * np.conj(np.fft.rfft(template, n)), n)
    offset = base + int(np.argmax(corr[:len(data) - len(template) + 1])) - template_start
    rows = []
    for second in range(1, len(src) // 48000):
        at = second * 48000
        if offset + at < 0 or offset + at + 48000 > len(recording):
            continue
        a, b = src[at:at + 48000], recording[offset + at:offset + at + 48000]
        energy = float(np.sum(a * a))
        if energy == 0:
            continue
        gain = float(np.sum(a * b) / energy)
        distinct = np.abs(a[:, 0] - a[:, 1]) > 100
        rows.append(dict(second=second, gain=gain,
                         residual_rms=float(np.sqrt(np.mean((b - gain * a) ** 2))),
                         clipped=int((np.abs(b) >= 32767).sum()),
                         distinct_channels=int(distinct.sum()),
                         left_matches_left=int(((np.abs(b[:, 0] - a[:, 0]) < 10) & distinct).sum()),
                         left_matches_right=int(((np.abs(b[:, 0] - a[:, 1]) < 10) & distinct).sum())))
    return dict(source_payload_sha256=digest, offset_samples=offset, rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('movie')
    parser.add_argument('raw')
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--end', type=float, required=True)
    parser.add_argument('--template-second', type=float, default=3)
    args = parser.parse_args()
    print(json.dumps(compare(args.movie, args.raw, args.start, args.end, args.template_second), indent=2))
