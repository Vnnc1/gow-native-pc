"""Run the real loading-screen QML with fake pipeline signals, using the existing Qt SDK."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
qml = Path(sys.argv[1]).resolve()
compiler_bin = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix="loading-progress-", dir=root / "data") as scratch:
    work = Path(scratch)
    shutil.copytree(root / "launcher/qml", work / "ui")
    # Match the production module's singleton declaration without needing the full launcher executable.
    (work / "ui/qmldir").write_text("singleton Tema 1.0 Tema.qml\n", encoding="utf-8")
    shutil.copyfile(root / "launcher/pruebas/loading_progress.qml", work / "test.qml")
    env = os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_FORCE_STDERR_LOGGING": "1",
                       "QT_QUICK_CONTROLS_STYLE": "Basic",
                       "QT_QPA_FONTDIR": str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts"),
                       "PATH": str(qml.parent) + os.pathsep + str(compiler_bin) + os.pathsep + os.environ.get("PATH", "")}
    result = subprocess.run([str(qml), str(work / "test.qml")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    output = result.stdout.decode(errors="replace")
    print(output, end="")
    if result.returncode or "PASS: actual LoadingScreen" not in output or "ReferenceError" in output or "TypeError" in output:
        print(f"Loading-screen regression failed (exit {result.returncode})")
        raise SystemExit(1)
