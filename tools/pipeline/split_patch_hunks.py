"""Split the hunks of a patch file into two patches, by content marker.

A rebuilt patch can carry the changes of the patches that come after it: when
the stack is regenerated against the working tree, a patch that touches a file
another patch also touches takes the whole file with it. The hunks of the
later change then have to be moved back into their own patch.

This script moves the hunks whose added or removed lines mention one of the
markers into a second patch file:

    python tools/pipeline/split_patch_hunks.py <patch> <marker> <out.patch> [more markers...]

The hunks that stay keep their order; the ones that move keep theirs. Both
files are written with LF endings (the runtime checks out with LF, see its
.gitattributes).

Usage example (move the "patch 79" hunks of 78-vu1-acc-reg.patch into a patch
of their own):

    python tools/pipeline/split_patch_hunks.py \\
        engine/patches/78-vu1-acc-reg.patch "patch 79" engine/patches/79-vu1-vf-forward.patch
"""
import difflib
import sys
from pathlib import Path


def split_sections(text):
    """The patch as a list of (header, lines) sections, one per file."""
    lines = text.split("\n")
    sections = []
    current = []
    for line in lines:
        if line.startswith("--- ") and current:
            # a new file section starts here
            sections.append(current)
            current = [line]
        elif line.startswith("--- ") and not current:
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)
    return sections


def split_hunks(lines):
    """The lines of a file section as (head, hunks) with head the header lines."""
    head = []
    hunks = []
    current = None
    for line in lines:
        if line.startswith("@@"):
            if current is not None:
                hunks.append(current)
            current = [line]
        elif current is None:
            head.append(line)
        else:
            current.append(line)
    if current is not None:
        hunks.append(current)
    return head, hunks


def hunk_marker(hunk, markers):
    """The marker of the hunk, or None when it mentions none of them."""
    found = []
    for line in hunk:
        if not line or line[0] not in " +-":
            continue
        for marker in markers:
            if marker in line and marker not in found:
                found.append(marker)
    return found


def render(head, hunks):
    out = list(head)
    for hunk in hunks:
        out.extend(hunk)
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    source = Path(argv[1])
    markers = argv[2].split(",")
    out = Path(argv[3])
    # The hunks that stay in the source patch are written back to it, so the
    # source file does not carry the hunks that moved away.
    write_back = len(argv) > 4 and argv[4] == "--write-back"
    text = source.read_bytes().decode("utf-8", errors="surrogateescape").replace("\r\n", "\n")

    kept_sections = []
    moved_sections = []
    moved_count = 0
    for section in split_sections(text):
        head, hunks = split_hunks(section)
        if not hunks:
            kept_sections.append("\n".join(section).rstrip("\n") + "\n")
            continue
        kept = []
        moved = []
        for hunk in hunks:
            if hunk_marker(hunk, markers):
                moved.append(hunk)
                moved_count += 1
            else:
                kept.append(hunk)
        if not moved:
            kept_sections.append("\n".join(section).rstrip("\n") + "\n")
            continue
        # the file header of a section without hunks would leave a broken patch
        kept_sections.append(render(head, kept))
        moved_sections.append(render(head, moved))

    if not moved_count:
        print(f"[split] {source.name}: no hunk mentions {markers}")
        return 1
    out.write_text("".join(moved_sections), encoding="utf-8", newline="")
    if write_back:
        source.write_text("".join(kept_sections), encoding="utf-8", newline="")
    print(f"[split] {source.name}: {moved_count} hunk(s) moved to {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
