"""Exercise the actual Install QML import/retry/compatibility state without a game."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
qml = Path(sys.argv[1]).resolve()
compiler_bin = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='disc-import-ui-') as scratch:
    work = Path(scratch)
    shutil.copytree(root / 'launcher/qml', work / 'ui')
    (work / 'ui/qmldir').write_text('singleton Tema 1.0 Tema.qml\n', encoding='utf-8')
    (work / 'test.qml').write_text('''
import QtQuick
import QtQuick.Controls
import "ui" as UI
ApplicationWindow {
    width: 1100; height: 1000; visible: true
    QtObject {
        id: installer
        property bool running: false
        property bool identifying: false
        property string repoRoot: "/test"
        signal identified(var discs)
        signal stepChanged(string step)
        signal progress(int done, int total)
        signal statusText(string text)
        signal logLine(string text)
        signal finished(bool ok, int code)
        function environment() { return {tools:true, runtime:true, game:false, discs:false} }
        function languages() { return [] }
        function discScanReport() { return {} }
        function cpuSupported() { return true }
        function cpuThreads() { return 8 }
        function needsRebuild() { return false }
        function pgoApplied() { return false }
        function identify(paths) { identifying = true }
        function run(stages, options) { return true }
        function cancel() {}
        function openRunnerFolder() {}
    }
    QtObject {
        id: lanzador
        property string sistema: "windows"
        function rutaDesdeUrl(url) { return url.toString() }
    }
    UI.InstallPage { id: page; anchors.fill: parent }
    function check(ok, message) { if (!ok) throw new Error(message) }
    Timer {
        interval: 500; running: true
        onTriggered: {
            try {
                check(!page.canInstall, "empty list must not install")
                installer.identified([{path:"/japan.iso", compatible:false, reason_code:"region_not_ported", problems:[]}])
                check(!page.canInstall && page.discs.length === 1, "unsupported region must stay blocked")
                installer.identified([{path:"/demo.iso", compatible:false, reason_code:"demo_excluded", problems:[]}])
                check(!page.canInstall, "demo must stay blocked")
                installer.identified([{path:"/usa.chd", compatible:false, reason_code:"import_failed", problems:["failure"]}])
                installer.identified([{path:"/usa.chd", compatible:true, problems:[]}])
                check(page.discs.length === 3, "retry must replace the failed entry")
                check(page.canInstall, "compatible CHD must enable install")
                check(JSON.stringify(page.compatibleIsos()) === '["/usa.chd"]', "pipeline must receive the original CHD path only")
                page.pickIsos(["/next.chd"])
                check(installer.identifying && !page.canInstall, "import in progress must block installation")
                installer.logLine("Verifying CHD")
                check(page.log[page.log.length-1] === "Verifying CHD", "CHD status must reach the visible log")
                installer.identifying = false
                check(page.canInstall, "finished import must release the UI")
                console.log("PASS: disc import QML")
                Qt.exit(0)
            } catch (error) { console.error(error); Qt.exit(1) }
        }
    }
}
''', encoding='utf-8')
    env = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
                        'QT_FORCE_STDERR_LOGGING': '1', 'QT_QUICK_CONTROLS_STYLE': 'Basic',
                        'QT_QPA_FONTDIR': str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts'),
                        'PATH': str(qml.parent) + os.pathsep + str(compiler_bin) + os.pathsep + os.environ.get('PATH', '')}
    result = subprocess.run([str(qml), str(work / 'test.qml')], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    output = result.stdout.decode(errors='replace')
    print(output, end='')
    if result.returncode or 'PASS: disc import QML' not in output or 'ReferenceError' in output or 'TypeError' in output:
        raise SystemExit(1)
