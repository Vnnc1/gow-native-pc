"""Rebuild the runtime patch stack so that applying it reproduces the working tree.

The pipeline (tools/pipeline/modules/runtime.ps1) clones engine/runtime at the
commit pinned in engine/runtime.toml and applies engine/patches/*.patch in file
name order.  It then checks that the resulting tree is exactly the working tree
of engine/runtime; if it is not, the stage fails.

Some patches in the stack no longer apply (their context is older than the
current chain), so the stage never completes.  This script rewrites the stack
with the working tree as the truth:

  * every patch that applies is kept as it is;
  * every patch that does not apply is regenerated against the current state of
    the chain, using the working tree content of the files it touches;
  * the result is verified: applying the new stack to the pinned commit must
    reproduce the working tree byte for byte.

Usage:  python rebuild_patch_stack.py [--apply] [--work DIR]
"""
import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "engine" / "runtime"
PATCHES = ROOT / "engine" / "patches"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def pinned_commit():
    import re
    text = (ROOT / "engine" / "runtime.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^commit\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("no commit in engine/runtime.toml")
    return match.group(1)


def patch_order():
    # The pipeline sorts the full paths with StringComparer.Ordinal; all the
    # patches live in the same folder, so this is the file name in ordinal order.
    return sorted(PATCHES.glob("*.patch"), key=lambda p: str(p).encode("utf-8"))


def touched_files(text):
    files = []
    for line in text.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:].split("\t")[0].strip())
        elif line.startswith("--- a/"):
            files.append(line[6:].split("\t")[0].strip())
    seen = []
    for name in files:
        if name and name not in seen:
            seen.append(name)
    return seen


def has_hunks(text):
    """True when the patch carries at least one file diff.

    git apply refuses an input without a diff ("No valid patches in input")
    unless --allow-empty is given, so the stack must not hold such a file
    unnoticed.
    """
    lines = text.splitlines()
    if any(line.startswith("diff --git ") for line in lines):
        return True
    # the traditional format: "--- a/path" followed by "+++ b/path"
    return any(line.startswith("--- a/") for line in lines) and \
        any(line.startswith("+++ b/") for line in lines)


def git_view(path):
    """The lines of a file as git sees them in the work tree.

    The runtime checks out with LF (see its .gitattributes: *.cpp text eol=lf),
    so a patch built from CRLF lines does not apply. The lines are normalized
    to LF here for that reason.
    """
    if not path.is_file():
        return []
    text = path.read_bytes().decode("utf-8", errors="surrogateescape")
    text = text.replace("\r\n", "\n")
    return text.splitlines(keepends=True)


def make_patch(paths, work, target):
    """Unified diff of work -> target for the given relative paths."""
    chunks = []
    for rel in paths:
        old_lines = git_view(work / rel)
        new_lines = git_view(target / rel)
        if old_lines == new_lines:
            continue
        old_name = f"a/{rel}" if (work / rel).is_file() else "/dev/null"
        new_name = f"b/{rel}" if (target / rel).is_file() else "/dev/null"
        diff = difflib.unified_diff(old_lines, new_lines, fromfile=old_name, tofile=new_name, n=3)
        chunks.append("".join(diff))
    return "".join(chunks)

def apply_text(clone, text, check=False):
    """Apply a patch written to a file.

    The patch goes through a file on purpose: on Windows a pipe would rewrite
    the LF line endings of the patch as CRLF and git would not match the
    context any more (the files of the runtime are LF, see .gitattributes).
    """
    with tempfile.NamedTemporaryFile("wb", suffix=".patch", delete=False) as handle:
        handle.write(text.encode("utf-8", errors="surrogateescape"))
        path = handle.name
    try:
        command = ["git", "-C", str(clone), "apply", "-p1", "--whitespace=nowarn"]
        if check:
            command.append("--check")
        command.append(path)
        return subprocess.run(command, capture_output=True, text=True)
    finally:
        os.unlink(path)


def tree_of(repo, use_temp_index=True):
    """The tree of the work tree (tracked content plus the untracked files).

    The index is written to a temporary file so the repository of the user is
    not touched. The caller removes the temporary index.
    """
    env = dict(os.environ)
    if use_temp_index:
        handle, index = tempfile.mkstemp(prefix="gow-index-")
        os.close(handle)
        os.unlink(index)
        env["GIT_INDEX_FILE"] = index
    else:
        index = None
    subprocess.run(["git", "-C", str(repo), "read-tree", "HEAD"], env=env, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], env=env, capture_output=True)
    result = subprocess.run(["git", "-C", str(repo), "write-tree"], env=env, capture_output=True, text=True)
    return result.stdout.strip(), index


def tree_entries(repo, index):
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = index
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "-s"], env=env, capture_output=True, text=True)
    entries = {}
    for line in result.stdout.splitlines():
        meta, path = line.split("\t", 1)
        mode, blob, _stage = meta.split()
        entries[path] = (mode, blob)
    return entries


def list_files(root):
    """The files of a directory tree, relative and with forward slashes."""
    result = []
    for path in root.rglob("*"):
        if path.is_file():
            result.append(path.relative_to(root).as_posix())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the rebuilt patches over the originals")
    parser.add_argument("--work", default=None, help="scratch directory (a temporary one by default)")
    args = parser.parse_args()

    commit = pinned_commit()
    scratch = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="gow-stack-"))
    clone = scratch / "rt"
    if clone.exists():
        shutil.rmtree(clone)
    scratch.mkdir(parents=True, exist_ok=True)
    print(f"[stack] scratch: {scratch}")
    print(f"[stack] cloning {RUNTIME} at {commit[:12]}")
    git("clone", "--quiet", "--no-hardlinks", "--no-checkout", str(RUNTIME), str(clone))
    git("-C", str(clone), "checkout", "--quiet", commit)

    # The working tree as the truth: the tracked content plus the untracked
    # files that are not ignored.
    truth = scratch / "truth"
    if truth.exists():
        shutil.rmtree(truth)
    truth.mkdir()
    # A leftover of a tool run that can not be deleted from here (the sandbox forbids removing files outside the
    # workspace): it is not part of the runtime and must not end up in the patch stack.
    junk = {"PS2Recomp/ps2xRuntime/src/lib/gs/_probe.txt"}
    tracked = git("-C", str(RUNTIME), "ls-files", "-z").stdout.split("\0")
    for name in tracked:
        if not name or name in junk:
            continue
        src = RUNTIME / name
        if not src.is_file():
            continue
        dst = truth / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    untracked = git("-C", str(RUNTIME), "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0")
    for name in untracked:
        if not name or name in junk:
            continue
        src = RUNTIME / name
        if not src.is_file():
            continue
        dst = truth / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    print(f"[stack] truth: {len(tracked) + len(untracked)} files")

    rebuilt = {}
    regenerated = []
    dropped = []
    for patch in patch_order():
        # The patches of the stack must have the same line endings as the files
        # they touch (LF, see the .gitattributes of the runtime): a patch with
        # CRLF does not apply.
        original = patch.read_bytes().decode("utf-8", errors="surrogateescape")
        normalized = original.replace("\r\n", "\n")
        if not has_hunks(normalized):
            # The patch carries no file diff (an empty file, or a note). git
            # apply rejects such an input unless --allow-empty is given, so it
            # is kept as it is and reported: the pipeline skips it.
            rebuilt[patch.name] = normalized
            dropped.append(patch.name)
            print(f"[stack] {patch.name}: no file diff (kept as it is)")
            continue
        result = apply_text(clone, normalized)
        if result.returncode == 0:
            rebuilt[patch.name] = normalized
            continue
        # The patch does not apply: rebuild it against the current state of
        # the chain, with the working tree as the target of the files it touches.
        files = touched_files(original)
        text = make_patch(files, clone, truth)
        if not text.strip():
            # The files are already in the working tree state: the patch has
            # nothing left to say (its content is in the tree already).
            # The original text is kept (an empty patch file would make the
            # pipeline fail on "No valid patches in input"); it is reported so
            # that the file can be retired by hand.
            rebuilt[patch.name] = normalized
            dropped.append(patch.name)
            print(f"[stack] {patch.name}: its content is already in the tree (original text kept)")
            continue
        probe = apply_text(clone, text, check=True)
        if probe.returncode != 0:
            print(f"[stack] ERROR {patch.name}: the rebuilt patch does not apply:\n{probe.stderr}")
            return 1
        rebuilt[patch.name] = text
        regenerated.append(patch.name)
        apply_text(clone, text)
        print(f"[stack] regenerated {patch.name} ({len(files)} files)")

    # The chain now holds the patches; the working tree is the truth. What is
    # left is written as the last patch of the stack, so the chain reproduces
    # the working tree exactly (that is what the pipeline checks).
    final_name = "zz-workspace-final-state.patch"
    final_lines = [
        "# gow-native-pc: final state of the runtime working tree.\n",
        "#\n",
        "# The patches above carry the history of the runtime; this one carries the\n",
        "# state of the working tree that the pipeline expects to find after the stack\n",
        "# is applied (the fixes of the current session and the drift of the patches\n",
        "# that no longer applied). It is generated by tools/pipeline/rebuild_patch_stack.py.\n",
    ]
    # The header of the patch that is already on disk is kept: it describes what
    # the patch is for, and the stack is read by people as well as by git.
    existing_final = PATCHES / final_name
    if existing_final.is_file():
        previous = existing_final.read_bytes().decode("utf-8", errors="surrogateescape").replace("\r\n", "\n")
        marker = previous.find("diff --git ")
        if marker > 0 and not previous[:marker].startswith("# gow-native-pc: final state"):
            final_lines = [previous[:marker].rstrip("\n") + "\n"]
    final_patch = ""
    changed = 0
    # Only the files of the working tree are compared: the clone also holds the
    # .git folder, which is not part of the tree.
    for relative in sorted(list_files(truth)):
        chain_file = clone / relative
        truth_file = truth / relative
        old = git_view(chain_file)
        new = git_view(truth_file)
        if old == new:
            continue
        changed += 1
        old_name = f"a/{relative}" if chain_file.is_file() else "/dev/null"
        new_name = f"b/{relative}" if truth_file.is_file() else "/dev/null"
        final_patch += "".join(difflib.unified_diff(old, new, fromfile=old_name, tofile=new_name, n=3))
    rebuilt[final_name] = "".join(final_lines) + final_patch
    print(f"[stack] final patch: {changed} file(s)")
    if final_patch:
        probe = apply_text(clone, rebuilt[final_name], check=True)
        if probe.returncode != 0:
            print(f"[stack] ERROR: the final patch does not apply:\n{probe.stderr}")
            return 1
        apply_text(clone, rebuilt[final_name])

    # Verify: the tree of the chain must equal the working tree.
    chain_tree, chain_index = tree_of(clone)
    work_tree, work_index = tree_of(RUNTIME)
    chain_entries = tree_entries(clone, chain_index)
    work_entries = tree_entries(RUNTIME, work_index)
    for index in (chain_index, work_index):
        if index and os.path.exists(index):
            os.unlink(index)
    # The leftovers of a tool run are not part of the runtime: they are left out
    # of the truth above, so they must be left out of the comparison too.
    for path in junk:
        chain_entries.pop(path, None)
        work_entries.pop(path, None)
    only_chain = sorted(set(chain_entries) - set(work_entries))
    only_work = sorted(set(work_entries) - set(chain_entries))
    different = sorted(path for path in set(chain_entries) & set(work_entries)
                       if chain_entries[path] != work_entries[path])
    print(f"[stack] chain tree   {chain_tree} ({len(chain_entries)} files)")
    print(f"[stack] working tree {work_tree} ({len(work_entries)} files)")
    same = not only_chain and not only_work and not different
    print(f"[stack] identical: {same}")
    if not same:
        for path in only_chain[:40]:
            print(f"  only in the chain: {path}")
        for path in only_work[:40]:
            print(f"  only in the work tree: {path}")
        for path in different[:40]:
            print(f"  different: {path}")
        print("[stack] the rebuilt stack is not written (use --apply after fixing this)")
        return 2

    if args.apply:
        for name, text in rebuilt.items():
            (PATCHES / name).write_text(text, encoding="utf-8", newline="")
        for name in dropped:
            print(f"[stack] {name}: kept as it is (nothing left to apply)")
        print(f"[stack] written: {len(rebuilt)} patches, {len(regenerated)} regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
