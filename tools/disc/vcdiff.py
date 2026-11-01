"""VCDIFF (RFC 3284, xdelta3 extensions: app header, adler32) reader / decoder.
vcdiff.py info <patch>                       windows, source span, target size
vcdiff.py apply <patch> <source> <out>       decode (no secondary compression, default code table)"""
import struct, sys, zlib

def varint(f):
    v = 0
    while True:
        b = f.read(1)
        if not b: raise EOFError
        b = b[0]; v = (v << 7) | (b & 0x7F)
        if not b & 0x80: return v

def varint_buf(buf, pos):
    v = 0
    while True:
        b = buf[pos]; pos += 1; v = (v << 7) | (b & 0x7F)
        if not b & 0x80: return v, pos

def header(f):
    magic = f.read(4)
    if magic[:3] != b'\xd6\xc3\xc4': raise ValueError('not VCDIFF')
    ind = f.read(1)[0]
    if ind & 1: raise ValueError('secondary compression not supported')
    if ind & 2: raise ValueError('custom code table not supported')
    app = b''
    if ind & 4: app = f.read(varint(f))
    return app

def windows(f):
    while True:
        b = f.read(1)
        if not b: return
        wi = b[0]; src_len = src_pos = None
        if wi & 3: src_len = varint(f); src_pos = varint(f)
        enc_len = varint(f); start = f.tell()
        tlen = varint(f); dind = f.read(1)[0]
        dlen, ilen, alen = varint(f), varint(f), varint(f)
        cksum = struct.unpack('>I', f.read(4))[0] if wi & 4 else None
        yield dict(wi=wi, src_len=src_len, src_pos=src_pos, tlen=tlen, dind=dind, dlen=dlen, ilen=ilen, alen=alen,
                   cksum=cksum, body=f.tell(), end=start + enc_len)
        f.seek(start + enc_len)

# default code table (RFC 3284 section 5.6)
def code_table():
    t = [(0, 0, 0, 0, 0, 0)] * 256  # (type1, size1, mode1, type2, size2, mode2); types: 0 NOOP 1 ADD 2 RUN 3 COPY
    t = list(t); i = 0
    t[i] = (2, 0, 0, 0, 0, 0); i += 1
    t[i] = (1, 0, 0, 0, 0, 0); i += 1
    for s in range(1, 18): t[i] = (1, s, 0, 0, 0, 0); i += 1
    for m in range(9):
        t[i] = (3, 0, m, 0, 0, 0); i += 1
        for s in range(4, 19): t[i] = (3, s, m, 0, 0, 0); i += 1
    for m in range(6):
        for a in range(1, 5):
            for c in range(4, 7): t[i] = (1, a, 0, 3, c, m); i += 1
    for m in range(6, 9):
        for a in range(1, 5): t[i] = (1, a, 0, 3, 4, m); i += 1
    for m in range(9): t[i] = (3, 4, m, 1, 1, 0); i += 1
    assert i == 256
    return t

def apply(patch, source, out):
    table = code_table(); S_NEAR, S_SAME = 4, 3
    with open(patch, 'rb') as f, open(source, 'rb') as src, open(out, 'wb') as o:
        header(f)
        written = 0; nwin = 0
        for w in windows(f):
            nwin += 1
            f.seek(w['body']); data = f.read(w['dlen']); inst = f.read(w['ilen']); addr = f.read(w['alen'])
            if w['wi'] & 1:
                src.seek(w['src_pos']); sseg = src.read(w['src_len'])
            elif w['wi'] & 2:
                with open(out, 'rb') as back:
                    back.seek(w['src_pos']); sseg = back.read(w['src_len'])
            else:
                sseg = b''
            slen = len(sseg)
            tgt = bytearray()
            near = [0] * S_NEAR; nn = 0; same = [0] * (S_SAME * 256)
            dp = ip = ap = 0
            def addr_decode(here, mode):
                nonlocal ap, nn
                if mode == 0: a, ap2 = varint_buf(addr, ap)
                elif mode == 1:
                    v, ap2 = varint_buf(addr, ap); a = here - v
                elif mode < 2 + S_NEAR:
                    v, ap2 = varint_buf(addr, ap); a = near[mode - 2] + v
                else:
                    m = mode - (2 + S_NEAR); a = same[m * 256 + addr[ap]]; ap2 = ap + 1
                ap = ap2
                near[nn] = a; nn = (nn + 1) % S_NEAR; same[a % (S_SAME * 256)] = a
                return a
            while ip < len(inst):
                code = inst[ip]; ip += 1
                for (typ, size, mode) in ((table[code][0], table[code][1], table[code][2]), (table[code][3], table[code][4], table[code][5])):
                    if typ == 0: continue
                    if size == 0: size, ip = varint_buf(inst, ip)
                    if typ == 1:
                        tgt += data[dp:dp + size]; dp += size
                    elif typ == 2:
                        tgt += data[dp:dp + 1] * size; dp += 1
                    else:
                        here = slen + len(tgt)
                        a = addr_decode(here, mode)
                        if a + size <= slen:
                            tgt += sseg[a:a + size]
                        else:
                            for k in range(size):  # copies may overlap the bytes being produced
                                p = a + k
                                tgt.append(sseg[p] if p < slen else tgt[p - slen])
            if len(tgt) != w['tlen']: raise ValueError(f'window {nwin}: {len(tgt)} != {w["tlen"]}')
            if w['cksum'] is not None and (zlib.adler32(bytes(tgt)) & 0xFFFFFFFF) != w['cksum']:
                raise ValueError(f'window {nwin}: checksum mismatch' + (': the patch was made for a different ISO' if nwin == 1 else ''))
            o.write(tgt); written += len(tgt)
            if nwin % 200 == 0: print(f'{nwin} windows, {written / 2**20:.0f} MB', flush=True)
        print(f'done: {nwin} windows, {written} bytes')

if __name__ == '__main__':
    if sys.argv[1] == 'info':
        with open(sys.argv[2], 'rb') as f:
            app = header(f); n = 0; total = 0; smax = 0; adds = 0; src_windows = 0; tgt_windows = 0
            for w in windows(f):
                n += 1; total += w['tlen']; adds += w['dlen']
                if w['wi'] & 1: src_windows += 1; smax = max(smax, w['src_pos'] + w['src_len'])
                if w['wi'] & 2: tgt_windows += 1
            print('app header:', app[:200])
            print(f'windows {n}, target size {total} ({total / 2**30:.2f} GB), add data {adds / 2**30:.2f} GB')
            print(f'source windows {src_windows}, target-copy windows {tgt_windows}, source read up to {smax} ({smax / 2**30:.2f} GB)')
    else:
        apply(sys.argv[2], sys.argv[3], sys.argv[4])
