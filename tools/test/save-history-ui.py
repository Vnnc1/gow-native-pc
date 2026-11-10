"""Exercise the real Saves page's automatic history refresh and translated source labels."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[2]
qml,compiler=map(lambda p:Path(p).resolve(),sys.argv[1:3])
with tempfile.TemporaryDirectory(prefix='save-history-ui-') as temporary:
    work=Path(temporary); shutil.copytree(root/'launcher/qml',work/'ui')
    (work/'ui/qmldir').write_text('singleton Tema 1.0 Tema.qml\n')
    (work/'test.qml').write_text('''
import QtQuick
import "ui" as UI
Item {
    width: 1000; height: 800
    property int calls: 0
    property int phase: 0
    property int pausedCalls: 0
    QtObject {
        id: lanzador
        property bool jugando: true
        signal jugandoCambiado()
        property var entries: []
        function partidas(folder) { calls++; return entries }
        function partidasIndividuales(elf) { return [{slot:2,file:2,nombre:"Templo do Oráculo",fecha:"04/11/2026 07:54:30",segundos:7041,imagen:""}] }
    }
    UI.PaginaPartidas { id: page; anchors.fill: parent; carpeta: "/private/history"; elf: "/private/ELF" }
    function check(value, message) { if (!value) throw Error(message) }
    Component.onCompleted: {
        UI.Tema.idioma = "pt"
        lanzador.entries = [{nombre:"test", etiqueta:"", fecha:"2026-11-09", origen:"auto", ruta:"/private/history/test"}]
    }
    Timer {
        interval: 2500; running: true; repeat: true
        onTriggered: {
            try {
                if (phase === 0) {
                    check(page.lista.length === 1 && page.lista[0].origen === "auto", "new backup not refreshed during play")
                    check(page.slots.length === 1 && page.slots[0].slot === 2 && page.slots[0].nombre === "Templo do Oráculo", "native slots not refreshed")
                    check(UI.Tema.t("partidaOrigen_auto").indexOf("Backup automático") >= 0, "missing automatic label")
                    page.visible = false; pausedCalls = calls; phase++
                } else if (phase === 1) {
                    check(calls === pausedCalls, "hidden page still polls")
                    lanzador.entries = []; page.visible = true
                    check(page.lista.length === 0, "showing page did not refresh history")
                    lanzador.jugando = false; lanzador.jugandoCambiado(); pausedCalls=calls; phase++
                } else {
                    check(calls === pausedCalls, "closed game still polls")
                    console.log("PASS: real Saves page refresh, hidden/closed stop and automatic source label")
                    Qt.exit(0)
                }
            } catch(error) { console.error(error); Qt.exit(1) }
        }
    }
}
''',encoding='utf-8')
    env=os.environ|{'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software','QT_FORCE_STDERR_LOGGING':'1',
                    'QT_QPA_FONTDIR':str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'),
                    'QT_QUICK_CONTROLS_STYLE':'Basic','PATH':str(qml.parent)+os.pathsep+str(compiler)+os.pathsep+os.environ.get('PATH','')}
    result=subprocess.run([str(qml),str(work/'test.qml')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=25)
    output=result.stdout.decode(errors='replace'); print(output)
    if result.returncode or 'PASS: real Saves' not in output or 'ReferenceError' in output or 'TypeError' in output:
        raise SystemExit(1)
