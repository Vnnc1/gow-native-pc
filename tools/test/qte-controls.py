"""Exercise actual Controls QML bindings and legacy keyboard-map migration."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
qml = Path(sys.argv[1]).resolve()
compiler_bin = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='qte-controls-') as scratch:
    work = Path(scratch)
    shutil.copytree(root / 'launcher/qml', work / 'ui')
    (work / 'ui/qmldir').write_text('singleton Tema 1.0 Tema.qml\n', encoding='utf-8')
    (work / 'test.qml').write_text('''
import QtQuick
import QtQuick.Controls
import "ui" as UI
import "ui/Teclas.js" as Keys
ApplicationWindow {
    id: window
    width: 1100; height: 1500; visible: true
    QtObject {
        id: mando
        property bool conectado: false
        property string nombre: ""
        signal boton(int codigo)
        function escuchar(value) {}
    }
    QtObject {
        id: settings
        property string teclas: '{"circle":[70],"ld_mod":[341],"r2":[341]}'
        property string mando: ""
        property bool controlesDmc5: true
        property bool cancelarAnimaciones: true
        property bool escSalir: false
        property bool qteAuto: false
        property bool qteHold: true
        property string qteHoldButtons: "circle"
        property int qteHoldRate: 10
        property bool qteHoldL1: false
        property bool qteHoldL2: false
        property bool qteHoldR1: false
        property bool qteHoldR2: false
        property string qteStickMode: "off"
        property string pacoteTexturas: ""
        property bool usarPacoteTexturas: false
    }
    UI.PaginaControles { id: page; anchors.fill: parent; ajustes: settings; visible: false }
    UI.AccessibilityPage { id: accessibility; anchors.fill: parent; settings: settings }
    function find(item, predicate) {
        if (predicate(item)) return item
        var children = item.children || []
        for (var i = 0; i < children.length; ++i) {
            var result = find(children[i], predicate)
            if (result) return result
        }
        return null
    }
    function check(ok, message) { if (!ok) throw new Error(message) }
    Timer {
        interval: 500; running: true
        onTriggered: {
            try {
                check(page.mapa.qte_stick[0] === 71, "old maps inherit G")
                check(page.mapa.ld_mod[0] === 342 && page.mapa.r2[0] === 341, "legacy Ctrl conflict was not migrated")
                var custom = Keys.leer('{"ld_mod":[88],"r2":[341]}')
                check(custom.ld_mod[0] === 88, "custom dodge key must stay unchanged")
                check(Keys.conflictos({ld_mod:[341],r2:[345]}, "ld_mod", 341).indexOf("r2") >= 0,
                      "shared modifier conflicts must be visible")
                var occupied = Keys.leer('{"ld_mod":[341],"r2":[341],"circle":[346],"l1":[71]}')
                check(occupied.ld_mod.length === 0 && occupied.qte_stick.length === 0,
                      "migration must not introduce Alt/G conflicts")
                check(occupied.circle[0] === 346 && occupied.l1[0] === 71,
                      "migration must preserve existing gameplay keys")
                var explicitGesture = Keys.leer('{"qte_stick":[71],"l1":[71]}')
                check(explicitGesture.qte_stick[0] === 71, "explicit gesture bindings must remain editable")
                var defaults = Keys.predeterminado()
                for (var action in defaults)
                    for (var code of defaults[action])
                        check(Keys.conflictos(defaults, action, code).length === 0, "conflicting default: " + action)
                var texture = find(accessibility, o => o.titulo === UI.Tema.t("pacoteTexturas"))
                check(texture !== null, "texture packs missing from Accessibility")
                var textureToggle = find(texture, o => o.toggled !== undefined && o.checkable === true)
                settings.pacoteTexturas = "/test/textures"
                textureToggle.checked = true
                textureToggle.toggled()
                check(settings.usarPacoteTexturas, "texture pack toggle did not persist")
                var autoRow = find(accessibility, o => o.titulo === UI.Tema.t("qteAuto"))
                check(autoRow !== null, "automatic QTE setting missing")
                var autoToggle = find(autoRow, o => o.toggled !== undefined && o.checkable === true)
                check(!settings.qteAuto, "automatic QTE must default off")
                autoToggle.checked = true; autoToggle.toggled()
                check(settings.qteAuto, "automatic QTE setting did not persist")
                autoToggle.checked = false; autoToggle.toggled()
                check(!settings.qteAuto, "automatic QTE setting did not disable")
                var buttons = ["L1", "L2", "R1", "R2"]
                for (var i = 0; i < buttons.length; ++i) {
                    var title = UI.Tema.t("qteHold") + " · " + buttons[i]
                    var row = find(accessibility, o => o.titulo === title)
                    check(row !== null, "missing shoulder row " + buttons[i])
                    var toggle = find(row, o => o.toggled !== undefined && o.checkable === true)
                    check(toggle !== null, "missing shoulder toggle")
                    toggle.checked = true
                    toggle.toggled()
                    check(settings["qteHold" + buttons[i]], "toggle did not update settings")
                }
                var gesture = find(accessibility, o => o.titulo === UI.Tema.t("qteStick"))
                var selector = find(gesture, o => o.opciones !== undefined)
                selector.elegido("rotate")
                check(settings.qteStickMode === "rotate", "gesture selection not saved")
                page.abrirCaptura("qte_stick", 0)
                page.asignar(1003)
                check(JSON.parse(settings.teclas).qte_stick[0] === 1003, "mouse remapping not saved")
                console.log("PASS: actual QTE Controls bindings")
                Qt.exit(0)
            } catch (error) { console.error(error); Qt.exit(1) }
        }
    }
}
''', encoding='utf-8')
    env = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
                        'QT_FORCE_STDERR_LOGGING': '1',
                        'QT_QPA_FONTDIR': str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts'), 'QT_QUICK_CONTROLS_STYLE': 'Basic',
                        'PATH': str(qml.parent) + os.pathsep + str(compiler_bin) + os.pathsep + os.environ.get('PATH', '')}
    result = subprocess.run([str(qml), str(work / 'test.qml')], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    output = result.stdout.decode(errors='replace')
    print(output, end='')
    if result.returncode or 'PASS: actual QTE Controls' not in output or 'ReferenceError' in output or 'TypeError' in output:
        raise SystemExit(1)
