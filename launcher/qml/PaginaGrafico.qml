import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// "Graphics" tab: card, display mode, resolution, aspect ratio and scaling, plus every texture,
// presentation and renderer switch the runtime reads (the advanced ones are folded away by default).
ScrollView {
    id: raiz
    required property var ajustes
    required property var tarjetas
    required property var pantalla
    required property bool gpuPerdida
    required property int escalaAuto
    contentWidth: availableWidth
    clip: true

    // Full screen and borderless both use the monitor's own resolution.
    readonly property bool completa: ajustes.modoPantalla !== "ventana"
    readonly property bool avanzado: ajustes.verAvanzado

    // Quick profiles: each one is a set of the settings below; any other combination shows as "Custom".
    readonly property var perfiles: ({
        // Low-spec tier: half the PS2 frame (256x224) drawn into the window. On an i3-4170 + HD 4400 this is the
        // difference between ~24 and ~40 guest fps, because the cost lives in the GS, not in the VU1.
        bajo: { resolucionInterna: "0.5", filtro: "bilineal", fxaa: false, anisotropico: "1" },
        desempenho: { resolucionInterna: "1", filtro: "fsr", fxaa: false, anisotropico: "1" },
        equilibrado: { resolucionInterna: "2", filtro: "fsr", fxaa: true, anisotropico: "4" },
        qualidade: { resolucionInterna: "auto", filtro: "fsr", fxaa: true, anisotropico: "16" }
    })
    readonly property string perfilActual: {
        for (var nombre in perfiles) {
            var p = perfiles[nombre]
            if (ajustes.resolucionInterna === p.resolucionInterna && ajustes.filtro === p.filtro && ajustes.fxaa === p.fxaa
                    && ajustes.anisotropico === p.anisotropico)
                return nombre
        }
        return "personalizado"
    }
    function aplicarPerfil(nombre) {
        var p = perfiles[nombre]
        if (!p) return
        ajustes.resolucionInterna = p.resolucionInterna
        ajustes.filtro = p.filtro
        ajustes.fxaa = p.fxaa
        ajustes.anisotropico = p.anisotropico
    }

    component Grupo: Text {
        Layout.topMargin: 22
        Layout.bottomMargin: 2
        color: Tema.oro
        font.family: Tema.fuenteTitulo
        font.pixelSize: 13
        font.weight: Font.Bold
        font.letterSpacing: 2
    }
    readonly property real aspectoPantalla: pantalla.ancho / pantalla.alto

    function nombreTarjeta(t) {
        if (lanzador.sistema === "windows")
            return t.id === "ahorro" ? Tema.t("gpuAhorro") : Tema.t("gpuRendimiento")
        return t.fabricante + " " + t.nombre
    }

    readonly property var opcionesGpu: {
        var lista = [{ texto: Tema.t("gpuAuto"), valor: "auto" }]
        for (var i = 0; i < tarjetas.length; ++i) {
            var t = tarjetas[i]
            var tipo = t.tipo ? Tema.t(t.tipo) : ""
            lista.push({ texto: nombreTarjeta(t), valor: t.id, detalle: tipo + (lanzador.sistema === "linux" ? "  ·  " + t.id : "") })
        }
        return lista
    }

    readonly property var opcionesResolucion: {
        var comunes = [[1024, 768], [1280, 720], [1280, 800], [1280, 960], [1366, 768], [1440, 900], [1600, 900], [1600, 1200],
                       [1680, 1050], [1920, 1080], [1920, 1200], [2560, 1080], [2560, 1440], [2560, 1600], [3440, 1440], [3840, 2160]]
        var lista = []
        for (var i = 0; i < comunes.length; ++i) {
            var w = comunes[i][0], h = comunes[i][1]
            if (w > pantalla.ancho || h > pantalla.alto) continue
            var nativa = w === pantalla.ancho && h === pantalla.alto
            lista.push({ texto: w + " × " + h + (nativa ? "  (" + Tema.t("nativa") + ")" : ""), valor: w + "x" + h })
        }
        var clave = pantalla.ancho + "x" + pantalla.alto
        var esta = false
        for (var j = 0; j < lista.length; ++j) if (lista[j].valor === clave) esta = true
        if (!esta) lista.push({ texto: pantalla.ancho + " × " + pantalla.alto + "  (" + Tema.t("nativa") + ")", valor: clave })
        return lista
    }

    function textoEscala(n) {
        return n + "× · " + Math.round(512 * n) + "×" + Math.round(448 * n)
    }

    readonly property var opcionesEscala: {
        var lista = [{ texto: Tema.tf("internaAuto", textoEscala(raiz.escalaAuto)), valor: "auto" }]
        // Fixed steps, including the ones below 1x: the renderer accepts 0.25..4 and on an integrated GPU the whole
        // difference between 24 and 40 guest fps lives between 1x and 0.7x.
        var pasos = [0.35, 0.5, 0.7, 1, 1.5, 2, 3]
        for (var i = 0; i < pasos.length; ++i) {
            var n = pasos[i]
            var detalle = n === 1 ? Tema.t("internaNativa") : (n < 1 ? Tema.t("internaBaja") : (n >= 3 ? Tema.t("internaPesada") : ""))
            lista.push({ texto: textoEscala(n), valor: String(n), detalle: detalle })
        }
        return lista
    }

    function marcaPantalla(a) {
        return Math.abs(a - aspectoPantalla) < 0.04 ? "  ·  " + Tema.t("aspectoPantalla") : ""
    }

    ColumnLayout {
        width: raiz.availableWidth
        spacing: 0

        Fila {
            titulo: Tema.t("perfil")
            descripcion: Tema.t("perfilDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("perfilBajo"), valor: "bajo", detalle: Tema.t("perfilBajoDet") },
                    { texto: Tema.t("perfilDesempenho"), valor: "desempenho", detalle: Tema.t("perfilDesempenhoDet") },
                    { texto: Tema.t("perfilEquilibrado"), valor: "equilibrado", detalle: Tema.t("perfilEquilibradoDet") },
                    { texto: Tema.t("perfilQualidade"), valor: "qualidade", detalle: Tema.t("perfilQualidadeDet") }
                ].concat(raiz.perfilActual === "personalizado"
                         ? [{ texto: Tema.t("perfilPersonalizado"), valor: "personalizado", detalle: Tema.t("perfilPersonalizadoDet") }] : [])
                valor: raiz.perfilActual
                onElegido: (v) => raiz.aplicarPerfil(v)
            }
        }

        Grupo { text: Tema.t("grupoImagen") }
        Fila {
            titulo: Tema.t("gpu")
            descripcion: raiz.gpuPerdida ? Tema.t("gpuFalta") : Tema.t("gpuDesc")
            Selector {
                opciones: raiz.opcionesGpu
                valor: raiz.ajustes.gpu
                onElegido: (v) => raiz.ajustes.gpu = v
            }
        }
        Fila {
            titulo: Tema.t("modo")
            descripcion: Tema.t("modoDesc")
            Selector {
                opciones: [{ texto: Tema.t("completa"), valor: "completa" }, { texto: Tema.t("sinBordes"), valor: "sin_bordes" },
                           { texto: Tema.t("ventana"), valor: "ventana" }]
                valor: raiz.ajustes.modoPantalla
                onElegido: (v) => raiz.ajustes.modoPantalla = v
            }
        }
        Fila {
            titulo: Tema.t("resolucion")
            descripcion: raiz.completa ? Tema.t("resolucionCompleta") : Tema.t("resolucionVentana")
            Selector {
                enabled: !raiz.completa
                opacity: enabled ? 1 : 0.5
                opciones: raiz.completa ? [{ texto: raiz.pantalla.ancho + " × " + raiz.pantalla.alto + "  (" + Tema.t("nativa") + ")", valor: "nativa" }]
                                        : raiz.opcionesResolucion
                valor: raiz.completa ? "nativa" : raiz.ajustes.ancho + "x" + raiz.ajustes.alto
                onElegido: (v) => {
                    var partes = String(v).split("x")
                    raiz.ajustes.ancho = parseInt(partes[0])
                    raiz.ajustes.alto = parseInt(partes[1])
                }
            }
        }
        Fila {
            titulo: Tema.t("aspecto")
            descripcion: Tema.t("aspectoDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("aspecto43") + raiz.marcaPantalla(4 / 3), valor: "4:3" },
                    { texto: Tema.t("aspecto169") + raiz.marcaPantalla(16 / 9), valor: "16:9" },
                    { texto: Tema.t("aspecto1610") + raiz.marcaPantalla(16 / 10), valor: "16:10" },
                    { texto: Tema.t("aspecto219") + raiz.marcaPantalla(21 / 9), valor: "21:9" },
                    { texto: Tema.t("aspecto329") + raiz.marcaPantalla(32 / 9), valor: "32:9", detalle: "5120×1440, 3840×1080" }
                ]
                valor: raiz.ajustes.aspecto
                onElegido: (v) => raiz.ajustes.aspecto = v
            }
        }
        // TOBIICHI_ASPECTO: how the finished PS2 frame is fitted into the window. This is NOT the camera's
        // aspect ratio above (TOBIICHI_PANORAMICO); "auto" keeps the TV's 16:9 with black bars.
        Fila {
            titulo: Tema.t("presentacion")
            descripcion: Tema.t("presentacionDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("presentacionAuto"), valor: "auto" },
                    { texto: Tema.t("estirar"), valor: "estirar" },
                    { texto: Tema.t("aspecto43"), valor: "4:3" },
                    { texto: Tema.t("aspecto169"), valor: "16:9" },
                    { texto: Tema.t("aspecto1610"), valor: "16:10" },
                    { texto: Tema.t("aspecto219"), valor: "21:9" },
                    { texto: Tema.t("aspecto329"), valor: "32:9" }
                ]
                valor: raiz.ajustes.presentacion
                onElegido: (v) => raiz.ajustes.presentacion = v
            }
        }
        Fila {
            titulo: Tema.t("dibujoHardware")
            descripcion: Tema.t("dibujoHardwareDesc")
            Interruptor {
                checked: raiz.ajustes.dibujoHardware
                onToggled: raiz.ajustes.dibujoHardware = checked
            }
        }
        Grupo { text: Tema.t("grupoCalidad") }
        Fila {
            titulo: Tema.t("interna")
            descripcion: Tema.t("internaDesc")
            Selector {
                opciones: raiz.opcionesEscala
                valor: raiz.ajustes.resolucionInterna
                onElegido: (v) => raiz.ajustes.resolucionInterna = v
            }
        }
        Fila {
            titulo: Tema.t("escalado")
            descripcion: Tema.t("escaladoDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("filtroFsr"), valor: "fsr" },
                    { texto: Tema.t("filtroBilineal"), valor: "bilineal" }
                ]
                valor: raiz.ajustes.filtro
                onElegido: (v) => raiz.ajustes.filtro = v
            }
        }
        Fila {
            titulo: Tema.t("nitidez")
            descripcion: Tema.t("nitidezDesc")
            habilitada: raiz.ajustes.filtro === "fsr"
            Deslizador {
                from: 0
                to: 1
                stepSize: 0.05
                value: raiz.ajustes.nitidez
                onMovido: (v) => raiz.ajustes.nitidez = v
            }
        }
        Fila {
            titulo: Tema.t("fxaa")
            descripcion: Tema.t("fxaaDesc")
            Interruptor {
                checked: raiz.ajustes.fxaa
                onToggled: raiz.ajustes.fxaa = checked
            }
        }
        Fila {
            titulo: Tema.t("anisotropico")
            descripcion: Tema.t("anisotropicoDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("desactivado"), valor: "1" },
                    { texto: "2x", valor: "2" },
                    { texto: "4x", valor: "4" },
                    { texto: "8x", valor: "8" },
                    { texto: "16x", valor: "16" }
                ]
                valor: raiz.ajustes.anisotropico
                onElegido: (v) => raiz.ajustes.anisotropico = v
            }
        }

        Grupo { text: Tema.t("grupoEfectos") }
        Fila {
            titulo: Tema.t("fxSinSombras")
            descripcion: Tema.t("fxSinSombrasDesc")
            Interruptor {
                checked: raiz.ajustes.fxSinSombras
                onToggled: raiz.ajustes.fxSinSombras = checked
            }
        }
        Fila {
            titulo: Tema.t("fxSinAditivos")
            descripcion: Tema.t("fxSinAditivosDesc")
            Interruptor {
                checked: raiz.ajustes.fxSinAditivos
                onToggled: raiz.ajustes.fxSinAditivos = checked
            }
        }
        Fila {
            titulo: Tema.t("fxSinFiltrado")
            descripcion: Tema.t("fxSinFiltradoDesc")
            Interruptor {
                checked: raiz.ajustes.fxSinFiltrado
                onToggled: raiz.ajustes.fxSinFiltrado = checked
            }
        }
        Fila {
            titulo: Tema.t("fxAviso")
            descripcion: Tema.t("fxAvisoDesc")
            anchoControl: 0
        }

        // Texture packs (runtime patch 52). The folder is the same setting as in Accessibility / Mods; the
        // four switches below are the remaining controls the runtime actually reads for replacement textures.
        Grupo { text: Tema.t("grupoTexturas") }
        Fila {
            titulo: Tema.t("pacoteTexturas")
            descripcion: raiz.ajustes.pacoteTexturas.length > 0
                         ? Tema.tf("pacoteTexturasPasta", raiz.ajustes.pacoteTexturas)
                         : Tema.t("pacoteTexturasDesc")
            BotonSecundario {
                text: Tema.t("pacoteTexturasEscolher")
                onClicked: dialogoTexturas.open()
            }
        }
        FolderDialog {
            id: dialogoTexturas
            title: Tema.t("pacoteTexturas")
            onAccepted: {
                raiz.ajustes.pacoteTexturas = lanzador.rutaDesdeUrl(selectedFolder)
                raiz.ajustes.usarPacoteTexturas = true
            }
        }
        Fila {
            titulo: Tema.t("usarPaquete")
            descripcion: Tema.t("usarPaqueteDesc")
            habilitada: raiz.ajustes.pacoteTexturas.length > 0
            Interruptor {
                checked: raiz.ajustes.usarPacoteTexturas
                onToggled: raiz.ajustes.usarPacoteTexturas = checked
            }
        }
        Fila {
            titulo: Tema.t("texPresupuesto")
            descripcion: Tema.t("texPresupuestoDesc")
            Selector {
                opciones: [
                    { texto: "256 MB", valor: "256" }, { texto: "512 MB", valor: "512" },
                    { texto: "1024 MB", valor: "1024" }, { texto: "2048 MB", valor: "2048" },
                    { texto: "4096 MB", valor: "4096" }
                ]
                valor: String(raiz.ajustes.texPresupuestoMb)
                onElegido: (v) => raiz.ajustes.texPresupuestoMb = parseInt(v)
            }
        }
        Fila {
            titulo: Tema.t("texEstadisticas")
            descripcion: Tema.t("texEstadisticasDesc")
            Interruptor {
                checked: raiz.ajustes.texEstadisticas
                onToggled: raiz.ajustes.texEstadisticas = checked
            }
        }
        Fila {
            titulo: Tema.t("texNombres")
            descripcion: Tema.t("texNombresDesc")
            Interruptor {
                checked: raiz.ajustes.texNombres
                onToggled: raiz.ajustes.texNombres = checked
            }
        }

        Grupo { text: Tema.t("grupoPresentacion") }
        Fila {
            titulo: Tema.t("progresivo")
            descripcion: Tema.t("progresivoDesc")
            Interruptor {
                checked: raiz.ajustes.progresivo
                onToggled: raiz.ajustes.progresivo = checked
            }
        }
        Fila {
            titulo: Tema.t("presentacionDirecta")
            descripcion: Tema.t("presentacionDirectaDesc")
            Interruptor {
                checked: raiz.ajustes.presentacionDirecta
                onToggled: raiz.ajustes.presentacionDirecta = checked
            }
        }
        Fila {
            titulo: Tema.t("glMenor")
            descripcion: Tema.t("glMenorDesc")
            Selector {
                opciones: [
                    { texto: "4.6", valor: "6" }, { texto: "4.5", valor: "5" },
                    { texto: "4.4", valor: "4" }, { texto: "4.3", valor: "3" }
                ]
                valor: String(raiz.ajustes.glMenor)
                onElegido: (v) => raiz.ajustes.glMenor = parseInt(v)
            }
        }

        Fila {
            titulo: Tema.t("verAvanzado")
            descripcion: Tema.t("verAvanzadoDesc")
            separador: false
            Interruptor {
                checked: raiz.avanzado
                onToggled: raiz.ajustes.verAvanzado = checked
            }
        }
        // Advanced renderer switches: the label is the environment variable itself, so it can be looked up
        // directly in the runtime sources and in a session report. All defaults reproduce the shipped build.
        Grupo { visible: raiz.avanzado; text: Tema.t("grupoTuberia") }
        Repeater {
            model: [
                { clave: "GOW_GS_STATE_CACHE", prop: "gsCacheEstado" },
                { clave: "GOW_GS_TEXREUSE", prop: "gsReusoTexturas" },
                { clave: "GOW_GS_HW_RING", prop: "gsAnilloVertices" },
                { clave: "GOW_GS_DEPTH_PER_ZBP", prop: "gsProfundidadZbp" },
                { clave: "PS2X_GS_RUN", prop: "gsAgruparPrimitivas" },
                { clave: "PS2X_GS_RUN_STATE_FAST", prop: "gsRunRapido" },
                { clave: "PS2X_GS_COMPACT_QUEUE", prop: "gsColaCompacta" },
                { clave: "PS2X_GS_WORKER", prop: "gsHiloWorker" },
                { clave: "PS2X_GS_PIPELINE", prop: "gsHiloPipeline" },
                { clave: "GOW_GS_FINISH_ASINCRONO", prop: "gsFinishAsincrono" },
                { clave: "GOW_GS_ASYNC_SUBMIT", prop: "gsEnvioAsincrono" }
            ]
            delegate: Fila {
                required property var modelData
                visible: raiz.avanzado
                titulo: modelData.clave
                Interruptor {
                    checked: raiz.ajustes[modelData.prop]
                    onToggled: raiz.ajustes[modelData.prop] = checked
                }
            }
        }
        Fila {
            visible: raiz.avanzado
            titulo: "PS2X_GS_QUEUE_CHUNKS"
            Selector {
                opciones: [
                    { texto: Tema.t("presentacionAuto"), valor: "0" },
                    { texto: "4", valor: "4" }, { texto: "8", valor: "8" },
                    { texto: "16", valor: "16" }, { texto: "32", valor: "32" }, { texto: "64", valor: "64" }
                ]
                valor: String(raiz.ajustes.gsBloquesCola)
                onElegido: (v) => raiz.ajustes.gsBloquesCola = parseInt(v)
            }
        }

        Grupo { visible: raiz.avanzado; text: Tema.t("grupoDiagnostico") }
        Repeater {
            model: [
                { clave: "GOW_GS_HW_STATS", prop: "gsEstadisticas" },
                { clave: "GOW_GS_GPU_PROFILE", prop: "gsPerfilGpu" }
            ]
            delegate: Fila {
                required property var modelData
                visible: raiz.avanzado
                titulo: modelData.clave
                descripcion: Tema.t("diagDesc")
                Interruptor {
                    checked: raiz.ajustes[modelData.prop]
                    onToggled: raiz.ajustes[modelData.prop] = checked
                }
            }
        }
        Fila {
            visible: raiz.avanzado
            titulo: Tema.t("texVolcado")
            descripcion: Tema.t("diagDesc")
            Selector {
                opciones: [
                    { texto: Tema.t("desactivado"), valor: "0" }, { texto: "8", valor: "8" },
                    { texto: "32", valor: "32" }, { texto: "128", valor: "128" }
                ]
                valor: String(raiz.ajustes.texVolcado)
                onElegido: (v) => raiz.ajustes.texVolcado = parseInt(v)
            }
        }

        Grupo { text: Tema.t("grupoHerramientas") }
        Fila {
            titulo: Tema.t("upNativo")
            descripcion: Tema.t("upNativoDesc")
            anchoControl: 0
        }
        Fila {
            titulo: Tema.t("upDlss")
            descripcion: Tema.t("upDlssDesc")
            anchoControl: 150
            Rectangle {
                anchors.right: parent.right
                width: etiquetaNo.implicitWidth + 24
                height: 28
                radius: 14
                color: "transparent"
                border.width: 1
                border.color: Tema.borde
                Text {
                    id: etiquetaNo
                    anchors.centerIn: parent
                    text: Tema.t("upNoDisponible")
                    color: Tema.textoTenue
                    font.pixelSize: 12
                }
            }
        }
        Fila {
            titulo: Tema.t("upExternas")
            descripcion: Tema.t("upExternasDesc")
            separador: false
            Interruptor {
                checked: raiz.ajustes.modoPantalla === "sin_bordes"
                onToggled: raiz.ajustes.modoPantalla = checked ? "sin_bordes" : "completa"
            }
        }
    }
}
