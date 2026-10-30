"""Create a patch against a saved file baseline without changing the runtime index."""
import argparse
import difflib
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", type=Path)
    p.add_argument("runtime", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--header", required=True)
    p.add_argument("files", nargs="+")
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("Refusing to overwrite an existing patch")
    chunks = [a.header + "\n\n"]
    for name in a.files:
        old, new = a.baseline / name, a.runtime / name
        # Runtime sources are UTF-8 (Spanish comments); the Windows default code page cannot decode them.
        before = old.read_text(encoding="utf-8").splitlines(keepends=True) if old.exists() else []
        after = new.read_text(encoding="utf-8").splitlines(keepends=True)
        if before == after:
            continue
        chunks.append(f"diff --git a/{name} b/{name}\n")
        if not old.exists():
            chunks.append("new file mode 100644\n")
        chunks.extend(difflib.unified_diff(before, after, fromfile=f"a/{name}" if old.exists() else "/dev/null", tofile=f"b/{name}"))
    a.output.write_text("".join(chunks), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
