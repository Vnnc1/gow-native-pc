#!/usr/bin/env python3
"""God of War native port - mod manager.

This is the executable side of `docs/mod-manager-design.zh-CN.md`: mod discovery and metadata,
validation, enable order/priority, resource planning (environment variables, PCSX2 texture packs and
guest file overrides), conflict/missing detection, activation with a write-ahead journal and rollback,
and launching the runner with the plan applied.  It is intentionally dependency free (Python 3.11+,
standard library only) because this checkout ships the launcher binaries without their QML/C++ source;
section 7.2 of the design makes this CLI the contract a front-end consumes.

Runtime cooperation (patch 71, engine/patches/69-mod-vfs-hooks.patch):
  * GOW_TEXTURE_PACK is read by gs_hw_backend.cpp (patch 52); the manager only stages the PNGs.
  * GOW_MOD_VFS_TABLE is read by mod_vfs_table.cpp (patch 71); the manager writes the TSV.
  * Every other setting a mod contributes is an environment variable the runtime already reads.

Usage:  python -I tools/mods/gow_mods_cli.py <command> [options]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = 1
MAX_MODS = 256
MAX_FILES = 4096
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ENV_VALUE = 256  # some real runtime keys carry a path or a comma-separated cheat list

MOD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:-[0-9A-Za-z.-]+)?$")
# Must match the WHOLE guest path. The VFS hook is a line/tab-separated TSV, so a prefix-only match lets a
# manifest inject extra rows (or control characters) into hooks/vfs-overrides.tsv via its [vfs] keys.
GUEST_PATH_RE = re.compile(r"^(?:(?:cdrom0|cdrom|host|mc0|mc1|rom0):|(?:[A-Za-z0-9_.-]+[\\/])+)[A-Za-z0-9_.\-;\\/]*$",
                           re.IGNORECASE)

# Keys the runtime actually reads (grep of getenv in engine/runtime; patch numbers in comments).  A mod may not
# invent settings: an unknown key is a validation error instead of a silent no-op.
ENV_ALLOWED: dict[str, str] = {
    # display / image (patches 39, 52, 65)
    "GOW_SCALER": "visual",
    "GOW_SHARPEN": "visual",
    "TOBIICHI_FXAA": "visual",
    "GOW_PROGRESIVO": "visual",
    "GOW_TEXTURE_PACK_MB": "visual",
    "GOW_TEXTURE_PACK_STATS": "diagnostic",
    "GOW_GS_TEXREUSE": "diagnostic",
    "GOW_WINDOW": "behaviour",
    "PS2X_GS_HW_SCALE": "visual",
    # Presentation / picture toggles (Graphics tab, patch 47 and patch 80). All have a getenv reader.
    "PS2X_GS_DIRECT_PRESENT": "visual",
    "GOW_GL_MAX_MINOR": "engine",
    "GOW_FX_NO_SHADOWS": "visual",
    "GOW_FX_NO_ADDITIVE3D": "visual",
    "GOW_FX_NO_TEXTURE_FILTER": "visual",
    # Renderer diagnostics: they write counters or dumps but never change the picture.
    "GOW_GS_HW_STATS": "diagnostic",
    "GOW_GS_GPU_PROFILE": "diagnostic",
    "GOW_GS_HW_TEXDUMP": "diagnostic",
    # Image / presentation effects with a real getenv reader (gow_ajustes_vivo.h, gow_integracion.cpp,
    # gow_video.cpp, gow_trucos.cpp). These are read once at start-up, which is exactly when mods inject them.
    "GOW_ANISO": "visual",
    "TOBIICHI_ASPECTO": "visual",
    "TOBIICHI_PANORAMICO": "visual",
    "TOBIICHI_VSYNC": "visual",
    "TOBIICHI_FPS_GOSTER": "visual",
    # timing / logic
    "GOW_CANCELAR": "behaviour",
    "GOW_FIJAR": "behaviour",
    "GOW_ESPERA_EE": "behaviour",
    "GOW_QTE_HOLD": "behaviour",
    "GOW_QTE_STICK": "behaviour",
    "GOW_EE_FPU_NEAREST": "behaviour",
    "GOW_AUDIO": "behaviour",
    "GOW_AUDIO_DEVICE": "behaviour",
    "GOW_PAD_BT_RUMBLE": "behaviour",
    # Built-in gameplay/logic switches already compiled into the runner (gow_overrides.cpp, gow_trucos.cpp).
    # These are the ONLY way a mod changes game behaviour without rebuilding the binary: they are switches,
    # not executable code. A mod cannot load new host functions or patch guest code at runtime.
    "TOBIICHI_TRUCOS": "behaviour",
    "GOW_GOD_MODE": "behaviour",
    "GOW_FAST_BOOT": "behaviour",
    "GOW_SKIP_FMV": "behaviour",
    "GOW_MOVIE_OVERRIDE": "behaviour",
    "GOW_BONUS_MOVIE": "behaviour",
    "GOW_WARP": "engine",
    # the patch-stack switches: a mod that changes them is a code-style mod, allowed but flagged
    "GOW_VU1_FAST": "engine",
    "GOW_VU1N_X64": "engine",
    "PS2X_GS_RUN": "engine",
    "PS2X_GS_PIPELINE": "engine",
    "GOW_GS_FINISH_ASINCRONO": "engine",
    "PS2X_GS_HW": "engine",
    "PS2X_GS_WORKER": "engine",
    # GS pipeline switches (Graphics tab > Advanced renderer options). "engine" so a package that turns
    # one off is flagged: these restore older code paths and are for diagnosis, not for looks.
    "GOW_GS_STATE_CACHE": "engine",
    "GOW_GS_HW_RING": "engine",
    "GOW_GS_DEPTH_PER_ZBP": "engine",
    "PS2X_GS_RUN_STATE_FAST": "engine",
    "PS2X_GS_COMPACT_QUEUE": "engine",
    "PS2X_GS_QUEUE_CHUNKS": "engine",
    "GOW_GS_ASYNC_SUBMIT": "engine",
    "PS2X_GS_RENDERER": "engine",
}

# Manager-owned: staging paths, the test harness and diagnostics that write files.  A mod must not touch them, or
# activation would stop being reversible and a package could redirect the game's own evidence.
ENV_RESERVED = {
    "GOW_MOD_VFS_TABLE",
    "GOW_MOD_VFS_STATS",
    "GOW_MOD_VFS_TRACE",
    "GOW_MOD_VFS_LOG",
    "GOW_MOD_PATCH_TABLE",
    "GOW_MOD_PATCH_LOG",
    "GOW_TEXTURE_PACK",
    # The launcher writes this sampled-name list into its own report folder; a mod must not redirect it.
    "GOW_TEX_PCSX2_NAMES",
    "GOW_MC0",
    "GOW_SAVES_DIR",
    "GOW_PAD_TEST",
    "GOW_PAD_GUION",
    "GOW_PAD_CAPTURAS",
    "GOW_HOST_SHOT",
    "GOW_WINDOW_HIDDEN",
    "GOW_PERF_DIAG",
    "GOW_PERF_FRAME_PC",
    "GOW_DEBUG",
}

FORBIDDEN_PAYLOAD_SUFFIXES = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".com", ".scr", ".msi"}

# The drop folder installs into the launcher profile (the one ModsModel uses). A marker file inside a package
# turns a failed import into a visible "Blocked" row instead of silently ignoring the player's file.
DROP_PROFILE = "launcher"
DROP_ERROR_FILE = "gow-install-error.txt"
DROP_WARN_FILE = "gow-install-warning.txt"

# Stand-alone disc files the game OPENS BY GUEST PATH (so GOW_MOD_VFS_TABLE can redirect them). Audio/FMV
# packed inside PART1.PAK/PART2.PAK is read by LSN/sector and is NOT reachable this way; see the warning
# written into generated packages and docs/handoff-launcher-mod-manager-2026-11-05.zh-CN.md section 3.6.
DROP_VFS_SUFFIXES = {".irx", ".vag", ".pss", ".psw", ".str"}
# Files that advertise a capability this statically recompiled port cannot load at runtime. Reject them
# instead of producing a mod that silently does nothing (handoff section 9.4: no fake shells).
DROP_UNSUPPORTED_HINTS = {
    "function.toml": "Function overrides need C++ compiled into ps2EntryRunner.exe; a mod cannot load code at runtime",
    "script.toml": "Guest scripts are parsed by the game itself; there is no runtime path hook to replace them",
    "pak.toml": "PAK contents are read by LSN/sector, not by path; the runtime has no hook to remap them",
    "code.toml": "Game logic changes require rebuilding the runner; this port cannot runtime-load a code mod",
    "shader.glsl": "Post-processing shaders are compiled into the runner (kScalerFragment); a mod cannot load GLSL at runtime",
}

UNSUPPORTED_SECTIONS = {
    "pak": "PAK remapping needs the disc's TOC (the IOP reads by LBA, not by path); the runtime has no hook for it",
    "function": "function overrides need host symbols compiled into the runner; not part of this delivery",
    "script": "guest scripts are data the game parses itself; no runtime hook exists to replace them by path",
}

# Visual presets a mod can request with [effects] presets = [...] (or effects.toml for a zero-config drop).
# Every key below has a real getenv reader in the runtime; no invented settings, no shader loading.
EFFECT_PRESETS: dict[str, dict[str, str]] = {
    "sharp": {"GOW_SCALER": "sharp", "GOW_SHARPEN": "0.4"},
    "soft": {"GOW_SCALER": "bilinear", "GOW_SHARPEN": "0.0"},
    "fxaa": {"TOBIICHI_FXAA": "1"},
    "no-fxaa": {"TOBIICHI_FXAA": "0"},
    "aniso16": {"GOW_ANISO": "16"},
    "progressive": {"GOW_PROGRESIVO": "1"},
    "interlaced": {"GOW_PROGRESIVO": "0"},
    "widescreen": {"TOBIICHI_PANORAMICO": "1.7777"},
    "stretch": {"TOBIICHI_ASPECTO": "estirar"},
    "vsync": {"TOBIICHI_VSYNC": "1"},
    "fps": {"TOBIICHI_FPS_GOSTER": "1"},
    "retro": {"PS2X_GS_HW_SCALE": "0.5", "GOW_SCALER": "bilinear", "GOW_SHARPEN": "0.0"},
    # Picture/effect presets that use the same variables as the Graphics tab (patches 80, 47).
    "nearest": {"GOW_FX_NO_TEXTURE_FILTER": "1"},
    "no-shadows": {"GOW_FX_NO_SHADOWS": "1"},
    "no-glow": {"GOW_FX_NO_ADDITIVE3D": "1"},
    "crisp": {"GOW_SCALER": "sharp", "GOW_SHARPEN": "0.5", "GOW_ANISO": "16"},
    "gl43": {"GOW_GL_MAX_MINOR": "3"},
    "texture-stats": {"GOW_TEXTURE_PACK_STATS": "1"},
}
EFFECT_KEYS = frozenset(key for preset in EFFECT_PRESETS.values() for key in preset)

# Declarative guest-RAM data patches. These are DATA interpreted by host C++ (runtime patch 84), never code:
# no DLL, no machine code, no script. Bound to the game's .text SHA-1 so a USA address cannot hit a Japan build.
PATCH_MIN_ADDRESS = 0x00100000
PATCH_MAX_ADDRESS = 0x02000000
MAX_DATA_PATCHES = 512


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def brief(value: Any, limit: int = 300) -> str:
    """Optional manifest text shown in the UI; never trust its type or length."""
    return value[:limit] if isinstance(value, str) else ""


def digest(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Per-process temp name: two manager instances writing the same state file must not share a scratch file.
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows can hold the destination briefly (anti-virus/indexer); retry instead of failing the transaction.
        for attempt in range(6):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.2)
    finally:
        temp.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def canonical_guest_path(text: str) -> str:
    """Mirror of gow::mods::canonicalGuestPath (mod_vfs_table.cpp), so both sides agree on the key."""
    out: list[str] = []
    previous_separator = True
    for char in text:
        char = "/" if char == "\\" else char
        char = char.lower() if "A" <= char <= "Z" else char
        if char == "/":
            if previous_separator:
                continue
            previous_separator = True
            out.append("/")
            continue
        previous_separator = False
        out.append(char)
    result = "".join(out)
    if ";" in result:
        head, _, version = result.rpartition(";")
        if version.isdigit():
            result = head
    return result


def version_key(text: str) -> tuple:
    parts: list[Any] = []
    for piece in re.split(r"[-.]", text):
        parts.append((0, int(piece)) if piece.isdigit() else (1, piece))
    return tuple(parts)


class ManagerError(RuntimeError):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    mod: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message, "mod": self.mod}


@dataclass
class Package:
    id: str
    version: str
    path: Path
    manifest: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)
    textures: dict[str, Path] = field(default_factory=dict)
    vfs: dict[str, Path] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    priority: int = 0
    capabilities: list[str] = field(default_factory=list)
    patches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.id, self.version)

    @property
    def label(self) -> str:
        # An unreadable manifest has no version; do not show a bogus trailing "@" in the UI.
        return f"{self.id}@{self.version}" if self.version else self.id

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def target(self) -> dict[str, Any]:
        target = self.manifest.get("target", {})
        return target if isinstance(target, dict) else {}


class Context:
    def __init__(self, repo: Path, mods: Path):
        self.repo = repo
        self.mods = mods
        self.packages_dir = mods / "packages"
        self.profiles_dir = mods / "profiles"
        self.plans_dir = mods / "plans"
        self.staging_dir = mods / "staging"
        self.hooks_dir = mods / "hooks"
        self.journal_dir = mods / "journal"
        self.reports_dir = mods / "reports"
        self.runs_dir = mods / "runs"
        # Minecraft-style install folder: a player drops a .zip or an unpacked folder here and the manager
        # installs/enables it automatically. packages/ stays the manager-owned registry.
        self.drop_dir = mods / "mods"
        self.ingested_path = mods / "ingested.json"
        self.state_path = mods / "state.json"
        self.fingerprint_path = mods / "fingerprint.json"
        for folder in (self.packages_dir, self.profiles_dir, self.plans_dir, self.staging_dir,
                       self.hooks_dir, self.journal_dir, self.reports_dir, self.runs_dir, self.drop_dir):
            folder.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------------------------------------------------------------- fingerprint

def gather_fingerprint(ctx: Context) -> dict[str, Any]:
    profile_path = ctx.repo / "games" / "gow1" / "game.toml"
    if not profile_path.is_file():
        raise ManagerError(f"game profile missing: {profile_path}", 2)
    profile = load_toml(profile_path)
    # regional-builds.json is produced by an OPTIONAL isolated regional build (data/ is git-ignored). A normal
    # installation has no such file: fall back to the game profile instead of making every mod command fail.
    builds_path = ctx.repo / "data" / "gow1" / "regional-builds.json"
    builds: list[dict[str, Any]] = []
    if builds_path.is_file():
        try:
            loaded = json.loads(builds_path.read_text(encoding="utf-8")).get("builds", [])
            if isinstance(loaded, list):
                builds = [item for item in loaded if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            builds = []
    build = builds[0] if builds else {}
    executable = profile.get("executable", {}) if isinstance(profile.get("executable"), dict) else {}
    editions = profile.get("editions", []) if isinstance(profile.get("editions"), list) else []
    default_region = str(editions[0].get("id", "unknown")) if editions and isinstance(editions[0], dict) else "unknown"

    runtime = ctx.repo / "engine" / "runtime"
    try:
        commit = subprocess.run(["git", "-C", str(runtime), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "unknown"

    chain = hashlib.sha256()
    patches = sorted((ctx.repo / "engine" / "patches").glob("*.patch"), key=lambda item: item.name)
    for patch in patches:
        chain.update(patch.name.encode("utf-8"))
        chain.update(b"\0")
        chain.update(patch.read_bytes())
        chain.update(b"\0")

    fields = {
        "gameId": profile.get("id", "gow1"),
        # An isolated build's "region" is the disc edition and its "code" is the code region; the base profile
        # has no such pair, so use the serial and the first edition id. Both values are accepted by target.regions.
        "edition": str(build.get("region") or executable.get("serial") or "unknown"),
        "region": str(build.get("code") or default_region),
        "elfCrc": str(build.get("elf_crc") or executable.get("crc") or "").upper(),
        "textSha1": str(build.get("text_sha1") or executable.get("text_sha1") or ""),
        "runtimeCommit": commit,
        "patchChainHash": chain.hexdigest(),
    }
    record = {"schema": SCHEMA, **fields, "fingerprintId": digest(stable_json(fields)), "generatedAt": iso(now())}
    record["runnerSha256"] = build.get("runner_sha256", "")
    return record


def ensure_fingerprint(ctx: Context) -> tuple[dict[str, Any], bool]:
    current = gather_fingerprint(ctx)
    previous = None
    if ctx.fingerprint_path.is_file():
        try:
            previous = json.loads(ctx.fingerprint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None
    changed = previous is None or previous.get("fingerprintId") != current["fingerprintId"]
    atomic_write_json(ctx.fingerprint_path, current)
    return current, changed


# -------------------------------------------------------------------------------------------------------------- discovery

def has_symlink(base: Path, relative: str) -> bool:
    """Check the UNRESOLVED path. Path.resolve() follows symlinks, so is_symlink() on its result is always False."""
    current = base
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def reject_control_characters(text: str) -> bool:
    # The VFS table is a TSV read line by line by mod_vfs_table.cpp; never let a manifest forge a row.
    return any(char in text for char in ("\t", "\n", "\r", "\0"))


def resolve_dir(base: Path, relative: str, issues: list[Issue], label: str) -> Path | None:
    if not isinstance(relative, str) or not relative:
        issues.append(Issue("path.empty", "error", "empty folder path", label))
        return None
    if os.path.isabs(relative) or relative.startswith(("/", "\\")):
        issues.append(Issue("path.absolute", "error", f"absolute folder path: {relative}", label))
        return None
    if has_symlink(base, relative):
        issues.append(Issue("path.symlink", "error", f"folder path contains a symlink: {relative}", label))
        return None
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        issues.append(Issue("path.traversal", "error", f"folder escapes the package: {relative}", label))
        return None
    if not candidate.is_dir():
        issues.append(Issue("file.missing", "error", f"folder missing: {relative}", label))
        return None
    return candidate


def resolve_payload(base: Path, relative: str, issues: list[Issue], label: str) -> Path | None:
    if not isinstance(relative, str) or not relative:
        issues.append(Issue("path.empty", "error", "empty payload path", label))
        return None
    if os.path.isabs(relative) or relative.startswith(("/", "\\")):
        issues.append(Issue("path.absolute", "error", f"absolute payload path: {relative}", label))
        return None
    if has_symlink(base, relative):
        issues.append(Issue("path.symlink", "error", f"payload path contains a symlink: {relative}", label))
        return None
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        issues.append(Issue("path.traversal", "error", f"payload escapes the package: {relative}", label))
        return None
    if not candidate.is_file():
        issues.append(Issue("file.missing", "error", f"payload missing: {relative}", label))
        return None
    return candidate


def validate_png(path: Path) -> tuple[str | None, tuple[int, int] | None]:
    """Minimal structural check: a PNG that raylib cannot decode must be rejected before activation, not at runtime.

    Returns (error, (width, height)); the size is used to check the PCSX2 name's TW/TH fields."""

    def fail(message: str) -> tuple[str, None]:
        return message, None

    try:
        data = path.read_bytes()
    except OSError as error:
        return fail(f"cannot read: {error}")
    if len(data) < 8 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return fail("not a PNG file")
    offset = 8
    header: tuple[int, int, int, int] | None = None
    idat = bytearray()
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if offset + 12 + length > len(data):
            return fail("truncated chunk")
        if kind == b"IHDR":
            if length != 13:
                return fail("bad IHDR")
            width, height, depth, color, compression, filtering, interlace = (
                int.from_bytes(body[0:4], "big"), int.from_bytes(body[4:8], "big"), body[8], body[9], body[10], body[11], body[12])
            if depth != 8 or color not in (2, 6) or compression != 0 or filtering != 0:
                return fail(f"unsupported PNG format (depth={depth} color={color})")
            if interlace != 0:
                return fail("interlaced PNG is not supported")
            if not 0 < width <= 8192 or not 0 < height <= 8192:
                return fail(f"bad PNG size {width}x{height}")
            header = (width, height, 3 if color == 2 else 4, interlace)
        elif kind == b"IDAT":
            idat.extend(body)
        elif kind == b"IEND":
            break
        offset += 12 + length
    if header is None or not idat:
        return fail("missing IHDR or IDAT")
    width, height, channels, _ = header
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as error:
        return fail(f"IDAT does not decompress: {error}")
    if len(raw) != height * (1 + width * channels):
        return fail(f"IDAT holds {len(raw)} bytes, expected {height * (1 + width * channels)}")
    return None, (width, height)


def texture_expected_size(stem: str) -> tuple[int, int] | None:
    """Size encoded in a PCSX2 pack name: bits = PSM | TW << 6 | TH << 10."""
    try:
        bits = int(stem.rsplit("-", 1)[-1], 16)
    except ValueError:
        return None
    return 1 << ((bits >> 6) & 0xF), 1 << ((bits >> 10) & 0xF)


def parse_data_patch(item: Any, label: str, index: int, issues: list[Issue]) -> dict[str, Any] | None:
    """One [[patches]] entry. Declarative data only: it is interpreted by host C++, never executed."""
    if not isinstance(item, dict):
        issues.append(Issue("patches.type", "error", f"patch #{index} must be a table", label))
        return None

    def number(key: str, default: Any = None) -> int | None:
        raw = item.get(key, default)
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw, 0)
            except ValueError:
                try:
                    return int(raw, 10)
                except ValueError:
                    return None
        return None

    address = number("address")
    width = number("width", 4)
    value = number("value")
    if address is None or value is None or width not in (1, 2, 4):
        issues.append(Issue("patches.fields", "error",
                            f"patch #{index}: address/value are required and width must be 1, 2 or 4", label))
        return None
    if not (PATCH_MIN_ADDRESS <= address < PATCH_MAX_ADDRESS) or address % width:
        issues.append(Issue("patches.address", "error",
                            f"patch #{index}: address 0x{address:X} is outside guest RAM or misaligned", label))
        return None
    limit = 1 << (8 * width)
    mask = number("mask", 0)
    expected = number("expected", 0)
    if not 0 <= value < limit or mask is None or expected is None \
            or not 0 <= mask < limit or not 0 <= expected < limit:
        issues.append(Issue("patches.value", "error",
                            f"patch #{index}: value/mask/expected out of range for width {width}", label))
        return None
    region = item.get("region")
    sha = item.get("text_sha1")
    if (region is not None and not isinstance(region, str)) or (sha is not None and not isinstance(sha, str)):
        issues.append(Issue("patches.binding", "error", f"patch #{index}: region/text_sha1 must be strings", label))
        return None
    return {"address": address, "width": width, "value": value, "mask": mask, "expected": expected,
            "once": 1 if item.get("once") is True else 0, "region": region,
            "text_sha1": sha.lower() if isinstance(sha, str) else None, "mod": label}


def validate_package(ctx: Context, path: Path) -> Package:
    label = path.name
    issues: list[Issue] = []
    try:
        manifest = load_toml(path / "mod.toml")
    except (OSError, tomllib.TOMLDecodeError) as error:
        package = Package(id=path.name, version="", path=path, manifest={})
        package.issues.append(Issue("manifest.parse", "error", f"mod.toml unreadable: {error}", label))
        return package

    mod_id = manifest.get("id")
    version = manifest.get("version")
    if not isinstance(mod_id, str) or not MOD_ID_RE.match(mod_id):
        issues.append(Issue("manifest.id", "error", f"invalid id: {mod_id!r}", label))
        mod_id = mod_id if isinstance(mod_id, str) else label
    if not isinstance(version, str) or not VERSION_RE.match(version):
        issues.append(Issue("manifest.version", "error", f"invalid version: {version!r}", label))
        version = version if isinstance(version, str) else "0"
    if not isinstance(manifest.get("name"), str) or not manifest.get("name"):
        issues.append(Issue("manifest.name", "error", "name is required", label))
    if manifest.get("spec", SCHEMA) != SCHEMA:
        issues.append(Issue("manifest.spec", "error", f"unsupported spec {manifest.get('spec')}", label))

    kind = manifest.get("type", "content")
    if kind not in ("content", "code", "mixed"):
        issues.append(Issue("manifest.type", "error", f"unknown type {kind!r}", label))
    if kind in ("code", "mixed"):
        issues.append(Issue("capability.code_unsupported", "error",
                            "code/mixed mods need C++ compiled into ps2EntryRunner.exe (a rebuild); this port cannot "
                            "load game code from a mod at runtime", label))
    for section, reason in UNSUPPORTED_SECTIONS.items():
        if section in manifest:
            issues.append(Issue(f"capability.{section}_unsupported", "error", f"[{section}]: {reason}", label))

    priority = manifest.get("priority", 0)
    if not isinstance(priority, int) or isinstance(priority, bool) or not -100 <= priority <= 100:
        issues.append(Issue("manifest.priority", "error", f"priority out of range: {priority!r}", label))
        priority = 0

    target = manifest.get("target")
    if not isinstance(target, dict) or not isinstance(target.get("game_id"), str):
        issues.append(Issue("target.missing", "error", "target.game_id is required", label))
        target = {}
    profile = load_toml(ctx.repo / "games" / "gow1" / "game.toml")
    if target.get("game_id") and target["game_id"] != profile.get("id"):
        issues.append(Issue("target.game", "error", f"targets game {target['game_id']}, not {profile.get('id')}", label))
    # The base profile keeps "usa" in [[editions]] and the other discs in [[regions]]; both are valid targets.
    known_regions = {item.get("id") for item in profile.get("regions", []) if isinstance(item, dict)} | \
                    {item.get("id") for item in profile.get("editions", []) if isinstance(item, dict)}
    for value in target.get("regions", []) if isinstance(target.get("regions", []), list) else []:
        if value not in known_regions:
            issues.append(Issue("target.region", "error", f"unknown region {value!r}", label))
    edition = target.get("edition")
    if edition is not None and not isinstance(edition, str):
        issues.append(Issue("target.edition", "error", "edition must be a string", label))

    requires = manifest.get("requires", {}).get("mods", []) if isinstance(manifest.get("requires"), dict) else []
    if not isinstance(requires, list) or not all(isinstance(item, str) for item in requires):
        issues.append(Issue("requires.mods", "error", "requires.mods must be an array of strings", label))
        requires = []
    for item in requires:
        if not mod_spec_valid(item):
            issues.append(Issue("requires.spec", "error", f"invalid mod reference {item!r}", label))
    conflicts = manifest.get("conflicts", {}).get("mods", []) if isinstance(manifest.get("conflicts"), dict) else []
    if not isinstance(conflicts, list) or not all(isinstance(item, str) for item in conflicts):
        issues.append(Issue("conflicts.mods", "error", "conflicts.mods must be an array of strings", label))
        conflicts = []
    for item in conflicts:
        if not mod_spec_valid(item):
            issues.append(Issue("conflicts.spec", "error", f"invalid mod reference {item!r}", label))

    package = Package(id=mod_id, version=version, path=path, manifest=manifest, issues=issues, priority=priority)
    # directory name must be "<id>@<version>" so importing twice is visible in the registry
    if path.name != f"{mod_id}@{version}":
        issues.append(Issue("package.name", "warn", f"folder is {path.name}, expected {mod_id}@{version}", label))

    total = 0
    count = 0

    def account(candidate: Path) -> bool:
        nonlocal total, count
        count += 1
        if count > MAX_FILES:
            issues.append(Issue("package.files", "error", f"more than {MAX_FILES} payload files", label))
            return False
        size = candidate.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            issues.append(Issue("package.size", "error", f"payload too large: {candidate.name}", label))
            return False
        return True

    # [effects] presets expand to existing runtime variables; an explicit [env] key always wins over a preset.
    preset_env: dict[str, Any] = {}
    effects = manifest.get("effects")
    if effects is not None:
        if not isinstance(effects, dict) or not isinstance(effects.get("presets", []), list):
            issues.append(Issue("effects.type", "error", "[effects] must have a presets array", label))
        else:
            for preset in effects.get("presets", []):
                if not isinstance(preset, str) or preset not in EFFECT_PRESETS:
                    issues.append(Issue("effects.unknown", "error", f"unknown effect preset {preset!r}", label))
                    continue
                for key, value in EFFECT_PRESETS[preset].items():
                    preset_env.setdefault(key, value)
    raw_env = dict(preset_env)
    explicit_env = manifest.get("env", {})
    if explicit_env and not isinstance(explicit_env, dict):
        issues.append(Issue("env.type", "error", "[env] must be a table", label))
    elif isinstance(explicit_env, dict):
        raw_env.update(explicit_env)
    for key, value in raw_env.items():
        text = str(value)
        if key in ENV_RESERVED:
            issues.append(Issue("env.reserved", "error", f"{key} is owned by the manager", label))
            continue
        if key not in ENV_ALLOWED:
            issues.append(Issue("env.unknown", "error", f"{key} is not read by this runtime (dead setting)", label))
            continue
        if len(text) > MAX_ENV_VALUE or "\n" in text or "\r" in text:
            issues.append(Issue("env.value", "error", f"{key} value is invalid", label))
            continue
        package.env[key] = text
        if ENV_ALLOWED[key] == "engine":
            issues.append(Issue("env.engine", "warn", f"{key} changes engine behaviour rather than content", label))
        elif ENV_ALLOWED[key] == "diagnostic":
            issues.append(Issue("env.diagnostic", "warn", f"{key} only writes diagnostics", label))

    textures = manifest.get("textures")
    if textures is not None:
        if not isinstance(textures, dict) or not isinstance(textures.get("dir", "textures"), str):
            issues.append(Issue("textures.type", "error", "[textures] must have dir", label))
        else:
            folder = resolve_dir(path, textures.get("dir", "textures"), issues, label)
            if folder is not None:
                for png in sorted(folder.glob("*.png")):
                    key = png.stem
                    if not re.match(r"^[0-9a-f]+-[0-9a-f]+(?:-[0-9a-f]+)?$", key):
                        issues.append(Issue("textures.name", "error", f"not a PCSX2 texture name: {png.name}", label))
                        continue
                    if key in package.textures:
                        issues.append(Issue("textures.duplicate", "error", f"duplicate texture {key}", label))
                        continue
                    if not account(png):
                        continue
                    broken, dims = validate_png(png)
                    if broken is not None:
                        issues.append(Issue("textures.format", "error", f"{png.name}: {broken}", label))
                        continue
                    # Measured 2026-11-05 (patch 52): a pack image smaller than the GS texture it replaces (64x64 for a
                    # 512x512 name) exits the runner during the intro cutscene. PCSX2 packs keep the dumped size, and the
                    # name encodes it in TW/TH, so a mismatch is an incompatible mod, rejected before activation.
                    expected = texture_expected_size(key)
                    if dims is not None and expected is not None and dims != expected:
                        issues.append(Issue("textures.size", "error",
                                            f"{png.name}: image is {dims[0]}x{dims[1]}, the name's TW/TH is {expected[0]}x{expected[1]}",
                                            label))
                        continue
                    package.textures[key] = png
                if not package.textures and not any(issue.severity == "error" for issue in issues):
                    issues.append(Issue("textures.empty", "warn", "textures folder has no PNG", label))

    vfs = manifest.get("vfs")
    if vfs is not None:
        if not isinstance(vfs, dict):
            issues.append(Issue("vfs.type", "error", "[vfs] must be a table of guest path -> payload", label))
        else:
            for guest, relative in vfs.items():
                if not isinstance(guest, str) or reject_control_characters(guest) or not GUEST_PATH_RE.fullmatch(guest):
                    issues.append(Issue("vfs.guest", "error", f"not a guest path: {guest!r}", label))
                    continue
                key = canonical_guest_path(guest)
                if key in package.vfs:
                    issues.append(Issue("vfs.duplicate", "error", f"duplicate guest path {key}", label))
                    continue
                if reject_control_characters(str(relative)):
                    issues.append(Issue("vfs.payload", "error", f"payload path contains control characters: {relative!r}", label))
                    continue
                candidate = resolve_payload(path, str(relative), issues, label)
                if candidate is None:
                    continue
                if candidate.suffix.lower() in FORBIDDEN_PAYLOAD_SUFFIXES:
                    issues.append(Issue("vfs.executable", "error", f"executable payload: {relative}", label))
                    continue
                if not account(candidate):
                    continue
                package.vfs[key] = candidate

    raw_patches = manifest.get("patches", [])
    if raw_patches is None:
        raw_patches = []
    if not isinstance(raw_patches, list):
        issues.append(Issue("patches.type", "error", "[[patches]] must be an array of tables", label))
    elif len(raw_patches) > MAX_DATA_PATCHES:
        issues.append(Issue("patches.count", "error", f"more than {MAX_DATA_PATCHES} data patches", label))
    else:
        for index, item in enumerate(raw_patches):
            parsed = parse_data_patch(item, label, index, issues)
            if parsed is not None:
                package.patches.append(parsed)

    if not package.env and not package.textures and not package.vfs and not package.patches:
        issues.append(Issue("content.empty", "warn", "mod has no resource that this runtime consumes", label))

    if package.env:
        package.capabilities.append("env")
    if package.vfs:
        package.capabilities.append("vfs")
    if package.textures:
        package.capabilities.append("texture_pack")
    if package.patches:
        package.capabilities.append("data_patch")
    if any(key in EFFECT_KEYS for key in package.env):
        package.capabilities.append("effects")
    # Show what the mod actually changes, so "audio" or "gameplay" is never inferred from a generic "vfs".
    if any(key.endswith((".vag", ".pss", ".psw", ".str", ".xa", ".adp")) for key in package.vfs):
        package.capabilities.append("audio")
    if any(key in package.env for key in ("TOBIICHI_TRUCOS", "GOW_GOD_MODE", "GOW_WARP")):
        package.capabilities.append("gameplay")
    # A failed drop-folder import still installs a placeholder package, so the launcher can show WHY the
    # player's file was refused instead of pretending it was never there.
    marker = path / DROP_ERROR_FILE
    if marker.is_file():
        detail = marker.read_text(encoding="utf-8", errors="replace").strip()
        if detail:
            issues.append(Issue("drop.install", "error", detail[:400], label))
    notice = path / DROP_WARN_FILE
    if notice.is_file():
        detail = notice.read_text(encoding="utf-8", errors="replace").strip()
        if detail:
            issues.append(Issue("drop.notice", "warn", detail[:400], label))
    return package


def mod_spec_valid(text: str) -> bool:
    mod_id, _, version = text.partition("@")
    return bool(MOD_ID_RE.match(mod_id)) and (not version or bool(VERSION_RE.match(version)))


def scan_packages(ctx: Context) -> dict[tuple[str, str], Package]:
    packages: dict[tuple[str, str], Package] = {}
    if not ctx.packages_dir.is_dir():
        return packages
    for folder in sorted(ctx.packages_dir.iterdir(), key=lambda item: item.name):
        if not folder.is_dir() or folder.name.startswith(".") or not (folder / "mod.toml").is_file():
            continue
        package = validate_package(ctx, folder)
        key = package.key
        if key in packages:
            # Keep the first package and flag IT, so the duplicate is visible in `list` instead of silently
            # replacing a working install with whichever folder sorts last.
            packages[key].issues.append(Issue("package.duplicate", "error",
                                              f"{package.label} is installed twice (also {folder.name})", package.label))
            continue
        packages[key] = package
    return packages


# -------------------------------------------------------------------------------------------------------------- drop folder
# Minecraft-style installation: data/mods/mods/ is the only folder a player has to touch. Drop a .zip or an
# unpacked folder in, it is installed and enabled on the next refresh; delete it to uninstall. Every package
# still goes through validate_package, so the path/size/executable/TSV checks are the same as a manual import.

def drop_game_id(ctx: Context) -> str:
    return str(load_toml(ctx.repo / "games" / "gow1" / "game.toml").get("id", "gow1"))


def drop_slug(text: str) -> tuple[str, str]:
    """'My Cool Mod v1.2.zip' -> ('my-cool-mod', '1.2'); only used when the mod has no mod.toml."""
    stem = text.rsplit(".", 1)[0] if "." in text else text
    # A version is the LAST "v1.2"-ish token; a leading \b would miss "_v1.2" and split it into "v1" + "2".
    matches = list(re.finditer(r"v?(\d+(?:\.\d+){0,2})(?![0-9.])", stem, re.IGNORECASE))
    match = matches[-1] if matches else None
    version = match.group(1) if match else "1.0.0"
    name_part = (stem[:match.start()] + stem[match.end():]) if match else stem
    slug = re.sub(r"[^a-z0-9._-]+", "-", name_part.lower()).strip("-._")
    if not slug or not re.match(r"[a-z0-9]", slug[0]):
        slug = "mod-" + slug
    slug = slug[:64].rstrip("-._")
    if len(slug) < 2 or not MOD_ID_RE.match(slug):
        slug = "mod-" + digest(text)[:8]
    if not VERSION_RE.match(version):
        version = "1.0.0"
    return slug, version


def drop_fingerprint(entry: Path) -> str:
    if entry.is_file():
        return sha256_file(entry)
    hasher = hashlib.sha256()
    for item in sorted(entry.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue
        hasher.update(str(item.relative_to(entry)).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def drop_extract_zip(entry: Path, target: Path) -> Path:
    """Manual extraction (never extractall): block zip-slip, symlinks, control characters and executables."""
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(entry) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_FILES:
            raise ManagerError(f"archive has more than {MAX_FILES} files")
        if sum(info.file_size for info in members) > MAX_TOTAL_BYTES:
            raise ManagerError("uncompressed archive is too large")
        for info in members:
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part]
            if (not parts or name.startswith("/") or ".." in parts or "\0" in name
                    or reject_control_characters(name) or any(":" in part for part in parts)
                    or ((info.external_attr >> 16) & 0o170000) == 0o120000
                    or info.file_size > MAX_FILE_BYTES
                    or Path(name).suffix.lower() in FORBIDDEN_PAYLOAD_SUFFIXES):
                raise ManagerError(f"unsafe archive member: {name!r}")
            destination = target.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info) as source, destination.open("wb") as out:
                while True:
                    chunk = source.read(1 << 20)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_FILE_BYTES:
                        raise ManagerError(f"archive member is too large: {name!r}")
                    out.write(chunk)
        # The usual shape is a zip with one top-level folder; use that folder as the package root.
        roots = {info.filename.replace("\\", "/").lstrip("/").split("/")[0] for info in members}
        if len(roots) == 1 and all("/" in info.filename.replace("\\", "/").lstrip("/") for info in members):
            return target / next(iter(roots))
    return target


def drop_prepare_tree(entry: Path, temp: Path) -> Path:
    if entry.is_file() and entry.suffix.lower() == ".zip":
        return drop_extract_zip(entry, temp / "unpacked")
    for item in entry.rglob("*"):
        if item.is_symlink():
            raise ManagerError(f"symlink in mod folder: {item.name}")
        if item.is_file() and item.suffix.lower() in FORBIDDEN_PAYLOAD_SUFFIXES:
            raise ManagerError(f"executable file in mod folder: {item.name}")
    root = temp / "copied"
    shutil.copytree(entry, root)
    return root


def drop_generate_manifest(ctx: Context, root: Path, entry: Path) -> None:
    if (root / "mod.toml").is_file():
        return  # the author supplied one; do not guess anything
    for hint, reason in DROP_UNSUPPORTED_HINTS.items():
        if (root / hint).is_file():
            raise ManagerError(reason)
    slug, version = drop_slug(entry.name)
    name = entry.stem if entry.is_file() else entry.name
    lines = ["# Generated by the drop-folder installer; edit it to fine-tune this mod.",
             f"spec = {SCHEMA}", f"id = {json.dumps(slug)}", f"name = {json.dumps(name)}",
             f"version = {json.dumps(version)}", 'type = "content"',
             "[target]", f"game_id = {json.dumps(drop_game_id(ctx))}"]
    pngs = sorted(item for item in root.rglob("*.png") if item.is_file() and not item.is_symlink())
    if pngs:
        folder = root / "textures"
        folder.mkdir(exist_ok=True)
        for png in pngs:
            if png.parent != folder and not (folder / png.name).exists():
                png.rename(folder / png.name)
        lines += ["", "[textures]", 'dir = "textures"']
    # Stand-alone audio / FMV / IOP module files: these ARE opened by guest path, so a VFS override works.
    # An explicit vfs.toml always wins over guessing.
    if not (root / "vfs.toml").is_file():
        mapped: list[tuple[str, str]] = []
        for item in sorted(root.rglob("*")):
            if not item.is_file() or item.is_symlink() or item.suffix.lower() not in DROP_VFS_SUFFIXES:
                continue
            relative = item.relative_to(root).as_posix()
            if relative.startswith("textures/"):
                continue
            guest = (f"cdrom0:\\IOP_MOD\\{item.name}" if item.suffix.lower() == ".irx"
                     else f"cdrom0:\\{item.name}")
            mapped.append((guest, relative))
        if mapped:
            lines += ["", "[vfs]"]
            for guest, relative in mapped:
                lines.append(f"{json.dumps(guest)} = {json.dumps(relative)}")
            # Never let a player believe PAK-contained audio or game code was replaced: say so in the UI.
            (root / DROP_WARN_FILE).write_text(
                "VFS overrides only replace files the game opens by guest PATH. Audio/FMV packed inside "
                "PART1.PAK/PART2.PAK is read by sector and is NOT replaced. Game code cannot be changed "
                "by a mod in this port (it needs a runner rebuild).", encoding="utf-8")
    effects_path = root / "effects.toml"
    if effects_path.is_file():
        try:
            effects_data = load_toml(effects_path)
            presets = effects_data.get("presets", []) if isinstance(effects_data, dict) else []
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ManagerError(f"effects.toml is not valid TOML: {exc}")
        if isinstance(presets, list) and presets:
            lines += ["", "[effects]",
                      "presets = [" + ", ".join(json.dumps(str(item)) for item in presets) + "]"]
    # Optional zero-config extras: vfs.toml (guest path -> payload) and env.toml (KEY -> value).
    for table_name, section in (("vfs.toml", "vfs"), ("env.toml", "env")):
        table_path = root / table_name
        if not table_path.is_file():
            continue
        try:
            table = load_toml(table_path)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ManagerError(f"{table_name} is not valid TOML: {exc}")
        if not isinstance(table, dict) or not table:
            continue
        lines += ["", f"[{section}]"]
        for key, value in table.items():
            lines.append(f"{json.dumps(str(key))} = {json.dumps(str(value))}")
    (root / "mod.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def drop_read_state(ctx: Context) -> dict[str, Any]:
    if ctx.ingested_path.is_file():
        try:
            data = json.loads(ctx.ingested_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema": SCHEMA, "items": {}}


def sync_drop_folder(ctx: Context, profile_name: str = DROP_PROFILE) -> dict[str, Any]:
    """Install/enable new or changed drop entries and uninstall deleted ones. Never raises: a broken mod must
    not take down `list`, which the launcher calls on every refresh. Idempotent via ingested.json."""
    summary: dict[str, Any] = {"installed": [], "failed": [], "removed": [], "error": ""}
    try:
        ctx.drop_dir.mkdir(parents=True, exist_ok=True)
        readme = ctx.drop_dir / "README.txt"
        if not readme.exists():
            atomic_write(readme,
                         "Drop .zip files or unpacked mod folders here.\n"
                         "They are installed and enabled automatically when the launcher refreshes.\n"
                         "Delete a file here to uninstall its mod.\n"
                         "A folder may contain mod.toml; without one the manager guesses the id/version\n"
                         "from the file name and treats PNG files as a texture pack.\n")
        state = drop_read_state(ctx)
        items: dict[str, Any] = state["items"]
        entries: dict[str, Path] = {}
        for entry in sorted(ctx.drop_dir.iterdir(), key=lambda item: item.name):
            if entry.name.startswith(".") or entry.name.upper() == "README.TXT":
                continue
            if entry.is_file() and entry.suffix.lower() != ".zip":
                continue
            if not (entry.is_file() or entry.is_dir()):
                continue
            entries[entry.name] = entry

        # Removed from the drop folder -> uninstall, but only packages this manager created.
        for name in list(items):
            if name in entries:
                continue
            record = items.pop(name) or {}
            label = record.get("package")
            if record.get("managed") and label:
                enabled = read_profile(ctx, profile_name)
                if label in enabled:
                    write_profile(ctx, profile_name, [item for item in enabled if item != label])
                shutil.rmtree(ctx.packages_dir / label, ignore_errors=True)
                summary["removed"].append(label)

        for name, entry in entries.items():
            try:
                fingerprint = drop_fingerprint(entry)
            except OSError as exc:
                summary["failed"].append(f"{name}: {exc}")
                continue
            record = items.get(name) or {}
            label = record.get("package")
            if (record.get("sha256") == fingerprint and label
                    and (ctx.packages_dir / label).is_dir()):
                continue  # unchanged: never re-enable a mod the player deliberately turned off

            temp = Path(tempfile.mkdtemp(prefix="ingest-", dir=ctx.mods))
            try:
                error = ""
                try:
                    root = drop_prepare_tree(entry, temp)
                    drop_generate_manifest(ctx, root, entry)
                    package = validate_package(ctx, root)
                    if not package.version:
                        raise ManagerError("mod.toml could not be parsed")
                    label = package.label
                    error = "; ".join(issue.message for issue in package.issues if issue.severity == "error")
                except Exception as exc:
                    slug, version = drop_slug(entry.name)
                    label = f"{slug}@{version}"
                    root = temp / "placeholder"
                    root.mkdir(parents=True, exist_ok=True)
                    (root / "mod.toml").write_text(
                        f"# Placeholder for a mod that could not be installed.\nspec = {SCHEMA}\n"
                        f"id = {json.dumps(slug)}\nname = {json.dumps(label)}\nversion = {json.dumps(version)}\n"
                        f"[target]\ngame_id = {json.dumps(drop_game_id(ctx))}\n", encoding="utf-8")
                    error = str(exc) or type(exc).__name__

                if error:
                    (root / DROP_ERROR_FILE).write_text(error[:400], encoding="utf-8")
                target = ctx.packages_dir / label
                if target.exists():
                    if record.get("managed") and record.get("package") == label:
                        shutil.rmtree(target)
                    else:
                        raise ManagerError(f"{label} is already installed from another source")
                shutil.copytree(root, target)
                if not error:
                    enabled = read_profile(ctx, profile_name)
                    if label not in enabled:
                        enabled.append(label)
                        write_profile(ctx, profile_name, enabled)
                items[name] = {"sha256": fingerprint, "package": label, "managed": True,
                               "status": "invalid" if error else "installed", "message": error[:400]}
                (summary["failed"] if error else summary["installed"]).append(label)
            except Exception as exc:
                items[name] = {"sha256": fingerprint, "package": None, "managed": False,
                               "status": "error", "message": str(exc)[:400]}
                summary["failed"].append(f"{name}: {exc}")
            finally:
                shutil.rmtree(temp, ignore_errors=True)

        drop_write_state(ctx, state)
    except Exception as exc:
        summary["error"] = str(exc)
    return summary


def drop_write_state(ctx: Context, state: dict[str, Any]) -> None:
    atomic_write_json(ctx.ingested_path, state)


# -------------------------------------------------------------------------------------------------------------- profile / plan

def profile_path(ctx: Context, name: str) -> Path:
    return ctx.profiles_dir / f"{name}.toml"


def read_profile(ctx: Context, name: str) -> list[str]:
    path = profile_path(ctx, name)
    if not path.is_file():
        return []
    data = load_toml(path)
    enabled = data.get("enabled", [])
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ManagerError(f"profile {name}: enabled must be an array of strings", 2)
    return enabled


def write_profile(ctx: Context, name: str, enabled: list[str]) -> None:
    lines = [f"# Mod profile {name}. Managed by tools/mods/gow_mods_cli.py; edit it with `enable`/`disable`.",
             f"schema = {SCHEMA}", f"name = {json.dumps(name)}", "enabled = ["]
    lines += [f"  {json.dumps(item)}," for item in enabled]
    lines += ["]", ""]
    atomic_write(profile_path(ctx, name), "\n".join(lines))


def find_package(packages: dict[tuple[str, str], Package], spec: str) -> Package | None:
    mod_id, _, version = spec.partition("@")
    if version:
        return packages.get((mod_id, version))
    installed = [package for key, package in packages.items() if key[0] == mod_id]
    if not installed:
        return None
    return max(installed, key=lambda package: version_key(package.version))


def select_enabled(packages: dict[tuple[str, str], Package], specs: list[str]) -> tuple[list[Package], list[Issue]]:
    issues: list[Issue] = []
    selected: dict[tuple[str, str], Package] = {}
    for spec in specs:
        package = find_package(packages, spec)
        if package is None:
            issues.append(Issue("profile.missing", "warn", f"{spec} is not installed", spec))
            continue
        selected[package.key] = package
    return list(selected.values()), issues


def expand_dependencies(packages: dict[tuple[str, str], Package], selected: dict[tuple[str, str], Package]) -> list[Issue]:
    issues: list[Issue] = []
    queue = list(selected.values())
    while queue:
        package = queue.pop()
        requires = package.manifest.get("requires", {}).get("mods", []) if isinstance(package.manifest.get("requires"), dict) else []
        for spec in requires:
            dependency = find_package(packages, spec)
            if dependency is None:
                issues.append(Issue("requires.missing", "error",
                                    f"{package.label} requires {spec}, which is not installed", package.label))
                # Do not mutate package.issues here: that is the per-package validation record, while this
                # issue belongs to the plan (and would otherwise make the package look invalid twice).
                continue
            if dependency.key not in selected:
                selected[dependency.key] = dependency
                queue.append(dependency)
    return issues


def _requirement_present(packages: dict[tuple[str, str], Package], selected: dict[tuple[str, str], Package], spec: str) -> bool:
    dependency = find_package(packages, spec)
    return dependency is not None and dependency.key in selected


def rank_of(package: Package) -> tuple:
    return (-package.priority, package.id, tuple(-item[1] if isinstance(item[1], int) else 0 for item in version_key(package.version)))


def resolve_order(packages: dict[tuple[str, str], Package], selected: dict[tuple[str, str], Package]) -> tuple[list[Package], list[Issue]]:
    issues: list[Issue] = []
    indegree: dict[tuple[str, str], int] = {key: 0 for key in selected}
    edges: dict[tuple[str, str], list[tuple[str, str]]] = {key: [] for key in selected}
    for package in selected.values():
        requires = package.manifest.get("requires", {}).get("mods", []) if isinstance(package.manifest.get("requires"), dict) else []
        for spec in requires:
            dependency = find_package(packages, spec)
            if dependency is None or dependency.key not in selected:
                continue
            edges[dependency.key].append(package.key)
            indegree[package.key] += 1

    ready = [key for key, value in indegree.items() if value == 0]
    ordered_keys: list[tuple[str, str]] = []
    while ready:
        ready.sort(key=lambda key: rank_of(packages[key]))
        key = ready.pop(0)
        ordered_keys.append(key)
        for dependent in edges[key]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if len(ordered_keys) != len(selected):
        for key in selected:
            if key not in ordered_keys:
                issues.append(Issue("requires.cycle", "error", f"{packages[key].label} is part of a dependency cycle", packages[key].label))
    return [packages[key] for key in ordered_keys], issues


def build_plan(ctx: Context, profile: str, packages: dict[tuple[str, str], Package]) -> dict[str, Any]:
    fingerprint, changed = ensure_fingerprint(ctx)
    specs = read_profile(ctx, profile)
    found, issues = select_enabled(packages, specs)
    # Invalid packages must stay in the candidate set: filtering them here made enabled-but-broken mods vanish
    # from the plan without appearing in `excluded` or `issues`.
    candidates = {package.key: package for package in found}
    issues += expand_dependencies(packages, candidates)
    ordered, order_issues = resolve_order(packages, candidates)
    issues += order_issues

    excluded: list[dict[str, str]] = []
    plan_mods: list[dict[str, Any]] = []
    env_map: dict[str, dict[str, str]] = {}
    vfs_map: dict[str, dict[str, str]] = {}
    texture_map: dict[str, dict[str, str]] = {}
    conflicts: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    excluded_keys: set[tuple[str, str]] = set()
    patch_rows: list[dict[str, Any]] = []

    def exclude(package: Package, reason: str, message: str = "") -> None:
        excluded_keys.add(package.key)
        # "message" is what ModsModel shows in the UI; "reason" is the machine-readable summary.
        excluded.append({"mod": package.label, "reason": reason,
                         "message": message or f"{package.label}: {reason}"})

    def declared_mods(package: Package, section: str) -> list[str]:
        table = package.manifest.get(section, {})
        if not isinstance(table, dict) or not isinstance(table.get("mods", []), list):
            return []
        return [item for item in table.get("mods", []) if isinstance(item, str)]

    # Phase 1a: decide eligibility BEFORE merging any resource. Validation, target and missing requirements
    # are settled first so an excluded mod cannot influence the conflicts of a usable one.
    eligible: dict[tuple[str, str], Package] = {}
    for package in ordered:
        if not package.valid:
            detail = "; ".join(issue.message for issue in package.issues if issue.severity == "error") or "validation failed"
            exclude(package, "validation failed", f"{package.label}: {detail}")
            issues.append(Issue("mod.invalid", "error", f"{package.label} is enabled but invalid: {detail}", package.label))
            continue
        target = package.target()
        regions = target.get("regions") or []
        # game.toml ids cover both the code region ("japan") and disc editions ("asia-97399"); the fingerprint
        # carries them in "region"/"edition" respectively, so accept either instead of only one of them.
        if isinstance(regions, list) and regions and not any(
                region in (fingerprint["region"], fingerprint["edition"]) for region in regions):
            exclude(package, f"targets region {regions}, this is {fingerprint['region']}/{fingerprint['edition']}")
            warnings.append({"code": "target.region", "mod": package.label, "message": "does not target this region"})
            continue
        edition = target.get("edition")
        if edition and edition not in (fingerprint["edition"], fingerprint["region"]):
            exclude(package, f"targets edition {edition}, this is {fingerprint['edition']}")
            continue
        missing = [spec for spec in declared_mods(package, "requires")
                   if not _requirement_present(packages, eligible, spec)]
        if missing:
            exclude(package, f"missing requirement {', '.join(missing)}")
            continue
        eligible[package.key] = package

    # resolve_order omits mods caught in a dependency cycle; report them instead of dropping them silently.
    ordered_keys = {package.key for package in ordered}
    for key, package in candidates.items():
        if key not in ordered_keys and key not in excluded_keys:
            exclude(package, "dependency cycle")

    # Phase 1b: conflicts only between mods that are still in `kept`. A mod removed by 1a (region, validation,
    # missing dependency) can no longer knock a perfectly usable mod out of the plan.
    kept = dict(eligible)
    for package in ordered:
        if package.key not in kept:
            continue
        for other_spec in declared_mods(package, "conflicts"):
            other = find_package(packages, other_spec)
            if other is None or other.key == package.key or other.key not in kept:
                continue
            conflicts.append({"mod": package.label, "with": other.label, "reason": "declared conflict",
                              "severity": "warning", "message": f"{package.label} conflicts with {other.label}"})
            drop = package if rank_of(package) > rank_of(other) else other
            kept.pop(drop.key, None)
            rival = other.label if drop is package else package.label
            exclude(drop, f"conflicts with {rival}", f"{drop.label} conflicts with {rival}")
            if drop is package:
                break

    # Phase 2: merge only the survivors. `ordered` is ranked, so the first writer of a key is the
    # higher-priority mod (which is what the "higher-ranked mod wins" warnings say).
    for package in ordered:
        if package.key not in kept:
            continue
        plan_mods.append({
            "id": package.id, "version": package.version, "priority": package.priority,
            "capabilities": package.capabilities, "path": str(package.path),
        })
        for patch in package.patches:
            # A guest address is only valid for the .text it was measured on. A USA address applied to the
            # Japan build writes into unrelated memory, so refuse the plan instead of guessing.
            bound = patch.get("text_sha1")
            if bound and bound != str(fingerprint["textSha1"]).lower():
                issues.append(Issue("patches.elf", "error",
                                    f"{package.label}: patch 0x{patch['address']:X} is bound to .text {bound}, "
                                    f"this build is {fingerprint['textSha1']}", package.label))
                continue
            region = patch.get("region")
            if region and region not in (fingerprint["region"], fingerprint["edition"]):
                warnings.append({"code": "patches.region", "mod": package.label,
                                 "message": f"patch for region {region} skipped on {fingerprint['region']}"})
                continue
            patch_rows.append(patch)
        for key, value in package.env.items():
            if key in env_map and env_map[key]["value"] != value:
                conflicts.append({"mod": package.label, "with": env_map[key]["mod"], "reason": f"{key} set differently",
                                  "severity": "warning", "message": f"{key} is set differently by {package.label}"})
                warnings.append({"code": "env.shadowed", "mod": package.label,
                                 "message": f"{key} is already set by {env_map[key]['mod']}; the higher-ranked mod wins"})
                continue
            env_map.setdefault(key, {"value": value, "mod": package.label})
        for guest, host in package.vfs.items():
            if guest in vfs_map:
                warnings.append({"code": "vfs.shadowed", "mod": package.label,
                                 "message": f"{guest} is already provided by {vfs_map[guest]['mod']}; the higher-ranked mod wins"})
                continue
            vfs_map[guest] = {"host": str(host), "mod": package.label, "sha256": sha256_file(host)}
        for key, host in package.textures.items():
            if key in texture_map:
                warnings.append({"code": "texture.shadowed", "mod": package.label,
                                 "message": f"texture {key} is already provided by {texture_map[key]['mod']}; the higher-ranked mod wins"})
                continue
            texture_map[key] = {"host": str(host), "mod": package.label, "sha256": sha256_file(host)}

    payload = {
        "profile": profile,
        "fingerprintId": fingerprint["fingerprintId"],
        "fingerprint": {key: fingerprint[key] for key in
                        ("gameId", "edition", "region", "elfCrc", "textSha1", "runtimeCommit", "patchChainHash")},
        "mods": plan_mods,
        "env": env_map,
        "vfs": vfs_map,
        "textures": texture_map,
        "patches": patch_rows,
        # Data patches are interpreted by host C++ (runtime patch 84). A runner built before that patch
        # simply ignores GOW_MOD_PATCH_TABLE, so the launcher tells the player to rebuild once.
        "requiresRebuild": bool(patch_rows),
        "excluded": excluded,
        "conflicts": conflicts,
        "warnings": warnings,
        "issues": [issue.as_dict() for issue in issues],
    }
    plan_id = digest(stable_json(payload))
    plan = {"schema": SCHEMA, "planId": plan_id, "createdAt": iso(now()), **payload}
    atomic_write_json(ctx.plans_dir / f"{plan_id}.json", plan)
    return plan


def plan_hook_env(plan: dict[str, Any], staging: Path, hooks_dir: Path | None = None) -> dict[str, str]:
    env = {key: entry["value"] for key, entry in plan["env"].items()}
    if plan["textures"]:
        env["GOW_TEXTURE_PACK"] = str((staging / "textures").resolve())
    if plan.get("patches") and hooks_dir is not None:
        env["GOW_MOD_PATCH_TABLE"] = str((hooks_dir / "data-patches.tsv").resolve())
    return env


# -------------------------------------------------------------------------------------------------------------- activation

def current_state(ctx: Context) -> dict[str, Any]:
    if not ctx.state_path.is_file():
        return {"schema": SCHEMA, "activePlan": None, "enabled": [], "fingerprintId": None}
    try:
        return json.loads(ctx.state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema": SCHEMA, "activePlan": None, "enabled": [], "fingerprintId": None}


def hooks_snapshot(ctx: Context) -> dict[str, str | None]:
    names = ("env.json", "vfs-overrides.tsv", "data-patches.tsv", "plan.json", "profile.txt", "state.json")
    snapshot: dict[str, str | None] = {}
    for name in names:
        path = ctx.state_path if name == "state.json" else ctx.hooks_dir / name
        snapshot[name] = path.read_text(encoding="utf-8") if path.is_file() else None
    return snapshot


def write_hooks(ctx: Context, plan: dict[str, Any], staging: Path) -> None:
    atomic_write_json(ctx.hooks_dir / "env.json", plan["env"])
    lines = ["# guest path\tstaged host path (patch 71)",
             "# generated by tools/mods/gow_mods_cli.py; do not edit while the game runs"]
    for guest, entry in sorted(plan["vfs"].items()):
        host = (staging / "vfs" / digest(guest)[:16] / Path(entry["host"]).name).resolve()
        if reject_control_characters(guest) or reject_control_characters(str(host)):
            raise ManagerError(f"refusing to write an unsafe VFS table row for {guest!r}", 4)
        lines.append(f"{guest}\t{host}")
    atomic_write(ctx.hooks_dir / "vfs-overrides.tsv", "\n".join(lines) + "\n")
    # Declarative guest-RAM patches (runtime patch 84). Six fixed columns, no free-form text: the runtime
    # only ever interprets numbers, so a mod cannot smuggle code or a new table row into this file.
    patch_lines = ["# address\twidth\tvalue\tmask\texpected\tonce",
                   "# generated by tools/mods/gow_mods_cli.py; declarative data, interpreted by host C++"]
    for patch in plan.get("patches", []):
        patch_lines.append(f"0x{patch['address']:08X}\t{patch['width']}\t0x{patch['value']:08X}"
                           f"\t0x{patch['mask']:08X}\t0x{patch['expected']:08X}\t{patch['once']}")
    atomic_write(ctx.hooks_dir / "data-patches.tsv", "\n".join(patch_lines) + "\n")
    atomic_write_json(ctx.hooks_dir / "plan.json", plan)
    atomic_write(ctx.hooks_dir / "profile.txt", plan["profile"] + "\n")


def materialize(ctx: Context, plan: dict[str, Any], staging: Path) -> None:
    # Rebuild from scratch: the plan id covers the file hashes, so a stale folder can only come from a partial
    # earlier attempt, and leftover resources would silently survive a change.
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    if plan["textures"]:
        folder = staging / "textures"
        folder.mkdir(parents=True, exist_ok=True)
        for key, entry in plan["textures"].items():
            source = Path(entry["host"])
            if not source.is_file():
                raise ManagerError(f"staged source disappeared: {source}", 4)
            target = folder / f"{key}.png"
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
    if plan["vfs"]:
        for guest, entry in plan["vfs"].items():
            source = Path(entry["host"])
            if not source.is_file():
                raise ManagerError(f"staged source disappeared: {source}", 4)
            folder = staging / "vfs" / digest(guest)[:16]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / source.name
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
    atomic_write_json(staging / "plan.json", plan)


def activate(ctx: Context, plan: dict[str, Any]) -> Path:
    plan_id = plan["planId"]
    staging = ctx.staging_dir / plan_id
    journal = {
        "schema": SCHEMA,
        "planId": plan_id,
        "startedAt": iso(now()),
        "status": "applying",
        "previous": hooks_snapshot(ctx),
        "steps": [],
    }
    journal_path = ctx.journal_dir / f"{plan_id}.json"
    atomic_write_json(journal_path, journal)

    def step(record: dict[str, Any]) -> None:
        journal["steps"].append(record)
        atomic_write_json(journal_path, journal)

    try:
        step({"op": "materialize", "staging": str(staging)})
        materialize(ctx, plan, staging)
        step({"op": "hooks", "dir": str(ctx.hooks_dir)})
        write_hooks(ctx, plan, staging)
        state = {
            "schema": SCHEMA,
            "fingerprintId": plan["fingerprintId"],
            "activePlan": plan_id,
            "profile": plan["profile"],
            "enabled": [{"id": item["id"], "version": item["version"]} for item in plan["mods"]],
            "activatedAt": iso(now()),
            "staging": str(staging),
        }
        step({"op": "state", "path": str(ctx.state_path)})
        atomic_write_json(ctx.state_path, state)
        journal["status"] = "applied"
        journal["finishedAt"] = iso(now())
        atomic_write_json(journal_path, journal)
        return staging
    except Exception:
        restore(ctx, journal)
        journal["status"] = "rolled-back"
        journal["finishedAt"] = iso(now())
        atomic_write_json(journal_path, journal)
        raise


def restore(ctx: Context, journal: dict[str, Any]) -> None:
    plan_id = journal.get("planId", "")
    staging = ctx.staging_dir / plan_id if plan_id else None
    if staging is not None and staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    previous = journal.get("previous", {})
    for name in ("env.json", "vfs-overrides.tsv", "data-patches.tsv", "plan.json", "profile.txt"):
        path = ctx.hooks_dir / name
        value = previous.get(name)
        if value is not None:
            atomic_write(path, value)
        elif path.exists():
            path.unlink()
    value = previous.get("state.json")
    if value is not None:
        atomic_write(ctx.state_path, value)
    elif ctx.state_path.exists():
        ctx.state_path.unlink()


def deactivate(ctx: Context, reason: str = "") -> None:
    state = current_state(ctx)
    previous = hooks_snapshot(ctx)
    plan_id = state.get("activePlan")
    # Keep this journal separate from the activation journal: `rollback <planId>` must still be able to restore
    # the PRE-activation state, not this snapshot of the already active hooks.
    stamp = now().strftime("%Y%m%d%H%M%S")
    journal_path = ctx.journal_dir / f"{plan_id or 'none'}-deactivate-{stamp}-{os.getpid()}.json"
    journal = {"schema": SCHEMA, "planId": plan_id or "deactivate", "startedAt": iso(now()),
               "status": "rolling-back", "reason": reason, "previous": previous, "steps": []}
    atomic_write_json(journal_path, journal)
    # restore() expects the state BEFORE the transaction. Passing the snapshot we just took (the active one)
    # would rewrite every hook and state.json exactly as they were, i.e. deactivate would not clean anything.
    restore(ctx, {**journal, "previous": {}})
    state = {"schema": SCHEMA, "activePlan": None, "enabled": [], "fingerprintId": state.get("fingerprintId"),
             "profile": state.get("profile"), "staging": None, "deactivatedAt": iso(now()), "reason": reason}
    atomic_write_json(ctx.state_path, state)
    journal["status"] = "deactivated"
    journal["finishedAt"] = iso(now())
    atomic_write_json(journal_path, journal)


# -------------------------------------------------------------------------------------------------------------- launching

def runner_and_elf(ctx: Context) -> tuple[Path, Path]:
    builds_path = ctx.repo / "data" / "gow1" / "regional-builds.json"
    build = json.loads(builds_path.read_text(encoding="utf-8"))["builds"][0]
    runner = Path(build["runner"])
    elf = Path(build["elf"])
    if not runner.is_file():
        raise ManagerError(f"runner not found: {runner}", 5)
    if not elf.is_file():
        raise ManagerError(f"guest ELF not found: {elf}", 5)
    return runner, elf


def sanitized_environ() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("GOW_MOD_VFS_TABLE", "GOW_MOD_VFS_STATS", "GOW_MOD_VFS_TRACE", "GOW_TEXTURE_PACK"):
        env.pop(key, None)
    return env


def run_game(ctx: Context, label: str, seconds: int, no_mods: bool, extra: dict[str, str]) -> dict[str, Any]:
    state = current_state(ctx)
    fingerprint, changed = ensure_fingerprint(ctx)
    if state.get("activePlan") and state.get("fingerprintId") != fingerprint["fingerprintId"]:
        deactivate(ctx, "game identity changed")
        state = current_state(ctx)
        changed = True
    if not no_mods and not state.get("activePlan"):
        raise ManagerError("no active plan; run `apply` first (or pass --no-mods for the baseline)", 6)

    stamp = now().strftime("%Y%m%d-%H%M%S")
    run_dir = ctx.runs_dir / f"{stamp}-{label or 'run'}"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = sanitized_environ()
    active_plan = None
    if not no_mods:
        active_plan = json.loads((ctx.hooks_dir / "plan.json").read_text(encoding="utf-8"))
        staging = Path(state["staging"])
        env.update(plan_hook_env(active_plan, staging, ctx.hooks_dir))
        env["GOW_MOD_VFS_TABLE"] = str((ctx.hooks_dir / "vfs-overrides.tsv").resolve())
    env["GOW_MOD_VFS_STATS"] = str(run_dir / "vfs-stats.json")
    env["GOW_MOD_VFS_TRACE"] = str(run_dir / "vfs-trace.txt")
    # --set is documented as "applied last": put it after the plan so a test-harness setting really wins.
    env.update(extra)

    runner, elf = runner_and_elf(ctx)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    started = time.time()
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        process = subprocess.Popen([str(runner), elf.name], cwd=str(elf.parent), env=env, stdout=out, stderr=err)
        timed_out = False
        try:
            process.wait(timeout=seconds if seconds > 0 else None)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
    result = {
        "schema": SCHEMA,
        "label": label,
        "profile": state.get("profile"),
        "mods": [] if no_mods else state.get("enabled", []),
        "planId": None if no_mods else state.get("activePlan"),
        "fingerprintId": fingerprint["fingerprintId"],
        "fingerprintChangedDuringRun": changed,
        "seconds": round(time.time() - started, 2),
        "timedOut": timed_out,
        "exitCode": process.returncode,
        "envApplied": {key: env[key] for key in ("GOW_TEXTURE_PACK", "GOW_MOD_VFS_TABLE") if key in env},
        "envMods": {key: entry["value"] for key, entry in (active_plan or {}).get("env", {}).items()},
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "vfsStats": str(run_dir / "vfs-stats.json"),
        "vfsTrace": str(run_dir / "vfs-trace.txt"),
    }
    if (run_dir / "vfs-stats.json").is_file():
        try:
            result["vfs"] = json.loads((run_dir / "vfs-stats.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    atomic_write_json(run_dir / "run.json", result)
    atomic_write_json(ctx.reports_dir / f"{run_dir.name}.json", result)
    return result


def log_evidence(run: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {"lines": {}}
    for key, patterns in {
        "stderr": {"texpack": "[gs-texpack]", "modvfs": "[mod-vfs]", "pad": "[gow-pad2:test] state=", "present": "[gs-present]"},
    }.items():
        path = Path(run.get(key, ""))
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        evidence["lines"][key] = {name: [line for line in text.splitlines() if token in line][-6:]
                                  for name, token in patterns.items()}
        tail = text.splitlines()[-1] if text.splitlines() else ""
        evidence["lines"][key]["last"] = tail
    return evidence


# -------------------------------------------------------------------------------------------------------------- commands

def describe_plan(plan: dict[str, Any]) -> str:
    lines = [f"plan {plan['planId'][:12]} profile={plan['profile']} mods={len(plan['mods'])}",
             f"fingerprint {plan['fingerprintId'][:12]} region={plan['fingerprint']['region']} edition={plan['fingerprint']['edition']}"]
    for item in plan["mods"]:
        lines.append(f"  + {item['id']}@{item['version']} priority={item['priority']} capabilities={','.join(item['capabilities']) or '-'}")
    for item in plan["excluded"]:
        lines.append(f"  - {item['mod']}: {item['reason']}")
    for conflict in plan["conflicts"]:
        lines.append(f"  ! {conflict['mod']} vs {conflict['with']}: {conflict['reason']}")
    lines.append(f"  env={len(plan['env'])} vfs={len(plan['vfs'])} textures={len(plan['textures'])}")
    return "\n".join(lines)


def cmd_fingerprint(ctx: Context, args: argparse.Namespace) -> int:
    record, changed = ensure_fingerprint(ctx)
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
    else:
        print(f"fingerprint {record['fingerprintId']} changed={changed}")
        for key in ("gameId", "edition", "region", "elfCrc", "textSha1", "runtimeCommit", "patchChainHash"):
            print(f"  {key}: {record[key]}")
        print(f"  runnerSha256: {record['runnerSha256']}")
    return 0


def cmd_list(ctx: Context, args: argparse.Namespace) -> int:
    sync_drop_folder(ctx, args.profile)
    packages = scan_packages(ctx)
    enabled = set(read_profile(ctx, args.profile))
    rows = []
    for package in sorted(packages.values(), key=lambda item: (item.id, version_key(item.version))):
        rows.append({
            "mod": package.label, "name": package.manifest.get("name", ""),
            "type": package.manifest.get("type", "content"), "priority": package.priority,
            "capabilities": package.capabilities, "valid": package.valid,
            "enabled": any(find_package(packages, spec) is not None and find_package(packages, spec).key == package.key
                           for spec in enabled),
            "issues": [issue.as_dict() for issue in package.issues if issue.severity == "error"],
            # ModsModel::refresh reads this key to show a warning when there is no error.
            "warnings": [issue.as_dict() for issue in package.issues if issue.severity == "warn"],
            # Optional metadata for the details panel (all rendered as plain text by the launcher).
            "description": brief(package.manifest.get("description")),
            "author": brief(package.manifest.get("author")),
            "homepage": brief(package.manifest.get("homepage")),
            "path": str(package.path),
        })
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            mark = "ERR" if not row["valid"] else ("on " if row["enabled"] else "off")
            print(f"{mark} {row['mod']:<40} {','.join(row['capabilities']) or '-':<20} priority={row['priority']}")
    return 0


def cmd_validate(ctx: Context, args: argparse.Namespace) -> int:
    sync_drop_folder(ctx, DROP_PROFILE)
    packages = scan_packages(ctx)
    if args.mod:
        matches = [package for package in packages.values() if package.label == args.mod or package.id == args.mod]
        if not matches:
            raise ManagerError(f"{args.mod} is not installed", 2)
        packages = {(package.id, package.version): package for package in matches}
    bad = 0
    rows = []
    for package in packages.values():
        errors = [issue for issue in package.issues if issue.severity == "error"]
        warns = [issue for issue in package.issues if issue.severity == "warn"]
        if args.json:
            rows.append({"mod": package.label, "valid": not errors,
                         "issues": [issue.as_dict() for issue in package.issues]})
        else:
            print(f"{'FAIL' if errors else 'OK  '} {package.label}: {len(errors)} error(s), {len(warns)} warning(s)")
            for issue in errors + warns:
                print(f"     {issue.severity:<5} {issue.code:<32} {issue.message}")
        bad += 1 if errors else 0
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0 if bad == 0 else 2


def _replace_dir(source: Path, target: Path) -> None:
    """os.replace for folders; Windows denies the rename while a scanner holds the fresh copy, so retry briefly."""
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 5:
                shutil.rmtree(source, ignore_errors=True)
                raise
            time.sleep(0.2)


def cmd_import(ctx: Context, args: argparse.Namespace) -> int:
    source = Path(args.source).resolve()
    if not (source / "mod.toml").is_file():
        raise ManagerError(f"{source} has no mod.toml", 2)
    package = validate_package(ctx, source)
    if not package.valid:
        for issue in package.issues:
            if issue.severity == "error":
                print(f"error {issue.code}: {issue.message}", file=sys.stderr)
        raise ManagerError("package is invalid; nothing was copied", 2)
    target = ctx.packages_dir / f"{package.id}@{package.version}"
    resolved_target = target.resolve()
    # Importing a package over itself (or over a folder that contains it) deleted the source before copying it,
    # silently destroying the user's mod. Reject those shapes instead.
    if (source == resolved_target or source.is_relative_to(resolved_target)
            or resolved_target.is_relative_to(source)):
        raise ManagerError("source folder overlaps the package being replaced; nothing was copied", 2)
    backup = None
    if target.exists():
        if not args.replace:
            raise ManagerError(f"{target.name} is already installed (use --replace)", 3)
        backup = ctx.packages_dir / f".backup-{target.name}-{os.getpid()}"
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(target, backup)
    # Unique scratch folder: two simultaneous imports must not delete each other's copy.
    temp = Path(tempfile.mkdtemp(prefix=".import-", dir=ctx.packages_dir))
    try:
        shutil.copytree(source, temp, dirs_exist_ok=True)
        _replace_dir(temp, target)
    except Exception:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    print(f"installed {package.label} in {target}")
    return 0


def _change_enabled(ctx: Context, args: argparse.Namespace, enable: bool) -> int:
    packages = scan_packages(ctx)
    enabled = read_profile(ctx, args.profile)
    if enable:
        for spec in args.mods:
            package = find_package(packages, spec)
            if package is None:
                raise ManagerError(f"{spec} is not installed", 2)
            if not package.valid:
                raise ManagerError(f"{package.label} does not validate; fix it before enabling", 2)
            label = package.label
            if label not in enabled:
                enabled.append(label)
    else:
        for spec in args.mods:
            package = find_package(packages, spec)
            if package is None:
                raise ManagerError(f"{spec} is not installed", 2)
            enabled = [item for item in enabled
                       if not (item.partition("@")[0] == package.id and (not item.partition("@")[2] or item == package.label))]
    write_profile(ctx, args.profile, enabled)
    print(f"profile {args.profile}: {len(enabled)} enabled")
    for item in enabled:
        print(f"  {item}")
    return 0


def cmd_plan(ctx: Context, args: argparse.Namespace) -> int:
    sync_drop_folder(ctx, args.profile)
    packages = scan_packages(ctx)
    plan = build_plan(ctx, args.profile, packages)
    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print(describe_plan(plan))
        for warning in plan["warnings"]:
            print(f"  warning {warning['code']}: {warning['mod']}: {warning['message']}")
        for issue in plan["issues"]:
            print(f"  issue {issue['severity']} {issue['code']}: {issue['message']}")
    # With --json the document carries its own issues[]; a non-zero exit made the launcher show a truncated
    # JSON document as though it were an error message. `apply` still refuses plans with errors.
    return 0 if args.json or not any(issue["severity"] == "error" for issue in plan["issues"]) else 2


def cmd_apply(ctx: Context, args: argparse.Namespace) -> int:
    sync_drop_folder(ctx, args.profile)
    packages = scan_packages(ctx)
    plan = build_plan(ctx, args.profile, packages)
    if any(issue["severity"] == "error" for issue in plan["issues"]):
        print(describe_plan(plan), file=sys.stderr)
        raise ManagerError("refusing to activate a plan with errors", 2)
    if not plan["mods"] and read_profile(ctx, args.profile) and not args.allow_empty:
        print(describe_plan(plan), file=sys.stderr)
        raise ManagerError("every enabled mod was excluded; refusing to activate an empty plan (use --allow-empty)", 2)
    staging = activate(ctx, plan)
    print(f"activated {plan['planId'][:12]} ({len(plan['mods'])} mods) in {staging}")
    print(f"  env={len(plan['env'])} vfs={len(plan['vfs'])} textures={len(plan['textures'])}")
    return 0


def cmd_deactivate(ctx: Context, args: argparse.Namespace) -> int:
    deactivate(ctx, args.reason or "requested")
    print("deactivated; the next launch uses the unmodified game")
    return 0


def cmd_rollback(ctx: Context, args: argparse.Namespace) -> int:
    if args.journal:
        path = ctx.journal_dir / f"{args.journal}.json"
        if not path.is_file():
            raise ManagerError(f"no journal {path}", 4)
        journal = json.loads(path.read_text(encoding="utf-8"))
        restore(ctx, journal)
        journal["status"] = "rolled-back"
        journal["finishedAt"] = iso(now())
        atomic_write_json(path, journal)
        print(f"rolled back {args.journal}")
        return 0
    deactivate(ctx, "rollback")
    print("rolled back the active plan")
    return 0


def cmd_status(ctx: Context, args: argparse.Namespace) -> int:
    sync_drop_folder(ctx, DROP_PROFILE)
    state = current_state(ctx)
    fingerprint, changed = ensure_fingerprint(ctx)
    stale = bool(state.get("activePlan")) and state.get("fingerprintId") != fingerprint["fingerprintId"]
    if args.json:
        print(json.dumps({"state": state, "fingerprintId": fingerprint["fingerprintId"], "stale": stale}, indent=2))
        return 0
    print(f"active: {state.get('activePlan') or 'none'}{' (stale fingerprint)' if stale else ''}")
    if state.get("enabled"):
        for item in state["enabled"]:
            print(f"  {item['id']}@{item['version']}")
    print(f"fingerprint: {fingerprint['fingerprintId'][:12]} region={fingerprint['region']} edition={fingerprint['edition']}")
    print(f"fingerprint changed at this run: {changed}")
    return 0


def cmd_run(ctx: Context, args: argparse.Namespace) -> int:
    extra: dict[str, str] = {}
    for item in args.set:
        key, _, value = item.partition("=")
        extra[key] = value
    result = run_game(ctx, args.label or "", args.seconds, args.no_mods, extra)
    evidence = log_evidence(result)
    if args.json:
        result["evidence"] = evidence
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"run {result['seconds']}s exit={result['exitCode']} timeout={result['timedOut']}")
        print(f"  mods: {result['mods'] or 'none'}")
        for key, value in result["envApplied"].items():
            print(f"  {key}={value}")
        for key, value in result["envMods"].items():
            print(f"  mod {key}={value}")
        if "vfs" in result:
            print(f"  vfs stats: {result['vfs']}")
        for name, lines in evidence.get("lines", {}).get("stderr", {}).items():
            if name != "last" and lines:
                for line in lines[-3:]:
                    print(f"  {line}")
        print(f"  log: {result['stderr']}")
    return 0


def cmd_report(ctx: Context, args: argparse.Namespace) -> int:
    if not args.run:
        runs = sorted(ctx.runs_dir.iterdir(), key=lambda item: item.name)
        if not runs:
            raise ManagerError("no runs recorded", 4)
        run_dir = runs[-1]
    else:
        run_dir = ctx.runs_dir / args.run
        if not run_dir.is_dir():
            raise ManagerError(f"no run {run_dir}", 4)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    evidence = log_evidence(run)
    evidence["run"] = run
    atomic_write_json(ctx.reports_dir / f"{run_dir.name}.json", evidence)
    if args.json:
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
    else:
        print(f"report {run_dir.name}")
        if "vfs" in run:
            print(f"  vfs: overrides={run['vfs'].get('overrides')} lookups={run['vfs'].get('lookups')} hits={run['vfs'].get('hits')}")
        for name, lines in evidence.get("lines", {}).get("stderr", {}).items():
            if name == "last":
                continue
            for line in lines[-2:]:
                print(f"  {name}: {line}")
    return 0


def cmd_profiles(ctx: Context, args: argparse.Namespace) -> int:
    """Named mod sets: switch a whole selection at once, like a Minecraft mod profile."""
    allowed = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

    def rows() -> list[dict[str, Any]]:
        return [{"name": path.stem, "enabled": len(read_profile(ctx, path.stem))}
                for path in sorted(ctx.profiles_dir.glob("*.toml")) if path.is_file()]

    if args.create:
        name = args.create
        if not allowed.match(name):
            raise ManagerError(f"invalid profile name: {name!r}", 2)
        if profile_path(ctx, name).is_file():
            raise ManagerError(f"profile {name} already exists", 3)
        # A profile that was never used has no file on disk (e.g. a fresh install's "launcher").
        # read_profile() already returns an empty selection for that case; copying must not fail.
        write_profile(ctx, name, read_profile(ctx, args.source) if args.source else [])
    if args.delete:
        if args.delete == DROP_PROFILE:
            raise ManagerError(f"cannot delete the built-in {DROP_PROFILE} profile", 2)
        path = profile_path(ctx, args.delete)
        if not path.is_file():
            raise ManagerError(f"no profile {args.delete}", 2)
        path.unlink()
    result = rows()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for row in result:
            print(f"{row['name']:<24} {row['enabled']} enabled")
    return 0


def cmd_export(ctx: Context, args: argparse.Namespace) -> int:
    """Pack an installed mod into a shareable .zip that the drop folder can re-import."""
    packages = scan_packages(ctx)
    matches = [package for package in packages.values() if package.label == args.mod or package.id == args.mod]
    if not matches:
        raise ManagerError(f"{args.mod} is not installed", 2)
    package = sorted(matches, key=lambda item: version_key(item.version))[-1]
    out_dir = Path(args.out).resolve() if args.out else ctx.mods / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{package.label}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(package.path.rglob("*")):
            # The two marker files are manager-owned bookkeeping; a shared mod must not inherit them.
            if not item.is_file() or item.is_symlink() or item.name in (DROP_ERROR_FILE, DROP_WARN_FILE):
                continue
            archive.write(item, item.relative_to(package.path).as_posix())
    if args.json:
        print(json.dumps({"ok": True, "mod": package.label, "path": str(target)}, ensure_ascii=False))
    else:
        print(f"exported {package.label} -> {target}")
    return 0


def make_test_png(width: int, height: int) -> bytes:
    """Minimal RGB8 PNG for the self test (no Pillow dependency)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def cmd_selftest(ctx: Context, args: argparse.Namespace) -> int:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        results.append((name, condition, detail))

    workspace = ctx.repo / "data" / "_tmp" / "mod-selftest"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    mods = workspace / "mods"
    for folder in ("packages", "profiles", "plans", "staging", "hooks", "journal", "reports", "runs"):
        (mods / folder).mkdir(parents=True)
    local = Context(ctx.repo, mods)

    good = mods / "packages" / "selftest.good@1.0.0"
    (good / "textures").mkdir(parents=True)
    # PCSX2 name form <hash>-<pal>-<bits>: bits=0x42 -> TW=(bits>>6)&0xF=1, TH=(bits>>10)&0xF=0, so the image must be 2x1.
    png = good / "textures" / "0123abcd-00000000-00000042.png"
    png.write_bytes(make_test_png(2, 1))
    (good / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.good"\nname = "Self test"\nversion = "1.0.0"\ntype = "content"\npriority = 0\n'
        '[target]\ngame_id = "gow1"\n[textures]\ndir = "textures"\n', encoding="utf-8")
    broken = mods / "packages" / "selftest.broken@1.0.0"
    broken.mkdir(parents=True)
    (broken / "mod.toml").write_text('spec = 1\nid = "selftest.broken"\nversion = "1.0.0"\n[target]\ngame_id = "gow1"\n'
                                     '[vfs]\n"cdrom0:\\\\x" = "../escape"\n', encoding="utf-8")
    dead_env = mods / "packages" / "selftest.deadenv@1.0.0"
    dead_env.mkdir(parents=True)
    (dead_env / "mod.toml").write_text('spec = 1\nid = "selftest.deadenv"\nname = "Dead"\nversion = "1.0.0"\n'
                                       '[target]\ngame_id = "gow1"\n[env]\nGOW_MADE_UP = "1"\n', encoding="utf-8")

    packages = scan_packages(local)
    check("valid package passes", packages[("selftest.good", "1.0.0")].valid)
    check("path traversal is rejected", not packages[("selftest.broken", "1.0.0")].valid)
    check("dead env key is rejected", not packages[("selftest.deadenv", "1.0.0")].valid)

    write_profile(local, "selftest", ["selftest.good@1.0.0"])
    plan = build_plan(local, "selftest", packages)
    check("plan has one mod", len(plan["mods"]) == 1)
    check("texture is planned", len(plan["textures"]) == 1)
    staging = activate(local, plan)
    check("staging exists", (staging / "textures" / "0123abcd-00000000-00000042.png").is_file())
    check("state points at plan", current_state(local).get("activePlan") == plan["planId"])
    deactivate(local, "selftest")
    check("deactivate clears state", current_state(local).get("activePlan") is None)
    check("deactivate removes staging", not staging.exists())
    check("deactivate removes the hook files",
          not (local.hooks_dir / "plan.json").exists() and not (local.hooks_dir / "vfs-overrides.tsv").exists())
    check("deactivate keeps the activation journal intact",
          json.loads((local.journal_dir / f"{plan['planId']}.json").read_text(encoding="utf-8"))["status"] == "applied")

    journal_plan = {"planId": "rollbacktest", "profile": "selftest", "fingerprintId": "x", "mods": [], "env": {},
                    "vfs": {}, "textures": {}, "excluded": [], "conflicts": [], "warnings": [], "issues": []}
    activate(local, journal_plan)
    journal = json.loads((local.journal_dir / "rollbacktest.json").read_text(encoding="utf-8"))
    restore(local, {**journal, "previous": journal.get("previous", {})})
    check("rollback clears staging", not (local.staging_dir / "rollbacktest").exists())

    # --- regressions for the 2026-11-06 audit -------------------------------------------------------------
    def regression_pkg(folder: str, text: str) -> None:
        path = mods / "packages" / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / "mod.toml").write_text(text, encoding="utf-8")

    regression_pkg("selftest.env@1.0.0",
                   f'spec = {SCHEMA}\nid = "selftest.env"\nname = "Env"\nversion = "1.0.0"\n'
                   '[target]\ngame_id = "gow1"\n[env]\nGOW_SCALER = "2"\n')
    regression_pkg("selftest.invalid2@1.0.0",
                   f'spec = {SCHEMA}\nid = "selftest.invalid2"\nname = "Bad"\nversion = "1.0.0"\n'
                   '[target]\ngame_id = "gow1"\n[env]\nGOW_MADE_UP = "1"\n')
    regression_pkg("selftest.region@1.0.0",
                   f'spec = {SCHEMA}\nid = "selftest.region"\nname = "Region"\nversion = "1.0.0"\npriority = 100\n'
                   '[target]\ngame_id = "gow1"\nregions = ["europe"]\n[env]\nGOW_AUDIO = "1"\n')
    regression_pkg("selftest.rival@1.0.0",
                   f'spec = {SCHEMA}\nid = "selftest.rival"\nname = "Rival"\nversion = "1.0.0"\npriority = -100\n'
                   '[target]\ngame_id = "gow1"\n[conflicts]\nmods = ["selftest.region"]\n[env]\nGOW_SCALER = "1"\n')
    regression_pkg("selftest.conflicter@1.0.0",
                   f'spec = {SCHEMA}\nid = "selftest.conflicter"\nname = "Conflicter"\nversion = "1.0.0"\n'
                   '[target]\ngame_id = "gow1"\n[conflicts]\nmods = ["selftest.env"]\n[env]\nGOW_AUDIO = "0"\n')

    rp = scan_packages(local)
    write_profile(local, "regression", ["selftest.env@1.0.0", "selftest.invalid2@1.0.0",
                                        "selftest.region@1.0.0", "selftest.rival@1.0.0"])
    plan_r = build_plan(local, "regression", rp)
    labels = [item["id"] for item in plan_r["mods"]]
    excluded_r = {item["mod"]: item for item in plan_r["excluded"]}
    check("env plan keeps the {value,mod} shape", plan_r["env"].get("GOW_SCALER", {}).get("value") == "2")
    check("plan_hook_env flattens the env map",
          plan_hook_env(plan_r, mods / "staging").get("GOW_SCALER") == "2")
    check("invalid enabled mod is reported, not dropped",
          "selftest.invalid2@1.0.0" in excluded_r
          and bool(excluded_r["selftest.invalid2@1.0.0"].get("message"))
          and any(i["code"] == "mod.invalid" for i in plan_r["issues"]))
    check("a region-excluded mod cannot knock out a usable one",
          "selftest.region@1.0.0" in excluded_r and "selftest.rival" in labels,
          f"mods={labels} excluded={list(excluded_r)}")
    check("excluded entries carry the message the UI reads",
          all(item.get("message") for item in plan_r["excluded"]))
    check("TSV row injection is rejected", not GUEST_PATH_RE.fullmatch("cdrom0:\nEVIL\tC:/Windows/win.ini"))

    write_profile(local, "regression2", ["selftest.env@1.0.0", "selftest.conflicter@1.0.0"])
    plan_r2 = build_plan(local, "regression2", rp)
    check("conflicts carry a message and severity",
          bool(plan_r2["conflicts"]) and all(item.get("message") and item.get("severity")
                                            for item in plan_r2["conflicts"]))

    source = mods / "packages" / "selftest.good@1.0.0"
    before = (source / "mod.toml").read_text(encoding="utf-8")
    refused = False
    try:
        cmd_import(local, argparse.Namespace(source=str(source), replace=True))
    except ManagerError:
        refused = True
    check("import --replace refuses to overwrite its own source",
          refused and (source / "mod.toml").read_text(encoding="utf-8") == before)

    # A normal installation has no data/gow1/regional-builds.json (it is an optional isolated build).
    fake_repo = workspace / "repo"
    (fake_repo / "games" / "gow1").mkdir(parents=True)
    (fake_repo / "engine" / "patches").mkdir(parents=True)
    shutil.copy2(ctx.repo / "games" / "gow1" / "game.toml", fake_repo / "games" / "gow1" / "game.toml")
    fake_ctx = Context(fake_repo, workspace / "mods-no-builds")
    fake_fp = gather_fingerprint(fake_ctx)
    check("fingerprint works without regional-builds.json",
          fake_fp["gameId"] == "gow1" and bool(fake_fp["elfCrc"]) and bool(fake_fp["textSha1"]))
    usa_pkg = fake_ctx.packages_dir / "selftest.usa@1.0.0"
    usa_pkg.mkdir(parents=True)
    (usa_pkg / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.usa"\nname = "USA"\nversion = "1.0.0"\n'
        '[target]\ngame_id = "gow1"\nregions = ["usa"]\n[env]\nGOW_SCALER = "1"\n', encoding="utf-8")
    write_profile(fake_ctx, "launcher", ["selftest.usa@1.0.0"])
    usa_plan = build_plan(fake_ctx, "launcher", scan_packages(fake_ctx))
    check("edition id is a valid region target without regional builds",
          [item["id"] for item in usa_plan["mods"]] == ["selftest.usa"])

    # --- drop folder (zero-config, Minecraft-style install) ---------------------------------------------------
    zip_entry = local.drop_dir / "Drop Test v2.0.zip"
    with zipfile.ZipFile(zip_entry, "w") as archive:
        archive.writestr("DropTest/0123abcd-00000000-00000042.png", make_test_png(2, 1))
        archive.writestr("DropTest/env.toml", 'GOW_SCALER = "3"\n')
    drop_label = "drop-test@2.0"
    first = sync_drop_folder(local, "selftest-drop")
    check("drop zip installs and enables a generated manifest",
          drop_label in first["installed"]
          and (local.packages_dir / drop_label / "mod.toml").is_file()
          and drop_label in read_profile(local, "selftest-drop"))
    drop_pkg = scan_packages(local).get(("drop-test", "2.0"))
    check("generated manifest passes validation",
          drop_pkg is not None and drop_pkg.valid
          and "texture_pack" in drop_pkg.capabilities and "env" in drop_pkg.capabilities)
    second = sync_drop_folder(local, "selftest-drop")
    check("drop sync is idempotent", not second["installed"] and not second["removed"])
    write_profile(local, "selftest-drop", [])  # the player turned the mod off
    sync_drop_folder(local, "selftest-drop")
    check("a disabled drop mod is not silently re-enabled",
          drop_label not in read_profile(local, "selftest-drop"))
    zip_entry.unlink()
    removed = sync_drop_folder(local, "selftest-drop")
    check("deleting the dropped file uninstalls the mod",
          drop_label in removed["removed"] and not (local.packages_dir / drop_label).exists())

    slipped = local.drop_dir / "evil.zip"
    with zipfile.ZipFile(slipped, "w") as archive:
        archive.writestr("../escape.png", b"x")
    sync_drop_folder(local, "selftest-drop")
    evil = scan_packages(local).get(("evil", "1.0.0"))
    check("zip-slip is refused with a visible reason",
          evil is not None and not evil.valid
          and any(issue.code == "drop.install" for issue in evil.issues))

    # --- capability boundaries: what a mod can and cannot change -----------------------------------------------
    sound_zip = local.drop_dir / "Sound Pack.zip"
    with zipfile.ZipFile(sound_zip, "w") as archive:
        archive.writestr("Sound/MUSIC.VAG", b"vag")
        archive.writestr("Sound/IOP_MOD/LIBSD.IRX", b"irx")
        archive.writestr("Sound/env.toml", 'TOBIICHI_TRUCOS = "inmortal"\n')
    sync_drop_folder(local, "selftest-drop")
    sound = scan_packages(local).get(("sound-pack", "1.0.0"))
    check("stand-alone audio/IRX files are mapped without a manifest",
          sound is not None and sound.valid and "audio" in sound.capabilities
          and any(key.endswith("libsd.irx") for key in sound.vfs))
    check("compiled-in gameplay switches are exposed to mods",
          sound is not None and "gameplay" in sound.capabilities
          and sound.env.get("TOBIICHI_TRUCOS") == "inmortal")
    check("generated audio mods state the PAK limitation",
          sound is not None and any(issue.code == "drop.notice" for issue in sound.issues))

    fake_zip = local.drop_dir / "Fake Code Mod.zip"
    with zipfile.ZipFile(fake_zip, "w") as archive:
        archive.writestr("Fake/function.toml", 'x = 1\n')
    sync_drop_folder(local, "selftest-drop")
    fake = scan_packages(local).get(("fake-code-mod", "1.0.0"))
    check("code mods are refused with an actionable reason",
          fake is not None and not fake.valid
          and any(issue.code == "drop.install" and "cannot load code" in issue.message for issue in fake.issues))
    code_dir = local.packages_dir / "selftest.code@1.0.0"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.code"\nname = "Code"\nversion = "1.0.0"\ntype = "code"\n'
        '[target]\ngame_id = "gow1"\n[env]\nGOW_SCALER = "1"\n', encoding="utf-8")
    check("code/mixed manifest types stay unsupported", not validate_package(local, code_dir).valid)

    # --- named profiles, export and optional metadata ----------------------------------------------------------
    import contextlib
    import io

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        cmd_profiles(local, argparse.Namespace(create="hd-textures", source="selftest-drop", delete=None, json=True))
        cmd_export(local, argparse.Namespace(mod="selftest.good@1.0.0", out=None, json=True))
    documentos = [line for line in captured.getvalue().splitlines() if line.startswith(("[", "{"))]
    profile_rows = json.loads(documentos[0])
    export_info = json.loads(documentos[1])
    check("profiles can be created and listed", any(row["name"] == "hd-textures" for row in profile_rows))
    check("a new profile copies another profile's selection",
          read_profile(local, "hd-textures") == read_profile(local, "selftest-drop"))
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_profiles(local, argparse.Namespace(create="empty-set", source="never-used-profile", delete=None, json=True))
    check("copying from a profile that has no file yet yields an empty set",
          profile_path(local, "empty-set").is_file() and read_profile(local, "empty-set") == [])
    with zipfile.ZipFile(export_info["path"]) as exported_zip:
        check("export produces a re-importable zip",
              "mod.toml" in exported_zip.namelist()
              and not any(name.startswith("gow-install-") for name in exported_zip.namelist()))
    with contextlib.redirect_stdout(io.StringIO()):
        cmd_profiles(local, argparse.Namespace(create=None, source=None, delete="hd-textures", json=False))
    check("profiles can be deleted", not profile_path(local, "hd-textures").is_file())

    original_manifest = (good / "mod.toml").read_text(encoding="utf-8")
    # Top-level keys must come BEFORE the first [table], or TOML puts them inside that table.
    (good / "mod.toml").write_text('description = "Test description"\nauthor = "Tester"\n' + original_manifest,
                                   encoding="utf-8")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        cmd_list(local, argparse.Namespace(profile="launcher", json=True))
    good_row = next(row for row in json.loads(captured.getvalue()) if row["mod"] == "selftest.good@1.0.0")
    check("optional mod metadata reaches the UI",
          good_row["description"] == "Test description" and good_row["author"] == "Tester")

    # --- visual effects and declarative data patches ----------------------------------------------------------
    fx = local.packages_dir / "selftest.fx@1.0.0"
    fx.mkdir(parents=True, exist_ok=True)
    (fx / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.fx"\nname = "FX"\nversion = "1.0.0"\n'
        '[target]\ngame_id = "gow1"\n[effects]\npresets = ["sharp", "fxaa"]\n'
        '[env]\nGOW_SHARPEN = "0.2"\n', encoding="utf-8")
    fx_pkg = validate_package(local, fx)
    check("effect presets expand to real runtime keys",
          fx_pkg.valid and fx_pkg.env.get("GOW_SCALER") == "sharp"
          and fx_pkg.env.get("TOBIICHI_FXAA") == "1" and fx_pkg.env.get("GOW_SHARPEN") == "0.2"
          and "effects" in fx_pkg.capabilities)

    dp = local.packages_dir / "selftest.patch@1.0.0"
    dp.mkdir(parents=True, exist_ok=True)
    (dp / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.patch"\nname = "Patch"\nversion = "1.0.0"\n'
        '[target]\ngame_id = "gow1"\n'
        '[[patches]]\naddress = "0x00302CC0"\nwidth = 4\nvalue = "0x64"\n'
        'mask = "0xFFFFFFFF"\nexpected = "0"\nonce = true\n', encoding="utf-8")
    dp_pkg = validate_package(local, dp)
    check("declarative data patches are validated",
          dp_pkg.valid and len(dp_pkg.patches) == 1 and "data_patch" in dp_pkg.capabilities)

    bad_dp = local.packages_dir / "selftest.badpatch@1.0.0"
    bad_dp.mkdir(parents=True, exist_ok=True)
    (bad_dp / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.badpatch"\nname = "Bad patch"\nversion = "1.0.0"\n'
        '[target]\ngame_id = "gow1"\n[[patches]]\naddress = "0x00000101"\nvalue = "1"\n',
        encoding="utf-8")
    check("out-of-range / misaligned patch addresses are rejected",
          not validate_package(local, bad_dp).valid)

    wrong = local.packages_dir / "selftest.wrongelf@1.0.0"
    wrong.mkdir(parents=True, exist_ok=True)
    (wrong / "mod.toml").write_text(
        f'spec = {SCHEMA}\nid = "selftest.wrongelf"\nname = "Wrong ELF"\nversion = "1.0.0"\n'
        '[target]\ngame_id = "gow1"\n[[patches]]\naddress = "0x00302CC0"\nvalue = "1"\n'
        'text_sha1 = "deadbeefdeadbeef"\n', encoding="utf-8")
    write_profile(local, "selftest-abilities", ["selftest.patch@1.0.0"])
    plan_dp = build_plan(local, "selftest-abilities", scan_packages(local))
    check("plan carries data patches and marks requiresRebuild",
          len(plan_dp["patches"]) == 1 and plan_dp["requiresRebuild"] is True)
    activate(local, plan_dp)
    tsv = (local.hooks_dir / "data-patches.tsv").read_text(encoding="utf-8")
    check("hooks TSV has one numeric patch row", "0x00302CC0\t4\t0x00000064" in tsv)
    deactivate(local, "selftest-abilities")
    check("deactivate removes the patch table", not (local.hooks_dir / "data-patches.tsv").exists())

    write_profile(local, "selftest-wrong", ["selftest.wrongelf@1.0.0"])
    plan_wrong = build_plan(local, "selftest-wrong", scan_packages(local))
    check("a patch bound to another ELF .text is refused",
          any(issue["code"] == "patches.elf" for issue in plan_wrong["issues"]))

    fxzip = local.drop_dir / "FX Preset.zip"
    with zipfile.ZipFile(fxzip, "w") as archive:
        archive.writestr("FX/effects.toml", 'presets = ["retro"]\n')
    sync_drop_folder(local, "selftest-abilities")
    fx_drop = scan_packages(local).get(("fx-preset", "1.0.0"))
    check("zero-config effects.toml becomes a visual mod",
          fx_drop is not None and fx_drop.valid and "effects" in fx_drop.capabilities)

    failures = [item for item in results if not item[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}{f' ({detail})' if detail else ''}")
    shutil.rmtree(workspace, ignore_errors=True)
    return 0 if not failures else 2


def main(argv: list[str] | None = None) -> int:
    default_repo = Path(os.environ.get("GOW_REPO_ROOT") or Path(__file__).resolve().parents[2])
    default_mods = Path(os.environ.get("GOW_MODS_DIR") or default_repo / "data" / "mods")
    parser = argparse.ArgumentParser(description="God of War native port mod manager")
    parser.add_argument("--repo", default=str(default_repo), help="checkout root (defaults to GOW_REPO_ROOT or the script's checkout)")
    parser.add_argument("--mods-dir", default=str(default_mods), help="mod data folder (defaults to GOW_MODS_DIR or data/mods)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=help_text)
        child.set_defaults(func=func)
        return child

    def json_flag(child: argparse.ArgumentParser) -> None:
        child.add_argument("--json", action="store_true", help="machine-readable output")

    p = add("fingerprint", cmd_fingerprint, "print and refresh the game identity the plans are bound to")
    json_flag(p)

    p = add("list", cmd_list, "list installed mods")
    p.add_argument("-p", "--profile", default="default")
    json_flag(p)

    p = add("validate", cmd_validate, "validate installed packages")
    p.add_argument("mod", nargs="?", help="id or id@version (default: all)")
    json_flag(p)

    p = add("import", cmd_import, "install a mod package folder")
    p.add_argument("source")
    p.add_argument("--replace", action="store_true")

    for name, enable in (("enable", True), ("disable", False)):
        p = add(name, lambda ctx, args, enable=enable: _change_enabled(ctx, args, enable),
                f"{'add mods to' if enable else 'remove mods from'} the profile")
        p.add_argument("mods", nargs="+")
        p.add_argument("-p", "--profile", default="default")

    p = add("plan", cmd_plan, "compute and store the plan without touching the game")
    p.add_argument("-p", "--profile", default="default")
    json_flag(p)

    p = add("apply", cmd_apply, "activate the plan transactionally")
    p.add_argument("-p", "--profile", default="default")
    p.add_argument("--allow-empty", action="store_true", help="allow a profile whose mods were all excluded")

    p = add("deactivate", cmd_deactivate, "restore the unmodified game")
    p.add_argument("--reason", default="")

    p = add("rollback", cmd_rollback, "roll back the active plan or a journal")
    p.add_argument("journal", nargs="?", help="journal id (default: the active plan)")

    p = add("status", cmd_status, "show the active plan and fingerprint")
    json_flag(p)

    p = add("run", cmd_run, "launch the runner with the active plan")
    p.add_argument("--label", default="")
    p.add_argument("--seconds", type=int, default=0)
    p.add_argument("--no-mods", action="store_true", help="clean baseline: no mod environment at all")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="test-harness setting, applied last")
    json_flag(p)

    p = add("report", cmd_report, "summarise a run's runtime evidence")
    p.add_argument("run", nargs="?", help="run folder name (default: latest)")
    json_flag(p)

    p = add("profiles", cmd_profiles, "list, create or delete named mod sets")
    p.add_argument("--create", metavar="NAME", help="create a new profile")
    p.add_argument("--from", dest="source", metavar="NAME", help="copy the enabled mods from another profile")
    p.add_argument("--delete", metavar="NAME", help="delete a profile")
    json_flag(p)

    p = add("export", cmd_export, "pack an installed mod into a shareable .zip")
    p.add_argument("mod", help="id or id@version")
    p.add_argument("--out", metavar="DIR", help="output folder (default: data/mods/exports)")
    json_flag(p)

    p = add("selftest", cmd_selftest, "run the manager's isolated checks")

    args = parser.parse_args(argv)
    ctx = Context(Path(args.repo).resolve(), Path(args.mods_dir).resolve())
    try:
        return args.func(ctx, args)
    except ManagerError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
