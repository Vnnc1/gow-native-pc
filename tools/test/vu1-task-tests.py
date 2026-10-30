"""Validate standalone task recording/replay and corrupt-input rejection without game data."""
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

exe = Path(sys.argv[1]).resolve()
env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("GOW_", "PS2X_", "TOBIICHI_"))}


def run(*args, code=0):
    p = subprocess.run([str(exe), *map(str, args)], env=env, capture_output=True, timeout=45)
    text = (p.stdout + p.stderr).decode(errors="replace")
    assert p.returncode == code, (p.returncode, text)
    return text


with tempfile.TemporaryDirectory(prefix="gow-vu1-tasks-") as tmp:
    root = Path(tmp)
    corpus = root / "tasks.bin"
    plain = run("--fixture", "none")
    recorded = run("--fixture", corpus)
    assert re.search(r"fixture_digest=\w+", plain)[0] == re.search(r"fixture_digest=\w+", recorded)[0]
    original = corpus.read_bytes()
    assert len(original) < 110000 and "recorded=3" in recorded
    for mode in ("hybrid", "jit", "helper", "sse", "exact"):
        result = run("--replay", corpus, mode, "3")
        assert "records=3 mismatches=0" in result, result
        if mode != "exact":
            assert any(int(n) > 0 for n in re.findall(r"native_blocks=(\d+)", result)), result
    duplicate = run("--fixture", corpus)
    assert "write_error=1" in duplicate and corpus.read_bytes() == original
    for name, content in (("empty", b""), ("short", original[:-1]), ("magic", b"BAD!" + original[4:]),
                          ("payload", original[:-1] + bytes([original[-1] ^ 1])), ("extra", original + b"x")):
        bad = root / (name + ".bin")
        bad.write_bytes(content)
        assert "invalid_corpus=1" in run("--replay", bad, code=2)
    run("--replay", corpus, "jit", "0", code=2)
    run("--replay", corpus, "jit", "101", code=2)
    changed = bytearray(original)
    changed[24] ^= 1  # Change only the first record's native baseline, retaining a valid checksum.
    record_size = struct.unpack_from("<I", changed, 8)[0]
    changed[16:24] = bytes(8)
    h = 1469598103934665603
    for byte in changed[:record_size]: h = ((h ^ byte) * 1099511628211) & ((1 << 64) - 1)
    struct.pack_into("<Q", changed, 16, h)
    mismatch = root / "mismatch.bin"
    mismatch.write_bytes(changed)
    assert "mismatches=1" in run("--replay", mismatch, "jit", "1", code=1)
    assert "mismatches=0" in run("--replay", mismatch, "exact", "1")
print("PASS: task capture preserves execution; bounded corpus; hybrid/JIT/helper/SSE/exact replay; invalid input rejected")
