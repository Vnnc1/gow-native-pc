"""Package the private precompiled Windows diagnostic kit; no game data is copied."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib


def required_disc_files(disc):
    # Prepared standalone translations can omit secondary PAKs (prepare.py normalizes their TOC).
    # This is a launch prerequisite check, not a complete disc-integrity audit.
    return [".disc_layout", disc["toc"], *disc["paks"][:1], disc["iop_modules_dir"]]


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ("runner", "launcher-build", "qt", "compiler-bin", "setup-base", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    profile = tomllib.loads((root / "games/gow1/game.toml").read_text(encoding="utf-8"))
    out = args.output.resolve()
    stage = out / "stage"
    stage.mkdir(parents=True, exist_ok=False)  # Never merge stale or unrelated package members.

    def copy(source, relative):
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def sha(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    runner = copy(args.runner, "runtime/ps2EntryRunner.exe")
    launcher = copy(args.launcher_build / "gow-diagnostics.exe", "launcher/bin/gow-launcher.exe")
    helper = copy(args.launcher_build / "gow-session.exe", "launcher/bin/gow-session.exe")
    for name in ("libc++.dll", "libunwind.dll"):
        copy(args.compiler_bin / name, "launcher/bin/" + name)
    copy(root / "games/gow1/game.toml", "games/gow1/game.toml")
    copy(root / "engine/runtime.toml", "engine/runtime.toml")
    for path in (root / "engine/patches").glob("*.patch"):
        copy(path, "engine/patches/" + path.name)
    for name in ("LICENSE", "CREDITS.md"):
        copy(root / name, name)
    copy(root / "docs/diagnostic-kit.pt-BR.md", "LEIA-ME.md")
    disc = profile["disc"]
    manifest = {
        "schema": 1, "purpose": "private diagnostic build; performance claims require matching hardware test results",
        "cpu_target": "x86-64-v2", "executable": profile["executable"],
        "frame_pc": profile["diagnostics"]["frame_pc"], "pad_script": profile["optimize"]["pad_script"],
        "required_files": required_disc_files(disc),
        "runner_sha256": sha(runner), "helper_sha256": sha(helper),
    }
    (stage / "diagnostic-kit.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = str(args.qt / "bin") + os.pathsep + str(args.compiler_bin) + os.pathsep + env["PATH"]
    subprocess.run([str(args.qt / "bin/windeployqt.exe"), "--no-translations",
                    "--no-system-d3d-compiler", "--no-compiler-runtime", "--qmldir",
                    str(root / "launcher/diagnostics"), str(launcher)], env=env, check=True)
    # Reproducible member hashes also catch missing/corrupt copies before installation.
    members = {p.relative_to(stage).as_posix(): sha(p) for p in sorted(stage.rglob("*")) if p.is_file()}
    (out / "members.json").write_text(json.dumps(members, indent=2), encoding="utf-8")
    setup = out / "setup.exe"
    subprocess.run([str(args.setup_base), "--pack", str(stage), str(setup)], check=True)
    (out / "setup.sha256.txt").write_text(sha(setup) + "  setup.exe\n", encoding="ascii")
    print(setup)


if __name__ == "__main__":
    main()
