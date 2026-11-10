import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Shapes
import "Teclas.js" as Teclas
import "Textos.js" as Textos

// Main launcher window: a sidebar with the pages on the left; Home (title, Play, language, summary) and the settings
// pages on the right.
ApplicationWindow {
    id: ventana
    width: 1280
    height: 760
    minimumWidth: 1040
    minimumHeight: 660
    visible: true
    title: "God of War — Native PC"
    color: Tema.fondo
    flags: Qt.Window | Qt.FramelessWindowHint
    font.family: Tema.fuenteCuerpo

    // Page shown: 0 Home, 1 Install, 2 Graphics, 3 Performance, 4 Controls, 5 Cheats, 6 Other.
    property int pagina: pestanaInicial
    // gow-native-pc: memory card copies (F1 > Saves in game, the Saves page here)
    readonly property var selectedGame: idiomaJuego(ajustes.textoJuego)
        || (!ajustes.textoJuego && idiomasJuego.length ? idiomasJuego[0] : null)
    readonly property bool selectedRegional: !!(selectedGame && selectedGame.regional)
    property bool playingRegional: false
    readonly property string carpetaPartidas: !selectedGame ? "" : selectedRegional ? selectedGame.saves
        : installer.repoRoot + "/data/" + installer.gameId + "/saves"
    // The Settings object for the pages: inside their Components "ajustes" names the page's own property.
    readonly property var ajustesGuardados: ajustes

    function sincronizarAjustesMenu() {
        const changes = lanzador.sincronizarMenu()
        for (const key in changes) ajustes[key] = changes[key]
        if (Object.keys(changes).length) ajustes.sync()
    }

    Timer {
        interval: 500; running: true; repeat: true; triggeredOnStart: true
        onTriggered: ventana.sincronizarAjustesMenu()
    }

    Settings {
        id: ajustes
        category: "ajustes"
        property string idioma: ""
        property string gpu: "auto"
        property string modoPantalla: "completa"
        property int ancho: 1280
        property int alto: 800
        property string aspecto: ""
        property bool estirar: false
        property string filtro: "bilineal" // soft image by default
        property real nitidez: 0.8
        property int audioVolume: 100
        property bool audioMute: false
        property bool fxaa: true
        property string anisotropico: "1" // anisotropic texture filtering: 1 = off, 2..16 (GOW_ANISO)
        property string resolucionInterna: "2" // "auto" (from the display) or "1".."8" (PS2X_GS_HW_SCALE)
    property bool dibujoHardware: true // false = software rasterizer, for a GPU without OpenGL 4.3 (PS2X_GS_RENDERER=sw)
        property int fpsLimite: 60
        property bool vsync: false
        property bool mostrarFps: false
        property string elf: ""
        property string iso: ""
        property string ejecutable: ""
        property bool saltarVideos: false // native movies include sound
        property bool arranqueRapido: false // used to shorten the game's opening (see Component.onCompleted)
        property int versionAjustes: 0
        property bool controlesDmc5: true
        property bool cancelarAnimaciones: true // snappier evade and input buffer (GOW_CANCELAR)
        // gow-native-pc: accessibility — holding a button instead of mashing it in the minigames (GOW_QTE_HOLD)
        property bool qteAuto: false
        property bool qteHold: false
        property string qteHoldButtons: "circle" // Base group; shoulders are independent opt-ins.
        property bool qteHoldL1: false
        property bool qteHoldL2: false
        property bool qteHoldR1: false
        property bool qteHoldR2: false
        property string qteStickMode: "off"
        property int qteHoldRate: 10 // presses per second the assist makes (GOW_QTE_HOLD_HZ)
        property bool escSalir: false
        property bool minimizarAlJugar: true
        property int segundosJugados: 0
        property int ultimaSesion: 0
        property string portada: ""
        property string teclas: "" // key map as JSON (empty = default layout)
        property string mando: "" // controller layout as JSON (empty = the fixed layout of controlesDmc5)
        property bool compilarAreas: true // in-process x64 JIT; existing saved choices are preserved
        property bool autoNative: false // optional AOT build after a successful play session
        property bool finAnticipado: true // GOW_GS_EARLY_FINISH (runtime patch 40): the EE prepares the next frame while VU1 draws
        property string pacoteTexturas: "" // texture pack folder (PCSX2 format, GOW_TEXTURE_PACK, runtime patch 52)
        property bool usarPacoteTexturas: false
        property bool vuRapida: false // GOW_VU1_FAST (runtime patch 51): VU1 blocks without operand normalisation / MADD overflow check
        property bool jitInline: true
        property bool diagnostics: false
        // gow-native-pc (runtime patch 80): effect switches. All off = the original picture; they only change the
        // host-side GS draw, the guest runs exactly the same.
        property bool fxSinSombras: false // GOW_FX_NO_SHADOWS
        property bool fxSinAditivos: false // GOW_FX_NO_ADDITIVE3D
        property bool fxSinFiltrado: false // GOW_FX_NO_TEXTURE_FILTER
        // gow-native-pc: the rest of the picture, texture and renderer switches the runtime actually reads.
        // Every default below is the runtime's own default; a switch left at its default writes no variable
        // (or writes "1" where the runtime only checks for "0"), so the original picture is byte-identical.
        // Texture packs (runtime patch 52).
        property int texPresupuestoMb: 1024 // GOW_TEXTURE_PACK_MB: GPU budget for replacement PNGs, >= 64 MiB
        property bool texEstadisticas: false // GOW_TEXTURE_PACK_STATS: hits / loads / evictions every 300 frames
        property bool texNombres: false // GOW_TEX_PCSX2_NAMES: list the texture names a session samples
        property int texVolcado: 0 // GOW_GS_HW_TEXDUMP: dump the first N game textures (developer only)
        // Presentation and video mode.
        property bool progresivo: true // GOW_PROGRESIVO=0 goes back to the game's interlaced setting
        property string presentacion: "auto" // TOBIICHI_ASPECTO: auto | estirar | 4:3 | 16:9 | 16:10 | 21:9 | 32:9
        property bool presentacionDirecta: true // PS2X_GS_DIRECT_PRESENT=0 forces the RAM readback path
        property int glMenor: 6 // GOW_GL_MAX_MINOR: first OpenGL 4.n context to request (3..6)
        // Renderer pipeline (advanced): on by default in the runtime, "0" selects the older code path.
        property bool gsCacheEstado: true // GOW_GS_STATE_CACHE (patch 72)
        property bool gsReusoTexturas: true // GOW_GS_TEXREUSE (patch 61)
        property bool gsAnilloVertices: true // GOW_GS_HW_RING (patch 59)
        property bool gsProfundidadZbp: true // GOW_GS_DEPTH_PER_ZBP (patch 69)
        property bool gsAgruparPrimitivas: true // PS2X_GS_RUN (patch 66)
        property bool gsRunRapido: true // PS2X_GS_RUN_STATE_FAST (patch 74)
        property bool gsColaCompacta: true // PS2X_GS_COMPACT_QUEUE
        property bool gsHiloWorker: true // PS2X_GS_WORKER (VIF1/GIF on its own thread)
        property bool gsHiloPipeline: true // PS2X_GS_PIPELINE (GS frontend stage thread)
        property bool gsFinishAsincrono: true // GOW_GS_FINISH_ASINCRONO
        property bool gsEnvioAsincrono: false // GOW_GS_ASYNC_SUBMIT (patch 77, off by default)
        property int gsBloquesCola: 0 // PS2X_GS_QUEUE_CHUNKS: 0 = the renderer's own default
        // Renderer diagnostics (counters only, no picture change).
        property bool gsEstadisticas: false // GOW_GS_HW_STATS
        property bool gsPerfilGpu: false // GOW_GS_GPU_PROFILE
        property bool verAvanzado: false // UI only: reveal the advanced renderer switches
        property string trucos: "" // cheats active at start, comma separated (gow_trucos.cpp)
        property string textoJuego: "" // game language: a "language" of installer.languages() (e.g. "en", "pt-BR"); empty = ask
        property real portadaFoco: 0.55
        property real portadaBrillo: 0.85
    }

    Binding { target: Tema; property: "idioma"; value: idiomaCaptura || ajustes.idioma || "en" }
    Binding { target: Tema; property: "fuenteTitulo"; value: fuenteTitulo }

    readonly property var pantalla: lanzador.pantalla()
    property var tarjetas: lanzador.tarjetasGraficas()
    readonly property bool gpuPerdida: ajustes.gpu !== "auto" && !tarjetaExiste(ajustes.gpu)
    readonly property var estadoJuego: lanzador.comprobarJuego(ajustes.elf)
    readonly property var estadoDatos: lanzador.comprobarDatos(ajustes.elf, ajustes.iso)
    readonly property var estadoEjecutable: lanzador.comprobarEjecutable(ajustes.ejecutable)
    // gow-native-pc: ready = the game is built and at least one language's disc is prepared (Install tab)
    // Plain values, not bindings: installer.languages() / runnerPath() are function calls QML evaluates once, so they
    // are read again by refrescarInstalacion() when a build finishes and before playing.
    property var idiomasJuego: installer.languages()
    property string ejecutableJuego: installer.runnerPath()
    property bool pgoAtivo: installer.pgoApplied() // the installed build uses the profile-guided optimisation
    readonly property bool listo: idiomasJuego.some(function(e) { return !!e.runner })
    // gow-native-pc: launcher updates (GitHub Releases, tools/pipeline/update.ps1). A newer release than this launcher is
    // offered under the version in the side bar.
    property var actualizacion: null
    function versionMayor(a, b) {
        var x = String(a).split("."), y = String(b).split(".")
        for (var i = 0; i < Math.max(x.length, y.length); ++i) {
            var p = parseInt(x[i] || "0"), q = parseInt(y[i] || "0")
            if (p !== q) return p > q
        }
        return false
    }
    Connections {
        target: installer
        function onUpdateChecked(info) {
            if (info && !info.error && ventana.versionMayor(info.version, Qt.application.version))
                ventana.actualizacion = info
        }
    }
    function refrescarInstalacion() {
        idiomasJuego = installer.languages()
        ejecutableJuego = installer.runnerPath()
        pgoAtivo = installer.pgoApplied()
    }
    Connections {
        target: installer
        function onFinished() { ventana.refrescarInstalacion() }
    }
    // also when the window comes back to the front (a build run from a terminal with build.cmd)
    onActiveChanged: if (active && !installer.running) refrescarInstalacion()
    function idiomaJuego(codigo) {
        for (var i = 0; i < idiomasJuego.length; ++i)
            if (idiomasJuego[i].language === codigo) return idiomasJuego[i]
        return null
    }
    // A cut-out image (transparent background) is shown as a figure; an opaque one covers the cover area.
    readonly property bool portadaRecorte: ajustes.portada.length > 0 && lanzador.esRecorte(ajustes.portada)

    function tarjetaExiste(id) {
        for (var i = 0; i < tarjetas.length; ++i)
            if (tarjetas[i].id === id) return true
        return false
    }

    function aspectoPorDefecto() {
        var r = pantalla.ancho / pantalla.alto
        if (r >= 3.2) return "32:9"
        if (r >= 2.2) return "21:9"
        if (r >= 1.7) return "16:9"
        if (r >= 1.5) return "16:10"
        return "4:3"
    }

    // Internal resolution. Automatic: the image height on screen divided by 448 lines, 2x to 8x.
    function escalaAuto() {
        var alto = ajustes.modoPantalla !== "ventana" ? pantalla.alto : ajustes.alto
        return Math.max(2, Math.min(8, Math.floor(alto / 448)))
    }
    function escalaElegida() {
        var n = parseFloat(ajustes.resolucionInterna)
        return ajustes.resolucionInterna === "auto" || isNaN(n) ? escalaAuto() : Math.max(0.25, Math.min(4, n))
    }
    function textoEscala(n) {
        return n + "× · " + Math.round(512 * n) + "×" + Math.round(448 * n)
    }

    function detectarRutas(forzar) {
        var r = lanzador.rutasDetectadas()
        if ((forzar || ajustes.elf.length === 0) && r.elf.length > 0) ajustes.elf = r.elf
        if ((forzar || ajustes.ejecutable.length === 0) && r.ejecutable.length > 0) ajustes.ejecutable = r.ejecutable
    }

    function restablecer() {
        ajustes.gpu = "auto"
        ajustes.modoPantalla = "completa"
        ajustes.ancho = 1280
        ajustes.alto = pantalla.ancho / pantalla.alto < 1.7 ? 800 : 720
        ajustes.aspecto = aspectoPorDefecto()
        ajustes.estirar = false
        // Match the current first-launch defaults, including diagnostic and experimental options.
        ajustes.filtro = "bilineal"
        ajustes.nitidez = 0.8
        ajustes.fxaa = true
        ajustes.anisotropico = "1"
        ajustes.resolucionInterna = "2"
        // the game makes at most 60 frames; a higher window rate only repeats them
        ajustes.fpsLimite = 60
        ajustes.vsync = false
        ajustes.mostrarFps = false
        ajustes.saltarVideos = false
        ajustes.finAnticipado = true
        ajustes.vuRapida = false
        ajustes.diagnostics = false
        ajustes.autoNative = false
        ajustes.usarPacoteTexturas = false
        ajustes.arranqueRapido = false
        ajustes.controlesDmc5 = true
        ajustes.audioVolume = 100
        ajustes.audioMute = false
        ajustes.mando = ""
        ajustes.cancelarAnimaciones = true
        ajustes.qteAuto = false
        ajustes.qteHold = false
        ajustes.qteHoldButtons = "circle"
        ajustes.qteHoldL1 = false
        ajustes.qteHoldL2 = false
        ajustes.qteHoldR1 = false
        ajustes.qteHoldR2 = false
        ajustes.qteStickMode = "off"
        ajustes.qteHoldRate = 10
        ajustes.escSalir = false
        ajustes.minimizarAlJugar = true
        ajustes.trucos = ""
        ajustes.fxSinSombras = false
        ajustes.fxSinAditivos = false
        ajustes.fxSinFiltrado = false
        // Textures, presentation, renderer pipeline and diagnostics: all back to the runtime's defaults.
        ajustes.texPresupuestoMb = 1024
        ajustes.texEstadisticas = false
        ajustes.texNombres = false
        ajustes.texVolcado = 0
        ajustes.progresivo = true
        ajustes.presentacion = "auto"
        ajustes.presentacionDirecta = true
        ajustes.glMenor = 6
        ajustes.gsCacheEstado = true
        ajustes.gsReusoTexturas = true
        ajustes.gsAnilloVertices = true
        ajustes.gsProfundidadZbp = true
        ajustes.gsAgruparPrimitivas = true
        ajustes.gsRunRapido = true
        ajustes.gsColaCompacta = true
        ajustes.gsHiloWorker = true
        ajustes.gsHiloPipeline = true
        ajustes.gsFinishAsincrono = true
        ajustes.gsEnvioAsincrono = false
        ajustes.gsBloquesCola = 0
        ajustes.gsEstadisticas = false
        ajustes.gsPerfilGpu = false
    }

    // Name key of the Graphics page's quick profile the current settings match (PaginaGrafico.qml perfiles).
    function perfilTexto() {
        var r = ajustes.resolucionInterna, f = ajustes.filtro, x = ajustes.fxaa, a = ajustes.anisotropico
        if (r === "0.5" && f === "bilineal" && !x && a === "1") return "perfilBajo"
        if (f !== "fsr") return "perfilPersonalizado"
        if (r === "1" && !x && a === "1") return "perfilDesempenho"
        if (r === "2" && x && a === "4") return "perfilEquilibrado"
        if (r === "auto" && x && a === "16") return "perfilQualidade"
        return "perfilPersonalizado"
    }

    function nombreGpu() {
        if (ajustes.gpu === "auto" || gpuPerdida) return Tema.t("gpuAuto")
        for (var i = 0; i < tarjetas.length; ++i)
            if (tarjetas[i].id === ajustes.gpu)
                return lanzador.sistema === "windows" ? Tema.t(tarjetas[i].id === "ahorro" ? "gpuAhorro" : "gpuRendimiento")
                                                      : tarjetas[i].fabricante + " " + tarjetas[i].nombre
        return Tema.t("gpuAuto")
    }

    function jugar() {
        if (installer.running || lanzador.jugando) return
        refrescarInstalacion()
        if (!listo) { aviso(Tema.t("instNotReady")); ventana.pagina = 1; return }
        var elegido = idiomaJuego(ajustes.textoJuego)
        if (!elegido) {
            if (idiomasJuego.length > 1) { preguntaIdioma.open(); return }
            elegido = idiomasJuego[0]
            ajustes.textoJuego = elegido.language
        }
        // Mods (launcher patch 73): stage the enabled profile and hand the environment to the runner. With no mod,
        // prepararEntorno returns an empty map (and clears stale mod variables) so the original game is untouched.
        var modPrep = modeloMods.prepararEntorno(ajustes.usarPacoteTexturas ? ajustes.pacoteTexturas : "", elegido.elf, elegido.runner)
        if (!modPrep.ok) {
            dialogoError.texto = Tema.t("modsError")
            dialogoError.detalle = modPrep.error
            dialogoError.open()
            ventana.pagina = 9
            return
        }
        var a = {
            gpu: gpuPerdida ? "auto" : ajustes.gpu,
            modoPantalla: ajustes.modoPantalla,
            ancho: ajustes.ancho, alto: ajustes.alto,
            aspecto: ajustes.aspecto, presentacion: ajustes.presentacion,
            filtro: ajustes.filtro, nitidez: ajustes.nitidez, fxaa: ajustes.fxaa, anisotropico: ajustes.anisotropico,
            escala: escalaElegida(),
            dibujoHardware: ajustes.dibujoHardware,
            // Effect switches (runtime patch 80). Lanzador::iniciar reads them from this map and turns true into a
            // GOW_FX_* environment variable; a key missing here makes the switch a dead toggle (all read as false).
            fxSinSombras: ajustes.fxSinSombras, fxSinAditivos: ajustes.fxSinAditivos,
            fxSinFiltrado: ajustes.fxSinFiltrado,
            // Textures, presentation, renderer pipeline and diagnostics. Every key Lanzador::iniciar() reads
            // must be forwarded here: a missing key silently reads as false/0 (the patch 81 v2 dead-toggle bug).
            texPresupuestoMb: ajustes.texPresupuestoMb, texEstadisticas: ajustes.texEstadisticas,
            texNombres: ajustes.texNombres, texVolcado: ajustes.texVolcado,
            progresivo: ajustes.progresivo, presentacionDirecta: ajustes.presentacionDirecta,
            glMenor: ajustes.glMenor,
            gsCacheEstado: ajustes.gsCacheEstado, gsReusoTexturas: ajustes.gsReusoTexturas,
            gsAnilloVertices: ajustes.gsAnilloVertices, gsProfundidadZbp: ajustes.gsProfundidadZbp,
            gsAgruparPrimitivas: ajustes.gsAgruparPrimitivas, gsRunRapido: ajustes.gsRunRapido,
            gsColaCompacta: ajustes.gsColaCompacta, gsHiloWorker: ajustes.gsHiloWorker,
            gsHiloPipeline: ajustes.gsHiloPipeline, gsFinishAsincrono: ajustes.gsFinishAsincrono,
            gsEnvioAsincrono: ajustes.gsEnvioAsincrono, gsBloquesCola: ajustes.gsBloquesCola,
            gsEstadisticas: ajustes.gsEstadisticas, gsPerfilGpu: ajustes.gsPerfilGpu,
            fpsLimite: ajustes.fpsLimite, vsync: ajustes.vsync, mostrarFps: ajustes.mostrarFps,
            elf: elegido.elf, iso: "", ejecutable: elegido.runner,
            // new VU1 microcode met while playing is recorded; the Install tab compiles it ("Speed up visited areas")
            // Isolated regional builds use JIT and have no launcher AOT rebuild stage.
            capturaVu1: elegido.regional ? "" : installer.repoRoot + "/data/" + installer.gameId + "/vu1_capture",
            // VU1 code met without native code is always compiled while playing (x86-64 JIT, GOW_VU1N_X64, inline tier):
            // the native path is the fast one, so it is no longer a switch
            datosJit: elegido.dataDir || installer.repoRoot + "/data/" + installer.gameId,
            jitInline: true,
            finAnticipado: ajustes.finAnticipado,
            vuRapida: ajustes.vuRapida,
            pacoteTexturas: ajustes.usarPacoteTexturas ? ajustes.pacoteTexturas : "",
            diagnostics: ajustes.diagnostics,
            framePc: elegido.framePc || installer.diagnosticsFramePc(),
            // F1 > Saves in game copies the memory card here; the Saves page puts a copy back (GOW_SAVES_DIR)
            partidas: carpetaPartidas,
            saltarVideos: ajustes.saltarVideos, arranqueRapido: ajustes.arranqueRapido,
            controlesDmc5: ajustes.controlesDmc5, escSalir: ajustes.escSalir,
            cancelarAnimaciones: ajustes.cancelarAnimaciones,
            qteHoldL1: ajustes.qteHoldL1, qteHoldL2: ajustes.qteHoldL2,
            qteHoldR1: ajustes.qteHoldR1, qteHoldR2: ajustes.qteHoldR2,
            qteStickMode: ajustes.qteStickMode,
            audioVolume: ajustes.audioVolume, audioMute: ajustes.audioMute,
            qteAuto: ajustes.qteAuto,
            qteHold: ajustes.qteHold, qteHoldButtons: ajustes.qteHoldButtons, qteHoldRate: ajustes.qteHoldRate,
            teclas: Teclas.cadena(Teclas.leer(ajustes.teclas)),
            mando: ajustes.mando ? Teclas.cadenaMando(Teclas.leerMando(ajustes.mando, ajustes.controlesDmc5)) : "",
            trucos: ajustes.trucos, idioma: Tema.idioma, textoJuego: ajustes.textoJuego
        }
        if (lanzador.iniciar(a, modPrep.env)) {
            playingRegional = !!elegido.regional
            if (ajustes.minimizarAlJugar) minimizarTrasArrancar.start()
        }
    }

    function ponerPortada(ruta) {
        var copia = lanzador.guardarPortada(ruta)
        if (copia.length > 0) {
            ajustes.portada = copia
            aviso(Tema.t("portadaHecha"))
        } else {
            aviso(Tema.t("portadaNoValida"))
        }
    }

    function quitarPortada() {
        lanzador.borrarPortada()
        ajustes.portada = ""
    }

    function aviso(texto) {
        tostada.texto = texto
        tostada.mostrar()
    }

    Timer {
        id: minimizarTrasArrancar
        interval: 600
        onTriggered: if (lanzador.jugando) ventana.showMinimized()
    }

    Connections {
        target: lanzador
        function onDiagnosticsExported(path) {
            dialogoError.texto = Tema.t("diagnosticsExported")
            dialogoError.detalle = path + "\n\n" + Tema.t("diagnosticsReportDesc")
            dialogoError.open()
        }
        function onJuegoTerminado(codigo, fallo, segundos, resumen) {
            ajustes.segundosJugados += segundos
            ajustes.ultimaSesion = segundos
            if (ventana.visibility === Window.Minimized) ventana.showNormal()
            ventana.raise()
            ventana.requestActivate()
            if (fallo) {
                dialogoError.texto = Tema.tf("terminadoFallo", codigo)
                dialogoError.detalle = resumen
                dialogoError.open()
            } else {
                ventana.aviso(Tema.tf("terminadoOk", Tema.duracion(segundos)))
                if (!playingRegional && ajustes.autoNative && !installer.running && installer.hasPendingNativeCode())
                    installer.run("native", { config: "Release" })
            }
        }
        function onError(clave, detalle) {
            dialogoError.texto = Tema.tf(clave, detalle)
            dialogoError.detalle = clave === "errorArranque" ? "" : detalle
            dialogoError.open()
        }
    }

    Component.onCompleted: {
        installer.checkUpdate() // a newer release on GitHub -> offered in the side bar
        // Settings version 2. Fast boot used to be on by default and ends the intro animation when the level
        // loads, which shortened the opening; it is turned off once.
        if (ajustes.versionAjustes < 2) {
            ajustes.arranqueRapido = false
            ajustes.versionAjustes = 2
        }
        // Version 3: 2x render resolution by default.
        if (ajustes.versionAjustes < 3) {
            ajustes.resolucionInterna = "2"
            ajustes.versionAjustes = 3
        }
        // Version 4 turned on a renderer switch that no longer exists.
        if (ajustes.versionAjustes < 4)
            ajustes.versionAjustes = 4
        // Version 5: movies skipped by default while the game was being optimised.
        if (ajustes.versionAjustes < 5) {
            ajustes.saltarVideos = true
            ajustes.versionAjustes = 5
        }
        // Version 6: the runtime plays the movies natively, with sound.
        if (ajustes.versionAjustes < 6) {
            ajustes.saltarVideos = false
            ajustes.versionAjustes = 6
        }
        // Version 7: native JIT always on, the duplicate "pixel" filter and fast boot removed from the interface, a
        // 120 FPS window limit (the game makes 60) brought to 60.
        if (ajustes.versionAjustes < 7) {
            ajustes.compilarAreas = true
            ajustes.jitInline = true
            ajustes.arranqueRapido = false
            if (ajustes.filtro === "pixel") ajustes.filtro = "bilineal"
            if (ajustes.fpsLimite === 120) ajustes.fpsLimite = 60
            ajustes.versionAjustes = 7
        }
        // Version 8: the old "stretch to window" on/off switch became the full TOBIICHI_ASPECTO selector
        // (auto / estirar / fixed ratios). Keep a saved stretch choice, otherwise stay on auto.
        if (ajustes.versionAjustes < 8) {
            if (ajustes.estirar) ajustes.presentacion = "estirar"
            ajustes.estirar = false
            ajustes.versionAjustes = 8
        }
        if (ajustes.idioma.length === 0) {
            ajustes.idioma = Textos.idiomaDeLocale(Qt.locale().name) // the system's language when the launcher has it
        }
        if (ajustes.aspecto.length === 0) ajustes.aspecto = aspectoPorDefecto()
        // A capture/test can request a specific starting tab; only fall back to Install for a normal launch.
        if (!listo && pestanaInicial <= 0) ventana.pagina = 1
        // "--jugar": starts the game right away with the saved settings (the shortcut's "Play now" action).
        if (Qt.application.arguments.indexOf("--jugar") >= 0 && listo)
            jugar()
    }

    // ---------------------------------------------------------------- Background
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#101217" }
            GradientStop { position: 1.0; color: Tema.fondo }
        }
    }
    Shape {
        // A crimson glow low on the right, under the hero.
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: 0
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: ventana.width * 0.78; centerY: ventana.height * 1.1
                centerRadius: ventana.height * 0.9
                focalX: centerX; focalY: centerY
                GradientStop { position: 0.0; color: "#5a1410" }
                GradientStop { position: 0.45; color: "#22100e" }
                GradientStop { position: 1.0; color: "transparent" }
            }
            startX: 0; startY: 0
            PathLine { x: ventana.width; y: 0 }
            PathLine { x: ventana.width; y: ventana.height }
            PathLine { x: 0; y: ventana.height }
            PathLine { x: 0; y: 0 }
        }
    }
    Ascuas {
        anchors.fill: parent
        anchors.leftMargin: lateral.width
        intensidad: lanzador.jugando ? 0.3 : 1.0
    }
    Rectangle {
        // Window frame.
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Tema.borde
        z: 10
    }

    // ---------------------------------------------------------------- Sidebar
    Rectangle {
        id: lateral
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 236
        color: Tema.lateral
        z: 4

        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: Tema.borde
        }
        DragHandler {
            target: null
            grabPermissions: PointerHandler.CanTakeOverFromAnything
            onActiveChanged: if (active) ventana.startSystemMove()
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 14
            anchors.topMargin: 22
            spacing: 4

            // Brand: the omega mark and the name.
            RowLayout {
                Layout.leftMargin: 6
                Layout.bottomMargin: 26
                spacing: 12
                Rectangle {
                    width: 40
                    height: 40
                    radius: 9
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#e0352a" }
                        GradientStop { position: 1.0; color: "#7a1610" }
                    }
                    Text {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: -1
                        text: "Ω"
                        color: "white"
                        font.family: Tema.fuenteTitulo
                        font.pixelSize: 24
                        font.weight: Font.Black
                    }
                }
                ColumnLayout {
                    spacing: 0
                    Text {
                        text: "GOD OF WAR"
                        color: "white"
                        font.family: Tema.fuenteTitulo
                        font.pixelSize: 16
                        font.weight: Font.Black
                        font.letterSpacing: 1.5
                    }
                    Text {
                        text: Tema.t("subtitulo")
                        color: Tema.oroClaro
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        font.letterSpacing: 3
                    }
                }
            }

            Repeater {
                model: [
                    { clave: "navInicio", icono: "" },
                    { clave: "pestInstalar", icono: "" },
                    { clave: "pestGrafico", icono: "" },
                    { clave: "pestRendimiento", icono: "" },
                    { clave: "pestControles", icono: "" },
                    { clave: "pestTrucos", icono: "" },
                    { clave: "pestOtros", icono: "" },
                    { clave: "pestPartidas", icono: "\uE74E" },
                    { clave: "pestAccessibility", icono: "\uE776" },
                    { clave: "pestMods", icono: "\uE9D9" }
                ]
                delegate: NavItem {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    text: Tema.t(modelData.clave)
                    glyph: modelData.icono
                    active: ventana.pagina === index
                    onClicked: ventana.pagina = index
                }
            }

            Item { Layout.fillHeight: true }

            // Status at the bottom of the sidebar.
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: columnaEstado.implicitHeight + 24
                radius: 8
                color: Tema.fondoAlto
                border.width: 1
                border.color: Tema.borde
                ColumnLayout {
                    id: columnaEstado
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 12
                    spacing: 6
                    RowLayout {
                        spacing: 8
                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: lanzador.jugando ? Tema.bien : (ventana.listo ? Tema.bien : Tema.aviso)
                            SequentialAnimation on opacity {
                                running: lanzador.jugando
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.3; duration: 700 }
                                NumberAnimation { to: 1.0; duration: 700 }
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: lanzador.jugando ? Tema.t("jugandoEstado") : (ventana.listo ? Tema.t("listo") : Tema.t("noInstalado"))
                            color: Tema.texto
                            font.pixelSize: 13
                            font.weight: Font.Medium
                            elide: Text.ElideRight
                        }
                    }
                    Text {
                        visible: lanzador.jugando
                        text: Tema.t("cerrarJuego")
                        color: zonaCerrar.containsMouse ? Tema.rojoClaro : Tema.textoSuave
                        font.pixelSize: 12
                        font.underline: zonaCerrar.containsMouse
                        MouseArea {
                            id: zonaCerrar
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: lanzador.detener()
                        }
                    }
                    Text {
                        text: "v" + Qt.application.version
                        color: Tema.textoTenue
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: ventana.actualizacion !== null
                        text: ventana.actualizacion ? "⬆  " + Tema.tf("actualizarA", ventana.actualizacion.version) : ""
                        color: zonaActualizar.containsMouse ? Tema.oroClaro : Tema.oro
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        font.underline: zonaActualizar.containsMouse
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        MouseArea {
                            id: zonaActualizar
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: dialogoActualizar.open()
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Loading screen (while the game is built)
    // Over the sidebar and the pages, under the title bar (z 5), so the window can still be moved, minimised or closed.
    LoadingScreen {
        anchors.fill: parent
        z: 4.5
        portada: ajustes.portada
        onJugar: { ventana.pagina = 0; ventana.jugar() }
    }

    // ---------------------------------------------------------------- Title bar (window buttons, drag area)
    Item {
        id: barra
        anchors.left: lateral.right
        anchors.right: parent.right
        anchors.top: parent.top
        height: 40
        z: 5

        DragHandler {
            target: null
            grabPermissions: PointerHandler.CanTakeOverFromAnything
            onActiveChanged: if (active) ventana.startSystemMove()
        }

        Row {
            anchors.right: parent.right
            anchors.top: parent.top
            height: parent.height
            Repeater {
                model: [{ simbolo: "minimizar", accion: 0 }, { simbolo: "cerrar", accion: 1 }]
                delegate: Rectangle {
                    id: botonVentana
                    required property var modelData
                    width: 48
                    height: barra.height
                    color: zona.containsMouse ? (modelData.accion === 1 ? "#c42b1c" : "#1fffffff") : "transparent"
                    Canvas {
                        anchors.centerIn: parent
                        width: 12
                        height: 12
                        property bool cerrar: botonVentana.modelData.accion === 1
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = "#dfe2e8"
                            ctx.lineWidth = 1.2
                            ctx.beginPath()
                            if (cerrar) {
                                ctx.moveTo(1, 1); ctx.lineTo(11, 11)
                                ctx.moveTo(11, 1); ctx.lineTo(1, 11)
                            } else {
                                ctx.moveTo(1, 6.5); ctx.lineTo(11, 6.5)
                            }
                            ctx.stroke()
                        }
                    }
                    MouseArea {
                        id: zona
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: botonVentana.modelData.accion === 1 ? ventana.close() : ventana.showMinimized()
                    }
                    ToolTip.visible: zona.containsMouse
                    ToolTip.delay: 600
                    ToolTip.text: Tema.t(modelData.simbolo)
                }
            }
        }
    }

    // ---------------------------------------------------------------- Pages
    StackLayout {
        id: paginas
        anchors.left: lateral.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        currentIndex: ventana.pagina

        // Home: hero with the cover, the title, Play, the language and a summary of the settings.
        Item {
            id: inicio

            // The user's cover image. Opaque: covers the area without distortion and fades into the background at the
            // edges. Cut-out (transparent background): a figure on the right, with a red aura.
            Item {
                id: marcoImagen
                readonly property bool figura: ventana.portadaRecorte
                anchors.fill: parent
                clip: true
                visible: imagenPortada.status === Image.Ready
                Image {
                    id: imagenPortada
                    readonly property real escala: !(implicitWidth > 0 && implicitHeight > 0) ? 1
                        : marcoImagen.figura ? marcoImagen.height * 0.95 / implicitHeight
                        : Math.max(marcoImagen.width / implicitWidth, marcoImagen.height / implicitHeight)
                    readonly property real sobrante: Math.max(0, height - marcoImagen.height)
                    source: ajustes.portada.length > 0 ? lanzador.urlDesdeRuta(ajustes.portada) : ""
                    asynchronous: true
                    cache: false
                    smooth: true
                    mipmap: true
                    visible: false
                    width: implicitWidth * escala
                    height: implicitHeight * escala
                    x: marcoImagen.figura ? marcoImagen.width * 0.72 - width / 2 : (marcoImagen.width - width) / 2
                    // Opaque: 0 = the bottom of the image at the very top; 1 = moved down by 40 % of the area.
                    // Figure: its top between the top edge (0) and 62 % of the area (1).
                    y: marcoImagen.figura ? marcoImagen.height * 0.62 * ajustes.portadaFoco
                                          : -sobrante + ajustes.portadaFoco * (sobrante + marcoImagen.height * 0.4)
                }
                Rectangle {
                    // Mask: the bottom of a figure fades out above the title.
                    id: mascaraPortada
                    x: imagenPortada.x
                    y: imagenPortada.y
                    width: imagenPortada.width
                    height: imagenPortada.height
                    visible: false
                    layer.enabled: true
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "white" }
                        GradientStop { position: marcoImagen.figura ? 0.7 : 0.98; color: "white" }
                        GradientStop { position: 1.0; color: marcoImagen.figura ? "transparent" : "white" }
                    }
                }
                MultiEffect {
                    x: imagenPortada.x
                    y: imagenPortada.y
                    width: imagenPortada.width
                    height: imagenPortada.height
                    source: imagenPortada
                    maskEnabled: true
                    maskSource: mascaraPortada
                    // Without spread the mask is a hard threshold; this way it follows the gradient.
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1.0
                    brightness: marcoImagen.figura ? (ajustes.portadaBrillo - 1.0) * 0.6 : 0
                    shadowEnabled: marcoImagen.figura
                    shadowColor: "#e0352a"
                    shadowBlur: 1.0
                    shadowOpacity: 0.8
                    shadowHorizontalOffset: 0
                    shadowVerticalOffset: 0
                    blurMax: 56
                    opacity: imagenPortada.status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
                }
                Rectangle {
                    visible: !marcoImagen.figura
                    anchors.fill: parent
                    color: Tema.fondo
                    opacity: 1 - ajustes.portadaBrillo
                }
                Rectangle {
                    // Dark on the left (title and buttons) and at the bottom; the image shows top right.
                    anchors.fill: parent
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#f00b0c0f" }
                        GradientStop { position: 0.45; color: "#a00b0c0f" }
                        GradientStop { position: 1.0; color: "#100b0c0f" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#600b0c0f" }
                        GradientStop { position: 0.3; color: "#000b0c0f" }
                        GradientStop { position: 0.62; color: "#300b0c0f" }
                        GradientStop { position: 1.0; color: "#f80b0c0f" }
                    }
                }
            }

            Shape {
                // Without a cover: Kratos' tattoo as two crimson blades across the right side.
                visible: !marcoImagen.visible
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                opacity: 0.85
                ShapePath {
                    strokeWidth: 0
                    strokeColor: "transparent"
                    fillGradient: LinearGradient {
                        x1: inicio.width * 0.55; y1: 0
                        x2: inicio.width; y2: inicio.height
                        GradientStop { position: 0.0; color: "#00c62a20" }
                        GradientStop { position: 0.5; color: "#55c62a20" }
                        GradientStop { position: 1.0; color: "#10c62a20" }
                    }
                    startX: inicio.width * 0.62; startY: 0
                    PathLine { x: inicio.width * 0.80; y: 0 }
                    PathLine { x: inicio.width * 0.52; y: inicio.height }
                    PathLine { x: inicio.width * 0.40; y: inicio.height }
                    PathLine { x: inicio.width * 0.62; y: 0 }
                }
                ShapePath {
                    strokeWidth: 0
                    strokeColor: "transparent"
                    fillGradient: LinearGradient {
                        x1: inicio.width * 0.8; y1: 0
                        x2: inicio.width; y2: inicio.height
                        GradientStop { position: 0.0; color: "#00c62a20" }
                        GradientStop { position: 0.6; color: "#33c62a20" }
                        GradientStop { position: 1.0; color: "#00c62a20" }
                    }
                    startX: inicio.width * 0.86; startY: 0
                    PathLine { x: inicio.width * 0.92; y: 0 }
                    PathLine { x: inicio.width * 0.68; y: inicio.height }
                    PathLine { x: inicio.width * 0.62; y: inicio.height }
                    PathLine { x: inicio.width * 0.86; y: 0 }
                }
            }
            Text {
                // Large faint omega behind the blades.
                visible: !marcoImagen.visible
                anchors.right: parent.right
                anchors.rightMargin: 40
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -50
                text: "Ω"
                font.family: Tema.fuenteTitulo
                font.pixelSize: 420
                font.weight: Font.Black
                color: "#0cffffff"
            }

            ColumnLayout {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 56
                anchors.rightMargin: 56
                anchors.bottomMargin: 44
                spacing: 0

                RowLayout {
                    spacing: 10
                    Rectangle { width: 28; height: 3; color: Tema.oro }
                    Text {
                        text: Tema.t("plataforma")
                        color: Tema.oroClaro
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        font.letterSpacing: 4
                    }
                }
                Text {
                    Layout.topMargin: 8
                    text: "GOD OF WAR"
                    color: "white"
                    font.family: Tema.fuenteTitulo
                    font.pixelSize: 82
                    font.weight: Font.Black
                    font.letterSpacing: -1
                    layer.enabled: true
                    layer.effect: MultiEffect {
                        shadowEnabled: true
                        shadowColor: "#000000"
                        shadowBlur: 0.6
                        shadowOpacity: 0.6
                        shadowVerticalOffset: 4
                    }
                }
                Text {
                    Layout.topMargin: 2
                    Layout.maximumWidth: 520
                    text: Tema.t("lema")
                    color: Tema.textoSuave
                    font.pixelSize: 16
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.topMargin: 30
                    spacing: 18
                    BotonJugar {
                        Layout.preferredWidth: 290
                        listo: ventana.listo
                        jugando: lanzador.jugando
                        text: lanzador.jugando ? Tema.t("jugando") : Tema.t("jugar")
                        onClicked: if (!lanzador.jugando) ventana.jugar()
                    }
                    // Game language: one pill per prepared disc (Other -> Game text has the same setting).
                    ColumnLayout {
                        visible: ventana.idiomasJuego.length > 0
                        spacing: 6
                        Text {
                            text: Tema.t("cardIdioma")
                            color: Tema.textoTenue
                            font.pixelSize: 11
                            font.weight: Font.Bold
                            font.letterSpacing: 2
                        }
                        Flow {
                            Layout.preferredWidth: 420
                            spacing: 6
                            Repeater {
                                model: ventana.idiomasJuego
                                delegate: Rectangle {
                                    id: pildora
                                    required property var modelData
                                    readonly property bool elegida: ajustes.textoJuego === modelData.language
                                    height: 32
                                    width: textoPildora.implicitWidth + 26
                                    radius: 16
                                    color: elegida ? "#3a1714" : (zonaPildora.containsMouse ? Tema.panelClaro : "#a0121419")
                                    border.width: 1
                                    border.color: elegida ? Tema.oro : Tema.bordeClaro
                                    Text {
                                        id: textoPildora
                                        anchors.centerIn: parent
                                        text: pildora.modelData.label.split(" — ")[0]
                                        color: pildora.elegida ? "white" : Tema.textoSuave
                                        font.pixelSize: 13
                                        font.weight: pildora.elegida ? Font.DemiBold : Font.Normal
                                    }
                                    MouseArea {
                                        id: zonaPildora
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: ajustes.textoJuego = pildora.modelData.language
                                    }
                                    ToolTip.visible: zonaPildora.containsMouse
                                    ToolTip.delay: 500
                                    ToolTip.text: pildora.modelData.label
                                }
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.topMargin: 16
                    spacing: 14
                    Text {
                        text: Tema.t("pistaF1")
                        color: Tema.textoSuave
                        font.pixelSize: 13
                        font.letterSpacing: 0.3
                    }
                    // an installed game without the profile-guided build: point to the step that adds it
                    Text {
                        visible: lanzador.sistema !== "linux" && ventana.listo && !ventana.selectedRegional && !ventana.pgoAtivo
                        text: "▲  " + Tema.t("pgoRecomendado")
                        color: zonaPgo.containsMouse ? Tema.oroClaro : Tema.oro
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        MouseArea {
                            id: zonaPgo
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: ventana.pagina = 1
                        }
                    }
                }

                // Summary cards.
                RowLayout {
                    Layout.topMargin: 14
                    Layout.fillWidth: true
                    spacing: 12
                    Repeater {
                        model: [
                            { titulo: Tema.t("cardPerfil"),
                              valor: Tema.t(ventana.perfilTexto()),
                              detalle: ventana.escalaElegida() + "× · " + (512 * ventana.escalaElegida()) + "×" + (448 * ventana.escalaElegida()),
                              pagina: 2 },
                            { titulo: Tema.t("cardImagen"),
                              valor: Tema.t(ajustes.modoPantalla === "sin_bordes" ? "sinBordes"
                                            : ajustes.modoPantalla === "completa" ? "completa" : "ventana"),
                              detalle: (ajustes.modoPantalla !== "ventana" ? ventana.pantalla.ancho + "×" + ventana.pantalla.alto
                                                                          : ajustes.ancho + "×" + ajustes.alto) + " · " + ajustes.aspecto,
                              pagina: 2 },
                            { titulo: Tema.t("cardControles"),
                              valor: mando.conectado ? Tema.t("cardMando") : Tema.t("cardTeclado"),
                              detalle: mando.conectado ? mando.nombre : Tema.t("cardTecladoDet"),
                              pagina: 4 },
                            { titulo: Tema.t("cardTiempo"),
                              valor: ajustes.segundosJugados > 0 ? Tema.duracion(ajustes.segundosJugados) : "—",
                              detalle: ajustes.ultimaSesion > 0 ? Tema.tf("ultimaSesion", Tema.duracion(ajustes.ultimaSesion)) : Tema.t("sinJugar"),
                              pagina: -1 }
                        ]
                        delegate: Rectangle {
                            id: tarjeta
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            implicitHeight: 84
                            radius: 10
                            color: zonaTarjeta.containsMouse && modelData.pagina >= 0 ? "#e61c1f26" : "#c0121419"
                            border.width: 1
                            border.color: zonaTarjeta.containsMouse && modelData.pagina >= 0 ? Tema.bordeClaro : Tema.borde
                            Behavior on color { ColorAnimation { duration: 120 } }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                anchors.leftMargin: 16
                                spacing: 2
                                Text {
                                    text: tarjeta.modelData.titulo.toLocaleUpperCase()
                                    color: Tema.textoTenue
                                    font.pixelSize: 11
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.5
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tarjeta.modelData.valor
                                    color: "white"
                                    font.pixelSize: 20
                                    font.weight: Font.Bold
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tarjeta.modelData.detalle
                                    color: Tema.textoSuave
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                            }
                            MouseArea {
                                id: zonaTarjeta
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: tarjeta.modelData.pagina >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: if (tarjeta.modelData.pagina >= 0) ventana.pagina = tarjeta.modelData.pagina
                            }
                        }
                    }
                }
            }
        }

        // Settings pages: a large title over a panel.
        Repeater {
            model: ["pestInstalar", "pestGrafico", "pestRendimiento", "pestControles", "pestTrucos", "pestOtros",
                    "pestPartidas", "pestAccessibility", "pestMods"]
            delegate: Item {
                id: hojaAjustes
                required property string modelData
                required property int index
                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 40
                    anchors.rightMargin: 40
                    anchors.topMargin: 34
                    anchors.bottomMargin: 30
                    spacing: 18
                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: Tema.t(hojaAjustes.modelData)
                            color: "white"
                            font.family: Tema.fuenteTitulo
                            font.pixelSize: 30
                            font.weight: Font.Black
                        }
                        Rectangle { width: 36; height: 3; radius: 1; color: Tema.oro }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 12
                        color: Tema.panel
                        border.width: 1
                        border.color: Tema.borde
                        Loader {
                            anchors.fill: parent
                            anchors.margins: 24
                            anchors.rightMargin: 14
                            sourceComponent: [paginaInstalar, paginaGrafico, paginaRendimiento, paginaControles,
                                              paginaTrucos, paginaOtros, paginaPartidas, accessibilityPage,
                                              paginaMods][hojaAjustes.index]
                        }
                    }
                }
            }
        }
    }

    Component {
        id: accessibilityPage
        AccessibilityPage {
            settings: ventana.ajustesGuardados
            onOpenControls: ventana.pagina = 4
        }
    }

    Component {
        id: paginaMods
        PaginaMods {
            settings: ventana.ajustesGuardados
            modelo: modeloMods
            onAviso: (texto) => ventana.aviso(texto)
            onFallo: (texto, detalle) => {
                dialogoError.texto = texto
                dialogoError.detalle = detalle
                dialogoError.open()
            }
        }
    }

    Component {
        id: paginaInstalar
        InstallPage {
            onSelectRegion: function(selection) {
                ventana.refrescarInstalacion()
                ajustes.textoJuego = selection
                ventana.pagina = 0
            }
        }
    }
    Component {
        id: paginaGrafico
        PaginaGrafico {
            ajustes: ventana.ajustesGuardados
            tarjetas: ventana.tarjetas
            pantalla: ventana.pantalla
            gpuPerdida: ventana.gpuPerdida
            escalaAuto: ventana.escalaAuto()
        }
    }
    Component {
        id: paginaRendimiento
        PaginaRendimiento {
            ajustes: ventana.ajustesGuardados
            pantalla: ventana.pantalla
        }
    }
    Component {
        id: paginaControles
        PaginaControles {
            ajustes: ventana.ajustesGuardados
        }
    }
    Component {
        id: paginaTrucos
        PaginaTrucos {
            ajustes: ventana.ajustesGuardados
        }
    }
    Component {
        id: paginaOtros
        PaginaOtros {
            ajustes: ventana.ajustesGuardados
            idiomasJuego: ventana.idiomasJuego
            onRestablecer: ventana.restablecer()
            onAviso: (t) => ventana.aviso(t)
            onPonerPortada: (r) => ventana.ponerPortada(r)
            onQuitarPortada: ventana.quitarPortada()
        }
    }

    Component {
        id: paginaPartidas
        PaginaPartidas {
            enabled: !!ventana.selectedGame
            carpeta: ventana.carpetaPartidas
            elf: ventana.selectedGame ? ventana.selectedGame.elf : ""
            onAviso: (t) => ventana.aviso(t)
            onIniciarSlot: ventana.jugar()
        }
    }

    // gow-native-pc: with several prepared languages and none chosen yet, ask once (Other -> Game text changes it)
    Popup {
        id: preguntaIdioma
        modal: true
        anchors.centerIn: parent
        width: 420
        padding: 24
        background: Rectangle { color: Tema.fondoAlto; border.color: Tema.bordeClaro; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: Tema.t("langQuestion"); color: Tema.oroClaro; font.pixelSize: 17; font.family: Tema.fuenteTitulo }
            Repeater {
                model: ventana.idiomasJuego
                delegate: BotonSecundario {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.label
                    onClicked: { ajustes.textoJuego = modelData.language; preguntaIdioma.close(); ventana.jugar() }
                }
            }
            Text {
                text: Tema.t("langRemember"); color: Tema.textoTenue; font.pixelSize: 12
                Layout.fillWidth: true; wrapMode: Text.WordWrap
            }
        }
    }

    // Dropping an image on the window makes it the cover.
    DropArea {
        id: zonaSoltar
        anchors.fill: parent
        z: 30
        onEntered: (drag) => drag.accepted = drag.hasUrls
        onDropped: (drop) => {
            if (drop.hasUrls && drop.urls.length > 0)
                ventana.ponerPortada(lanzador.rutaDesdeUrl(drop.urls[0]))
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 14
            visible: zonaSoltar.containsDrag
            radius: 10
            color: "#b30a0605"
            border.width: 2
            border.color: Tema.oro
            Text {
                anchors.centerIn: parent
                text: Tema.t("portadaSoltar")
                color: Tema.oroClaro
                font.family: Tema.fuenteTitulo
                font.pixelSize: 26
                font.weight: Font.Bold
                font.letterSpacing: 2
            }
        }
    }

    // Resize grip.
    MouseArea {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: 18
        height: 18
        z: 11
        cursorShape: Qt.SizeFDiagCursor
        onPressed: ventana.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
    }

    // ---------------------------------------------------------------- Notices
    Rectangle {
        id: tostada
        property string texto
        function mostrar() {
            animacionTostada.restart()
        }
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height - 70
        z: 20
        width: textoTostada.implicitWidth + 36
        height: 40
        radius: 8
        color: "#ee14161b"
        border.width: 1
        border.color: Tema.oro
        opacity: 0
        visible: opacity > 0
        Text {
            id: textoTostada
            anchors.centerIn: parent
            text: tostada.texto
            color: Tema.oroClaro
            font.pixelSize: 14
        }
        SequentialAnimation {
            id: animacionTostada
            NumberAnimation { target: tostada; property: "opacity"; to: 1; duration: 180 }
            PauseAnimation { duration: 4200 }
            NumberAnimation { target: tostada; property: "opacity"; to: 0; duration: 400 }
        }
    }

    Popup {
        id: dialogoError
        property string texto
        property string detalle
        anchors.centerIn: Overlay.overlay
        width: 560
        modal: true
        padding: 24
        Overlay.modal: Rectangle { color: "#a0000000" }
        background: Rectangle {
            radius: 6
            color: Tema.fondoAlto
            border.width: 1
            border.color: Tema.mal
        }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                text: dialogoError.texto
                color: Tema.texto
                font.pixelSize: 15
                font.weight: Font.Medium
                wrapMode: Text.WordWrap
            }
            Rectangle {
                visible: dialogoError.detalle.length > 0
                Layout.fillWidth: true
                implicitHeight: textoDetalle.implicitHeight + 20
                radius: 4
                color: Tema.lateral
                border.width: 1
                border.color: Tema.borde
                Text {
                    id: textoDetalle
                    anchors.fill: parent
                    anchors.margins: 10
                    text: dialogoError.detalle
                    color: Tema.textoSuave
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: Text.WrapAnywhere
                }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 8
                BotonSecundario {
                    text: Tema.t("verRegistro")
                    onClicked: lanzador.abrirRegistro()
                }
                BotonSecundario {
                    text: Tema.t("diagnosticsExport")
                    onClicked: lanzador.exportDiagnostics()
                }
                BotonSecundario {
                    text: Tema.t("entendido")
                    onClicked: dialogoError.close()
                }
            }
        }
    }

    Popup {
        id: dialogoActualizar
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 520
        modal: true
        padding: 24
        background: Rectangle { color: "#14161b"; radius: 8; border.width: 1; border.color: Tema.oro }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                text: ventana.actualizacion ? Tema.tf("actualizarTitulo", ventana.actualizacion.version) : ""
                color: Tema.oroClaro
                font.pixelSize: 18
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Tema.textoSuave
                font.pixelSize: 13
                text: lanzador.jugando ? Tema.t("actualizarJugando")
                    : (ventana.actualizacion && ventana.actualizacion.url ? Tema.t("actualizarDesc") : Tema.t("actualizarSinZip"))
            }
            RowLayout {
                spacing: 10
                BotonSecundario {
                    text: Tema.t("actualizarAhora")
                    visible: ventana.actualizacion && ventana.actualizacion.url
                    enabled: !lanzador.jugando && !installer.running
                    onClicked: installer.applyUpdate(ventana.actualizacion.url, ventana.actualizacion.sha256, ventana.actualizacion.version)
                }
                BotonSecundario {
                    text: Tema.t("actualizarNovedades")
                    onClicked: Qt.openUrlExternally(ventana.actualizacion.page)
                }
                Item { Layout.fillWidth: true }
                BotonSecundario { text: Tema.t("instCancel"); onClicked: dialogoActualizar.close() }
            }
        }
    }
}
