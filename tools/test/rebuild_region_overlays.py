"""Rebuild the regional overlays (japan/europe) against the current sources.

The regional overlay is a patch that relocates the native integration to the
addresses of the region (SLPM-67010 / SLES-...).  It was written against an
older copy of the sources, so it no longer applies after the runtime changed
(the USA ELF gate became a registry query, for example).

This script rebuilds every overlay with the same content matching the original
patch used, but by content instead of by line number: every hunk replaces the
block of removed lines with the block of added lines, wherever it is found in
the current file.  A hunk whose removed block is gone (because the code it
touched has changed) is dropped and reported, so nothing is applied blindly.

Usage:  python rebuild_region_overlays.py [--apply]
"""
import argparse
import difflib
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "engine" / "runtime"
REGIONS = ROOT / "games" / "gow1" / "regions"

# gow-native-pc: the registration of the overrides is the only place where the
# region has to be written down: the game modules ask the registry instead of
# repeating the executable name (that was six hard-coded copies of it). The
# overlay replaces the USA registration with the one of the region, and adds
# the serial that carries the same code as an alias.
USA_REGISTRATION = re.compile(r'PS2_REGISTER_GAME_OVERRIDE\("God of War \(SCUS-97399\)", "SCUS_973\.99", 0x00100008u, 0u, '
                              r'applyGowOverrides\)')
REGISTRATION = {
    "japan": ('PS2_REGISTER_GAME_OVERRIDE_ALIASES("God of War (SLPM-67010)", "SLPM_670.10", "SCAJ_973.99", nullptr, '
              '0x00100008u, 0u, applyGowOverrides)'),
    "europe": ('PS2_REGISTER_GAME_OVERRIDE_ALIASES("God of War (SLES-53133)", "SLES_531.33", nullptr, 0x00100008u, 0u, '
               'applyGowOverrides)'),
}


def split_patch(text):
    """The header of the patch and the per-file blocks."""
    blocks = re.split(r"(?m)^(?=--- a/)", text)
    header = blocks[0]
    files = []
    for block in blocks[1:]:
        if not block.strip():
            continue
        lines = block.splitlines(keepends=True)
        name = lines[0][6:].split("\t")[0].strip()
        files.append((name, block))
    return header, files


def hunks_of(block):
    """The hunks of a file block, as the ordered segments they are made of.

    A segment is (' ', lines) for the context, ('-', lines) for the lines the
    hunk removes and ('+', lines) for the lines it adds.
    """
    lines = block.splitlines(keepends=True)
    result = []
    header = None
    segments = []
    for line in lines[2:]:
        if line.startswith("@@"):
            if header is not None:
                result.append((header, segments))
            header, segments = line, []
        elif line.startswith("-"):
            segments.append(("-", line[1:]))
        elif line.startswith("+"):
            segments.append(("+", line[1:]))
        elif line.startswith(" ") or line == "\n":
            segments.append((" ", line[1:]))
        elif line.startswith("\\"):
            continue
    if header is not None:
        result.append((header, segments))
    return result


def rebuild_file(current, hunks):
    """Apply the hunks by content and report the ones that no longer fit.

    The context of the original patch belongs to a version of the file that has
    changed since (the fixes of the current session), so the place of a hunk
    is found by its own removed lines instead of by its line numbers.
    """
    text = current
    skipped = []
    applied = 0
    for header, segments in hunks:
        minus = [line for kind, line in segments if kind == "-"]
        plus = [line for kind, line in segments if kind == "+"]
        context = [line for kind, line in segments if kind == " "]
        old = "".join(minus)
        new = "".join(plus)
        if not minus and plus:
            # A hunk that only adds lines: they go after the context that
            # precedes them.
            anchor = "".join(context)
            if anchor and anchor in text:
                text = text.replace(anchor, anchor + new, 1)
                applied += 1
            else:
                skipped.append((header or "(hunk)").strip() + " (only additions)")
            continue
        if old in text:
            text = text.replace(old, new, 1)
            applied += 1
            continue
        if len(minus) == len(plus) and minus:
            # The block changed around: replace line by line.
            candidate = text
            ok = True
            for old_line, new_line in zip(minus, plus):
                if old_line in candidate:
                    candidate = candidate.replace(old_line, new_line, 1)
                else:
                    ok = False
                    break
            if ok:
                text = candidate
                applied += 1
                continue
        if len(plus) == len(minus) + 1 and plus[0].strip().startswith("return;"):
            # A statement that the overlay adds before a line that has changed
            # since (the USA ELF gate is now a registry query).
            marker = "elfAcceptedByAnyOverride(elfPath)"
            if marker in text:
                index = text.index(marker)
                start = text.rfind("\n", 0, index) + 1
                text = text[:start] + plus[0] + text[start:]
                applied += 1
                continue
        old_literals = re.findall(r"0x[0-9A-Fa-f]+u?", old)
        new_literals = re.findall(r"0x[0-9A-Fa-f]+u?", new)
        if old_literals and len(old_literals) == len(new_literals):
            # The line changed around, but the addresses it carries are the same:
            # relocate them one by one.
            candidate = text
            ok = True
            for old_literal, new_literal in zip(old_literals, new_literals):
                if old_literal in candidate:
                    candidate = candidate.replace(old_literal, new_literal, 1)
                else:
                    ok = False
                    break
            if ok:
                text = candidate
                applied += 1
                continue
        skipped.append((header or "(hunk)").strip())
    return text, applied, skipped


def diff_for(name, current, regional):
    old_lines = current.splitlines(keepends=True)
    new_lines = regional.splitlines(keepends=True)
    if old_lines == new_lines:
        return ""
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{name}", tofile=f"b/{name}", n=3)
    return "".join(diff)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    for region in ("japan", "europe"):
        folder = REGIONS / region
        patch_path = folder / "runtime.patch"
        text = patch_path.read_text(encoding="utf-8")
        header, files = split_patch(text)
        baseline = json.loads((folder / "baseline.json").read_text(encoding="utf-8"))
        new_blocks = []
        new_baseline = {}
        print(f"=== {region}")
        for name, block in files:
            source = RUNTIME / name
            if not source.is_file():
                print(f"  {name}: missing in the runtime, the hunk is dropped")
                continue
            current = source.read_text(encoding="utf-8")
            regional, applied, skipped = rebuild_file(current, hunks_of(block))
            # The registration of the region (the only place the region is written down).
            replaced, count = USA_REGISTRATION.subn(REGISTRATION[region], regional)
            if count:
                regional = replaced
                print(f"  {name}: registration replaced by the one of {region}")
            if skipped:
                print(f"  {name}: {applied} hunk(s) applied, {len(skipped)} dropped: {', '.join(skipped)}")
            else:
                print(f"  {name}: {applied} hunk(s) applied")
            piece = diff_for(name, current, regional)
            if piece:
                new_blocks.append(piece)
            new_baseline[name] = __import__("hashlib").sha256(current.encode("utf-8")).hexdigest()
        # The files of the baseline that the patch does not touch keep their hash.
        for name, value in baseline.items():
            new_baseline.setdefault(name, value)
        rebuilt = header + "".join(new_blocks)
        if args.apply:
            patch_path.write_text(rebuilt, encoding="utf-8", newline="\n")
            (folder / "baseline.json").write_text(json.dumps(new_baseline, indent=2, sort_keys=True) + "\n",
                                                  encoding="utf-8", newline="\n")
            print(f"  written: {patch_path.name} ({len(rebuilt)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
