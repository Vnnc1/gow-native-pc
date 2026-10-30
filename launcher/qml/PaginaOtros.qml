import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// "Other" tab: language, game options, shortcuts, log and defaults.
ScrollView {
    id: raiz
    required property var ajustes
    property var idiomasJuego: []   // installer.languages(): the prepared discs, one per language
    signal restablecer()
    signal aviso(string texto)
    signal ponerPortada(string ruta)
    signal quitarPortada()
    contentWidth: availableWidth
    clip: true

    ColumnLayout {
        width: raiz.availableWidth
        spacing: 0

        Fila {
            titulo: Tema.t("idioma")
            Selector {
                opciones: [{ texto: "Türkçe", valor: "tr" }, { texto: "English", valor: "en" }, { texto: "Español", valor: "es" },
                           { texto: "Português (Brasil)", valor: "pt" }]
                valor: raiz.ajustes.idioma
                onElegido: (v) => raiz.ajustes.idioma = v
            }
        }
        Fila {
            // gow-native-pc: the game's language = which prepared disc runs (tools/disc/prepare.py, languages.json)
            titulo: Tema.t("textoJuego")
            descripcion: Tema.t("textoJuegoDesc")
            Selector {
                opciones: raiz.idiomasJuego.map(function (l) { return { texto: l.label, valor: l.language } })
                valor: raiz.ajustes.textoJuego
                onElegido: (v) => raiz.ajustes.textoJuego = v
            }
        }
        Fila {
            titulo: Tema.t("portada")
            descripcion: Tema.t("portadaDesc")
            Row {
                anchors.right: parent.right
                spacing: 8
                BotonSecundario {
                    text: Tema.t("examinar")
                    onClicked: dialogoPortada.open()
                }
                BotonSecundario {
                    visible: raiz.ajustes.portada.length > 0
                    text: Tema.t("portadaQuitar")
                    onClicked: raiz.quitarPortada()
                }
            }
        }
        Fila {
            visible: raiz.ajustes.portada.length > 0
            titulo: Tema.t("portadaFoco")
            descripcion: Tema.t("portadaFocoDesc")
            Deslizador {
                from: 0
                to: 1
                stepSize: 0.01
                value: raiz.ajustes.portadaFoco
                onMovido: (v) => raiz.ajustes.portadaFoco = v
            }
        }
        Fila {
            visible: raiz.ajustes.portada.length > 0
            titulo: Tema.t("portadaOscurecer")
            descripcion: Tema.t("portadaOscurecerDesc")
            Deslizador {
                from: 0.3
                to: 1
                stepSize: 0.01
                value: raiz.ajustes.portadaBrillo
                onMovido: (v) => raiz.ajustes.portadaBrillo = v
            }
        }
        Fila {
            titulo: Tema.t("saltarVideos")
            descripcion: Tema.t("saltarVideosDesc")
            Interruptor {
                checked: raiz.ajustes.saltarVideos
                onToggled: raiz.ajustes.saltarVideos = checked
            }
        }
        Fila {
            titulo: Tema.t("minimizarAlJugar")
            descripcion: Tema.t("minimizarAlJugarDesc")
            Interruptor {
                checked: raiz.ajustes.minimizarAlJugar
                onToggled: raiz.ajustes.minimizarAlJugar = checked
            }
        }
        Fila {
            titulo: Tema.t("accesos")
            descripcion: Tema.t("accesosDesc")
            Row {
                anchors.right: parent.right
                spacing: 8
                BotonSecundario {
                    text: Tema.t("accesoMenu")
                    onClicked: if (lanzador.crearAccesoDirecto(false)) raiz.aviso(Tema.t("accesoHecho"))
                }
                BotonSecundario {
                    text: Tema.t("accesoEscritorio")
                    onClicked: if (lanzador.crearAccesoDirecto(true)) raiz.aviso(Tema.t("accesoHecho"))
                }
            }
        }
        Fila {
            titulo: Tema.t("registro")
            descripcion: Tema.t("registroDesc")
            BotonSecundario {
                anchors.right: parent.right
                text: Tema.t("abrir")
                onClicked: lanzador.abrirRegistro()
            }
        }
        Fila {
            titulo: Tema.t("diagnosticsReport")
            descripcion: Tema.t("diagnosticsReportDesc")
            BotonSecundario {
                anchors.right: parent.right
                text: Tema.t("diagnosticsExport")
                onClicked: lanzador.exportDiagnostics()
            }
        }
        Fila {
            titulo: Tema.t("diagnosticsMarker")
            descripcion: Tema.t("diagnosticsMarkerDesc")
            habilitada: lanzador.jugando
            Column {
                width: parent.width
                spacing: 8
                TextField {
                    id: diagnosticNote
                    width: parent.width
                    maximumLength: 1000
                    placeholderText: Tema.t("diagnosticsNote")
                    selectByMouse: true
                    color: Tema.texto
                    placeholderTextColor: Tema.textoTenue
                    font.pixelSize: 13
                    background: Rectangle {
                        color: Tema.lateral
                        radius: 4
                        border.color: diagnosticNote.activeFocus ? Tema.oro : Tema.borde
                    }
                }
                BotonSecundario {
                    anchors.right: parent.right
                    text: Tema.t("diagnosticsMark")
                    onClicked: {
                        if (lanzador.markDiagnostic(diagnosticNote.text)) {
                            raiz.aviso(Tema.t("diagnosticsMarked"))
                            diagnosticNote.clear()
                        }
                    }
                }
            }
        }
        Fila {
            titulo: Tema.t("restablecer")
            descripcion: Tema.t("restablecerDesc")
            BotonSecundario {
                anchors.right: parent.right
                peligro: true
                text: Tema.t("restablecer")
                onClicked: raiz.restablecer()
            }
        }
        Fila {
            titulo: Tema.t("acerca")
            descripcion: Tema.t("acercaTexto")
            separador: false
            Text {
                anchors.right: parent.right
                text: "v" + lanzador.version
                color: Tema.textoTenue
                font.pixelSize: 13
            }
        }
    }

    FileDialog {
        id: dialogoPortada
        title: Tema.t("elegirPortada")
        nameFilters: ["PNG / JPEG / WebP / AVIF (*.png *.jpg *.jpeg *.webp *.avif *.bmp)", "* (*)"]
        onAccepted: raiz.ponerPortada(lanzador.rutaDesdeUrl(selectedFile))
    }
}
