import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Shapes
import "Teclas.js" as Teclas

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
    // The Settings object for the pages: inside their Components "ajustes" names the page's own property.
    readonly property var ajustesGuardados: ajustes

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
        property bool fxaa: true
        property string anisotropico: "1" // anisotropic texture filtering: 1 = off, 2..16 (GOW_ANISO)
        property string resolucionInterna: "2" // "auto" (from the display) or "1".."8" (PS2X_GS_ESCALA)
        property bool escalaDinamica: true // lowers the resolution when the GPU cannot keep 60 (PS2X_GS_ESCALA_DINAMICA)
        property bool dibujoHardware: true // triangles through the GPU pipeline (PS2X_GS_HW, experimental)
        property bool imagenNitida: true // no line doubling or anti-flicker (PS2X_GS_NITIDO)
        property int fpsLimite: 120
        property bool vsync: false
        property bool mostrarFps: false
        property string elf: ""
        property string iso: ""
        property string ejecutable: ""
        property bool saltarVideos: true // skip the pre-rendered movies
        property bool arranqueRapido: false // used to shorten the game's opening (see Component.onCompleted)
        property int versionAjustes: 0
        property bool controlesDmc5: true
        property bool cancelarAnimaciones: true // snappier evade and input buffer (GOW_CANCELAR)
        // gow-native-pc: accessibility — holding a button instead of mashing it in the minigames (GOW_QTE_HOLD)
        property bool qteHold: false
        property string qteHoldButtons: "circle" // "circle" or "face" (the four face buttons)
        property int qteHoldRate: 10 // presses per second the assist makes (GOW_QTE_HOLD_HZ)
        property bool escSalir: false
        property bool minimizarAlJugar: true
        property int segundosJugados: 0
        property int ultimaSesion: 0
        property string portada: ""
        property string teclas: "" // key map as JSON (empty = default layout)
        property string mando: "" // controller layout as JSON (empty = the fixed layout of controlesDmc5)
        property string trucos: "" // cheats active at start, comma separated (gow_trucos.cpp)
        property string textoJuego: "" // game language: a "language" of installer.languages() (e.g. "en", "pt-BR"); empty = ask
        property real portadaFoco: 0.55
        property real portadaBrillo: 0.85
    }

    Binding { target: Tema; property: "idioma"; value: ajustes.idioma || "en" }
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
    readonly property bool listo: ejecutableJuego.length > 0 && idiomasJuego.length > 0
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
        var alto = ajustes.modoPantalla === "completa" ? pantalla.alto : ajustes.alto
        return Math.max(2, Math.min(8, Math.floor(alto / 448)))
    }
    function escalaElegida() {
        var n = parseInt(ajustes.resolucionInterna)
        return ajustes.resolucionInterna === "auto" || isNaN(n) ? escalaAuto() : Math.max(1, Math.min(8, n))
    }
    function textoEscala(n) {
        return n + "× · " + (512 * n) + "×" + (448 * n)
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
        ajustes.filtro = "bilineal"
        ajustes.nitidez = 0.8
        ajustes.fxaa = true
        ajustes.anisotropico = "1"
        ajustes.resolucionInterna = "2"
        ajustes.escalaDinamica = true
        ajustes.dibujoHardware = true
        ajustes.imagenNitida = true
        ajustes.fpsLimite = 120
        ajustes.vsync = false
        ajustes.mostrarFps = false
        ajustes.saltarVideos = true
        ajustes.arranqueRapido = false
        ajustes.controlesDmc5 = true
        ajustes.mando = ""
        ajustes.cancelarAnimaciones = true
        ajustes.qteHold = false
        ajustes.qteHoldButtons = "circle"
        ajustes.qteHoldRate = 10
        ajustes.escSalir = false
        ajustes.minimizarAlJugar = true
        ajustes.trucos = ""
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
        refrescarInstalacion()
        if (!listo) { aviso(Tema.t("instNotReady")); ventana.pagina = 1; return }
        // gow-native-pc: without the first-play preparation the vector-unit code still runs interpreted: say so instead of
        // letting the first minutes look frozen
        if (!installer.firstPlayPrepared()) aviso(Tema.t("firstPlayNotice"))
        var elegido = idiomaJuego(ajustes.textoJuego)
        if (!elegido) {
            if (idiomasJuego.length > 1) { preguntaIdioma.open(); return }
            elegido = idiomasJuego[0]
            ajustes.textoJuego = elegido.language
        }
        var a = {
            gpu: gpuPerdida ? "auto" : ajustes.gpu,
            modoPantalla: ajustes.modoPantalla,
            ancho: ajustes.ancho, alto: ajustes.alto,
            aspecto: ajustes.aspecto, estirar: ajustes.estirar,
            filtro: ajustes.filtro, nitidez: ajustes.nitidez, fxaa: ajustes.fxaa, anisotropico: ajustes.anisotropico,
            escala: escalaElegida(), escalaDinamica: ajustes.escalaDinamica, imagenNitida: ajustes.imagenNitida,
            dibujoHardware: ajustes.dibujoHardware,
            fpsLimite: ajustes.fpsLimite, vsync: ajustes.vsync, mostrarFps: ajustes.mostrarFps,
            elf: elegido.elf, iso: "", ejecutable: ejecutableJuego,
            // new VU1 microcode met while playing is recorded; the Install tab compiles it ("Speed up visited areas")
            capturaVu1: installer.repoRoot + "/data/" + installer.gameId + "/vu1_capture",
            saltarVideos: ajustes.saltarVideos, arranqueRapido: ajustes.arranqueRapido,
            controlesDmc5: ajustes.controlesDmc5, escSalir: ajustes.escSalir,
            cancelarAnimaciones: ajustes.cancelarAnimaciones,
            qteHold: ajustes.qteHold, qteHoldButtons: ajustes.qteHoldButtons, qteHoldRate: ajustes.qteHoldRate,
            teclas: Teclas.cadena(Teclas.leer(ajustes.teclas)),
            mando: ajustes.mando ? Teclas.cadenaMando(Teclas.leerMando(ajustes.mando, ajustes.controlesDmc5)) : "",
            trucos: ajustes.trucos, idioma: Tema.idioma, textoJuego: ajustes.textoJuego
        }
        if (lanzador.iniciar(a) && ajustes.minimizarAlJugar)
            minimizarTrasArrancar.start()
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
        // Version 3: 2x render resolution by default, with the dynamic resolution that protects 60 FPS.
        if (ajustes.versionAjustes < 3) {
            ajustes.resolucionInterna = "2"
            ajustes.escalaDinamica = true
            ajustes.versionAjustes = 3
        }
        // Version 4: the hardware triangle renderer, turned on once.
        if (ajustes.versionAjustes < 4) {
            ajustes.dibujoHardware = true
            ajustes.versionAjustes = 4
        }
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
        if (ajustes.idioma.length === 0) {
            var loc = Qt.locale().name
            ajustes.idioma = loc.indexOf("tr") === 0 ? "tr" : (loc.indexOf("es") === 0 ? "es"
                           : (loc.indexOf("pt") === 0 ? "pt" : "en"))
        }
        if (ajustes.aspecto.length === 0) ajustes.aspecto = aspectoPorDefecto()
        if (!listo) ventana.pagina = 1  // nothing installed yet: open on the Install tab
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
                    { clave: "pestOtros", icono: "" }
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

                // Summary cards.
                RowLayout {
                    Layout.topMargin: 30
                    Layout.fillWidth: true
                    spacing: 12
                    Repeater {
                        model: [
                            { titulo: Tema.t("cardImagen"),
                              valor: ajustes.modoPantalla === "completa" ? Tema.t("completa") : Tema.t("ventana"),
                              detalle: (ajustes.modoPantalla === "completa" ? ventana.pantalla.ancho + "×" + ventana.pantalla.alto
                                                                          : ajustes.ancho + "×" + ajustes.alto) + " · " + ajustes.aspecto,
                              pagina: 2 },
                            { titulo: Tema.t("cardEscala"),
                              valor: ventana.escalaElegida() + "×",
                              detalle: (512 * ventana.escalaElegida()) + "×" + (448 * ventana.escalaElegida()) + (ajustes.escalaDinamica ? " · " + Tema.t("dinamicaCorta") : ""),
                              pagina: 2 },
                            { titulo: Tema.t("cardFps"),
                              valor: ajustes.fpsLimite > 0 ? ajustes.fpsLimite + " FPS" : Tema.t("sinLimite"),
                              detalle: ajustes.vsync ? "VSync" : Tema.t("cardJuego60"),
                              pagina: 3 },
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
            model: ["pestInstalar", "pestGrafico", "pestRendimiento", "pestControles", "pestTrucos", "pestOtros"]
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
                                              paginaTrucos, paginaOtros][hojaAjustes.index]
                        }
                    }
                }
            }
        }
    }

    Component {
        id: paginaInstalar
        InstallPage {}
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
