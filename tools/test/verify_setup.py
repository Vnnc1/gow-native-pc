"""Verify a Windows LZMS setup payload against its staging directory without installing or changing Windows settings.

python -I tools/test/verify_setup.py <setup.exe> <staging directory>
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib
from pathlib import Path, PureWindowsPath
import struct
import sys


def verify(setup, staging):
    data = Path(setup).read_bytes()
    footer = struct.Struct('<8sQQII')
    magic, start, raw_total, blocks, version = footer.unpack_from(data, len(data) - footer.size)
    assert magic == b'GOWSETUP' and version == 1 and blocks > 0, 'bad footer'
    end = len(data) - footer.size
    assert 0 < start < end and 0 < raw_total < 2**32, 'invalid payload bounds'
    cabinet = c.WinDLL('cabinet.dll', use_last_error=True)
    cabinet.CreateDecompressor.argtypes = [w.DWORD, c.c_void_p, c.POINTER(c.c_void_p)]
    cabinet.CreateDecompressor.restype = w.BOOL
    cabinet.Decompress.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    cabinet.Decompress.restype = w.BOOL
    cabinet.CloseDecompressor.argtypes = [c.c_void_p]
    handle = c.c_void_p()
    assert cabinet.CreateDecompressor(5, None, c.byref(handle)), 'CreateDecompressor'
    raw = bytearray()
    at = start
    try:
        for _ in range(blocks):
            assert at + 8 <= end
            size, packed = struct.unpack_from('<II', data, at)
            at += 8
            assert 0 < size <= 16 * 1024 * 1024 and at + packed <= end
            output = c.create_string_buffer(size)
            count = c.c_size_t()
            assert cabinet.Decompress(handle, data[at:at + packed], packed, output, size, c.byref(count)), c.get_last_error()
            assert count.value == size
            raw.extend(output.raw)
            at += packed
    finally:
        cabinet.CloseDecompressor(handle)
    assert at == end and len(raw) == raw_total
    count, = struct.unpack_from('<I', raw)
    entries = []
    at = 4
    seen = set()
    for _ in range(count):
        length, = struct.unpack_from('<H', raw, at)
        at += 2
        assert at + length * 2 + 8 <= len(raw)
        name = raw[at:at + length * 2].decode('utf-16-le')
        at += length * 2
        size, = struct.unpack_from('<Q', raw, at)
        at += 8
        path = PureWindowsPath(name)
        assert name and not path.drive and not path.root and '..' not in path.parts
        assert name.casefold() not in seen, 'duplicate path'
        seen.add(name.casefold())
        entries.append((path, size))
    root = Path(staging).resolve()
    for path, size in entries:
        assert at + size <= len(raw)
        original = root.joinpath(*path.parts).resolve()
        assert original.is_relative_to(root)
        assert original.read_bytes() == raw[at:at + size], str(path)
        at += size
    assert at == len(raw)
    assert count == sum(p.is_file() for p in root.rglob('*'))
    print(f'PASS: {count} files, {blocks} LZMS blocks, {raw_total} unpacked bytes; all match the staging directory')
    print('SHA256:', hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    verify(*sys.argv[1:])
