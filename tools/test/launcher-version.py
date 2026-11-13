"""Run the launcher's update version comparison (versionMayor in launcher/qml/Main.qml) in the QML engine.

usage: python -I tools/test/launcher-version.py <Qt bin/qml.exe> <compiler bin (its C++ runtime DLLs)>
A pre-release launcher (GOW_PRERELEASE, e.g. 0.6.1-rc.1) must be offered its final release; equal versions never are.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CASES = [  # (latest release, this launcher, offered?)
    ("0.6.1", "0.6.0", True), ("0.6.0", "0.6.0", False), ("0.6.0", "0.6.1", False),
    ("0.6.1", "0.6.1-rc.1", True), ("0.6.1-rc.1", "0.6.1", False), ("0.6.1-rc.1", "0.6.1-rc.1", False),
    ("0.6.1-rc.2", "0.6.1-rc.1", True), ("0.6.1-rc.10", "0.6.1-rc.2", True), ("0.6.1-rc.2", "0.6.1-rc.10", False),
    ("0.6.1-rc.1", "0.6.0", True), ("0.7.0", "0.6.1-rc.1", True), ("1.0.0", "0.9.9", True), ("0.10.0", "0.9.0", True),
    ("0.6.1-rc", "0.6.1-rc.1", False), ("0.6.1-rc.1", "0.6.1-rc", True),
    ("0.6.1-beta", "0.6.1-alpha", True), ("0.6.1-rc.1", "0.6.1-1", True), ("0.6.1-1", "0.6.1-rc.1", False),
]


def extract(source):
    start = source.index("    function versionMayor(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
        if depth == 0:
            return source[start:i]


def main():
    qml = Path(sys.argv[1]).resolve()
    compiler_bin = Path(sys.argv[2]).resolve()
    root = Path(__file__).resolve().parents[2]
    function = extract((root / "launcher/qml/Main.qml").read_text(encoding="utf-8"))
    checks = "\n".join(f'        check("{a}", "{b}", {str(e).lower()})' for a, b, e in CASES)
    test = f"""import QtQuick
QtObject {{
{function}
    property int failures: 0
    function check(a, b, expected) {{
        var got = versionMayor(a, b)
        console.log((got === expected ? "ok   " : "FAIL ") + a + " newer than " + b + ": " + got)
        if (got !== expected) ++failures
    }}
    Component.onCompleted: {{
{checks}
        console.log(failures ? "FAILED: " + failures : "PASS: launcher update version order")
        Qt.exit(failures ? 1 : 0)
    }}
}}
"""
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "version.qml"
        path.write_text(test, encoding="utf-8")
        env = os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1",
                            "PATH": str(qml.parent) + os.pathsep + str(compiler_bin) + os.pathsep + os.environ.get("PATH", "")}
        result = subprocess.run([str(qml), str(path)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    output = result.stdout.decode(errors="replace")
    print(output, end="")
    if result.returncode or "PASS: launcher update version order" not in output:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
