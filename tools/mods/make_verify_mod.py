#!/usr/bin/env python3
"""Build the verification fixture mod used to prove the mod manager end to end.

This is NOT a content mod: it exists only to exercise both resource paths of the runtime on this checkout.

  * payload/textures/*.png  solid magenta RGBA at the size encoded in each PCSX2 name (TW/TH; 512x512 and
    512x256 in this fixture), one per PCSX2 texture name the baseline run drew (the names come from
    GOW_TEX_PCSX2_NAMES, patch 52's diagnostic).  Alpha is 128, the GS-unit "opaque" value the texture-pack
    decoder expects.  A smaller image than the name's TW/TH is rejected by the manager: replacing a 512x512
    texture with 64x64 made the runner exit during the intro cutscene (measured 2026-11-05).
  * payload/vfs/LIBSD.IRX   a byte-identical copy of the disc's iop_mod/LIBSD.IRX, mapped over
    iop_mod/libsd.irx so patch 71's override table is provably hit.  The copy is made locally and must
    never be redistributed.

Usage:
  python tools/mods/make_verify_mod.py --names data/_tmp/.../texnames.txt \
      --disc C:/gow-jpn-data/gow1/discs/asia-97399 --out data/_tmp/mod-verify/fixture
"""

from __future__ import annotations

import argparse
import os
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def solid_png(width: int, height: int, rgba: tuple[int, int, int, int]) -> bytes:
    rows = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA, no interlace
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", required=True, help="GOW_TEX_PCSX2_NAMES output of a baseline run")
    parser.add_argument("--disc", required=True, help="extracted disc root (source of LIBSD.IRX)")
    parser.add_argument("--out", required=True, help="package folder to create")
    parser.add_argument("--color", default="255,0,255,128")
    args = parser.parse_args()

    names: list[tuple[str, int, int]] = []
    seen = set()
    for line in Path(args.names).read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        token = fields[0]
        width = height = 0
        if len(fields) > 1 and "x" in fields[1]:
            size = fields[1].split("x")
            if len(size) == 2 and size[0].isdigit() and size[1].isdigit():
                width, height = int(size[0]), int(size[1])
        if width <= 0 or height <= 0:
            raise SystemExit(f"no size for {token}: this file must be a GOW_TEX_PCSX2_NAMES listing")
        if token not in seen:
            seen.add(token)
            names.append((token, width, height))
    if not names:
        raise SystemExit("no texture names: run a baseline session with GOW_TEX_PCSX2_NAMES first")

    red, green, blue, alpha = (int(part) for part in args.color.split(","))
    out = Path(args.out)
    textures = out / "payload" / "textures"
    textures.mkdir(parents=True, exist_ok=True)
    # Same dimensions as the texture the GS draws, as PCSX2 replacement packs do. A smaller pack image is bound while
    # the renderer still normalises with the GS size; measured on 2026-11-05, 64x64 images for 512x512 textures made the
    # intro cutscene exit the runner, so the fixture keeps the sizes the names encode.
    by_size: dict[tuple[int, int], bytes] = {}
    for name, width, height in names:
        if (width, height) not in by_size:
            by_size[(width, height)] = solid_png(width, height, (red, green, blue, alpha))
        (textures / f"{name}.png").write_bytes(by_size[(width, height)])

    disc = Path(args.disc)
    module = None
    for candidate in (disc / "iop_mod").iterdir():
        if candidate.name.upper() == "LIBSD.IRX":
            module = candidate
            break
    if module is None:
        raise SystemExit(f"LIBSD.IRX not found under {disc / 'iop_mod'}")
    vfs = out / "payload" / "vfs"
    vfs.mkdir(parents=True, exist_ok=True)
    (vfs / "LIBSD.IRX").write_bytes(module.read_bytes())

    manifest = f'''spec = 1
id = "verify.gow.recolor-probe"
name = "Verification fixture: magenta textures + identical IRX"
version = "1.0.0"
type = "content"
priority = 10
author = "local verification"
license = "none (not for distribution)"
description = """\
Verification fixture, not a playable content mod. Every texture the baseline session drew is replaced with a
solid magenta RGBA image of the same size (alpha 128 = opaque in GS units), and iop_mod/libsd.irx is mapped to a
byte-identical local copy of the disc's LIBSD.IRX so the patch 71 override hook is exercised. The IRX copy
is game data and must not be redistributed."""
min_manager = 1

[target]
game_id = "gow1"
regions = ["japan"]
edition = "asia-97399"

[textures]
dir = "payload/textures"

[vfs]
'iop_mod\\libsd.irx' = "payload/vfs/LIBSD.IRX"
'''
    (out / "mod.toml").write_text(manifest, encoding="utf-8")
    print(f"fixture: {len(names)} textures + 1 vfs override -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
