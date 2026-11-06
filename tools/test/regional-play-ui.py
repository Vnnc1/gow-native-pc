"""Exercise Main.qml's real play/save selection with isolated settings and fake children."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
qml = Path(sys.argv[1]).resolve()
compiler = Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='regional-play-ui-') as temporary:
    work = Path(temporary)
    shutil.copytree(root / 'launcher/qml', work / 'ui')
    (work / 'ui/qmldir').write_text('singleton Tema 1.0 Tema.qml\n')
    main = work / 'ui/Main.qml'
    main.write_text(main.read_text(encoding='utf-8').replace('category: "ajustes"',
        'location: "' + (work / 'settings.ini').as_uri() + '"\n        category: "ajustes"'), encoding='utf-8')
    (work / 'test.qml').write_text('''
import QtQuick
import "ui" as UI
Item {
    property int pestanaInicial: 0
    property string idiomaCaptura: "pt"
    property string fuenteTitulo: "Arial"
    QtObject {
        id: installer
        property string repoRoot: "/repo"
        property string gameId: "gow1"
        property bool running: false
        property bool identifying: false
        property string stages: ""
        signal finished(bool ok, int code)
        signal updateChecked(var info)
        signal identified(var discs)
        signal stepChanged(string step)
        signal progress(int done, int total)
        signal statusText(string text)
        signal logLine(string text)
        function languages() { return [
            {language:"en", elf:"/usa/ELF", runner:"/usa/runner", label:"USA"},
            {language:"region:europe", elf:"/europe/ELF", runner:"/europe/runner", label:"Europe", regional:true, dataDir:"/europe/data", saves:"/europe/data/saves", framePc:"0x1838a8"},
            {language:"region:japan", elf:"/japan/ELF", runner:"/japan/runner", label:"Japan", regional:true, dataDir:"/japan/data", saves:"/japan/data/saves", framePc:"0x183bb8"}
        ] }
        function runnerPath() { return "/usa/runner" }
        function pgoApplied() { return true }
        function checkUpdate() {}
        function diagnosticsFramePc() { return "0x1837b8" }
        function hasPendingNativeCode() { return false }
        function environment() { return {tools:true, runtime:true, game:true} }
        function needsRebuild() { return false }
        function cpuSupported() { return true }
        function cpuThreads() { return 8 }
        function discScanReport() { return {files:0, complete:false} }
        function loadingArt() { return [] }
    }
    QtObject {
        id: lanzador
        property string sistema: "windows"
        property bool jugando: false
        property var lastPlay: null
        property string lastSaves: ""
        signal error(string clave, string detalle)
        signal juegoTerminado(int codigo, bool fallo, int segundos, string resumen)
        signal jugandoCambiado()
        signal diagnosticsExported(bool ok, string path)
        function tarjetasGraficas() { return [] }
        function pantalla() { return {ancho:1280, alto:720} }
        function comprobarJuego(path) { return {} }
        function comprobarDatos(elf, iso) { return {} }
        function comprobarEjecutable(path) { return {} }
        function esRecorte(path) { return false }
        function urlDesdeRuta(path) { return "" }
        function iniciar(args) { lastPlay = args; return false }
        function partidas(path) { lastSaves = path; return [] }
    }
    QtObject { id: mando; property bool conectado: false; signal boton(string name) }
    // Mod model is a C++ context property in the real launcher; the play path only needs its staging result,
    // but Main.qml also instantiates the Mods page, whose bindings need the harmless empty shapes below.
    QtObject {
        id: modeloMods
        property var mods: []
        property var profiles: []
        property var diagnostics: []
        property var lastRun: ({hits: 0, lookups: 0})
        property string lastError: ""
        property string notice: ""
        property string profile: "launcher"
        property int enabledCount: 0
        property bool active: false
        property bool busy: false
        property bool pythonReady: true
        property bool stale: false
        property bool requiresRebuild: false
        function refresh() {}
        function prepararEntorno(path) { return {ok: true, env: {}} }
    }
    UI.Main { id: page }
    function check(ok, message) { if (!ok) throw new Error(message) }
    Timer {
        interval: 500; running: true
        onTriggered: {
            try {
                check(page.listo, "registered installations must be playable")
                for (var region of ["europe", "japan"]) {
                    page.ajustesGuardados.textoJuego = "region:" + region
                    page.jugar()
                    var args = lanzador.lastPlay
                    check(args.ejecutable === "/"+region+"/runner", "wrong regional runner")
                    check(args.elf === "/"+region+"/ELF", "wrong regional ELF")
                    check(args.partidas === "/"+region+"/data/saves", "shared saves")
                    check(page.carpetaPartidas === args.partidas, "Saves page disagrees with gameplay")
                    check(lanzador.lastSaves === args.partidas, "Saves list was not refreshed after changing region")
                    check(args.capturaVu1 === "", "JIT-only regions must not record unused AOT captures")
                    check(args.framePc === (region === "europe" ? "0x1838a8" : "0x183bb8"), "USA frame probe leaked")
                }
                page.ajustesGuardados.textoJuego = "en"
                page.jugar()
                check(lanzador.lastPlay.ejecutable === "/usa/runner", "USA runner changed")
                check(lanzador.lastPlay.partidas === "/repo/data/gow1/saves", "USA saves changed")
                check(lanzador.lastPlay.framePc === "0x1837b8", "USA frame probe changed")
                // gow-native-pc: the effect toggles are Settings properties, but Lanzador::iniciar only sees the
                // explicit play map. A key left out there silently reads as false and the switch does nothing.
                check(lanzador.lastPlay.fxSinSombras === false && lanzador.lastPlay.fxSinAditivos === false
                      && lanzador.lastPlay.fxSinFiltrado === false, "effect switches must default to off in the play map")
                page.ajustesGuardados.fxSinSombras = true
                page.ajustesGuardados.fxSinAditivos = true
                page.ajustesGuardados.fxSinFiltrado = true
                page.jugar()
                check(lanzador.lastPlay.fxSinSombras === true && lanzador.lastPlay.fxSinAditivos === true
                      && lanzador.lastPlay.fxSinFiltrado === true, "effect switches were not forwarded to Lanzador::iniciar")
                // The "low" graphics profile must still reach the runner as a smaller internal resolution.
                page.ajustesGuardados.resolucionInterna = "0.5"
                page.jugar()
                check(lanzador.lastPlay.escala === 0.5, "the low profile must lower PS2X_GS_HW_SCALE")
                page.ajustesGuardados.resolucionInterna = "2"
                // The texture, presentation and renderer switches are Settings properties, but Lanzador::iniciar
                // only sees the explicit play map. A key left out there silently reads as its default and the
                // switch does nothing (the same dead-toggle class as the three effect switches above).
                page.ajustesGuardados.texPresupuestoMb = 2048
                page.ajustesGuardados.progresivo = false
                page.ajustesGuardados.gsCacheEstado = false
                page.ajustesGuardados.presentacion = "21:9"
                page.jugar()
                check(lanzador.lastPlay.texPresupuestoMb === 2048 && lanzador.lastPlay.progresivo === false
                      && lanzador.lastPlay.gsCacheEstado === false && lanzador.lastPlay.presentacion === "21:9",
                      "texture, presentation and renderer switches were not forwarded by jugar()")
                page.ajustesGuardados.textoJuego = "region:missing"
                check(!page.selectedGame && page.carpetaPartidas === "", "missing regional build must not silently select USA saves")
                console.log("PASS: real Main.qml region routing and save isolation")
                Qt.exit(0)
            } catch (error) { console.error(error); Qt.exit(1) }
        }
    }
}
''', encoding='utf-8')
    env = os.environ | {'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
        'QT_FORCE_STDERR_LOGGING': '1', 'QT_QUICK_CONTROLS_STYLE': 'Basic',
        'QT_QPA_FONTDIR': str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts'),
        'PATH': str(qml.parent) + os.pathsep + str(compiler) + os.pathsep + os.environ.get('PATH', '')}
    result = subprocess.run([str(qml), str(work / 'test.qml')], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    output = result.stdout.decode(errors='replace')
    print(output)
    if result.returncode or 'PASS: real Main.qml' not in output or 'ReferenceError' in output or 'TypeError' in output:
        raise SystemExit(1)
