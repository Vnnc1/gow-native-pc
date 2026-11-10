import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// gow-native-pc: "Saves" tab. A save is a copy of the memory card (Mcd001.ps2) as the game last wrote it at a save
// altar: supported runners back it up automatically; F1 and "Save a copy" also make manual copies. "Use" restores with the game
// closed (the current card is kept first as a "backup" copy), so a test can start again from an area reached earlier.
ScrollView {
    id: raiz
    required property string carpeta
    property string elf
    signal aviso(string texto)
    signal iniciarSlot()
    property var lista: []
    property var slots: []
    function tr(pt, en) { return Tema.idioma === "pt" ? pt : en }
    contentWidth: availableWidth
    clip: true

    function refrescar() {
        var current = carpeta ? lanzador.partidas(carpeta) : []
        if (JSON.stringify(current) !== JSON.stringify(lista)) lista = current
        var individual = typeof lanzador.partidasIndividuales === "function" && elf ? lanzador.partidasIndividuales(elf) : []
        if (JSON.stringify(individual) !== JSON.stringify(slots)) slots = individual
    }
    onCarpetaChanged: refrescar()
    onElfChanged: refrescar()
    Component.onCompleted: refrescar()
    onVisibleChanged: if (visible) refrescar()
    Timer {
        interval: 2000
        repeat: true
        running: raiz.visible && lanzador.jugando
        onTriggered: raiz.refrescar()
    }
    Connections {
        target: lanzador
        function onJugandoCambiado() { raiz.refrescar() }
    }

    ColumnLayout {
        width: raiz.availableWidth
        spacing: 0

        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 12
            text: raiz.tr("Saves do jogo", "Game saves")
            color: Tema.texto
            font.pixelSize: 22
            font.bold: true
        }
        Repeater {
            model: raiz.slots
            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                Layout.bottomMargin: 10
                implicitHeight: 108
                color: Tema.campo
                radius: 6
                border.color: Tema.borde
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 16
                    Image {
                        source: modelData.imagen
                        Layout.preferredWidth: 128
                        Layout.preferredHeight: 80
                        fillMode: Image.PreserveAspectFit
                        smooth: false
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: modelData.nombre; color: Tema.texto; font.pixelSize: 17; elide: Text.ElideRight }
                        Text { text: "Slot " + (modelData.slot + 1) + " · " + modelData.fecha; color: Tema.textoSuave; font.pixelSize: 12 }
                        Text {
                            text: raiz.tr("Tempo de jogo: ", "Play time: ") + Math.floor(modelData.segundos / 3600) + "h " + Math.floor(modelData.segundos / 60) % 60 + "m"
                            color: Tema.textoTenue; font.pixelSize: 12
                        }
                    }
                    BotonSecundario {
                        text: raiz.tr("Carregar", "Load")
                        Accessible.name: text + " " + modelData.nombre
                        onClicked: { carregarSlot.slot = modelData.slot; carregarSlot.open() }
                    }
                }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 20
            visible: raiz.slots.length === 0
            text: raiz.tr("Nenhum slot compatível disponível neste cartão.", "No compatible slots available on this card.")
            color: Tema.textoSuave
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.bottomMargin: 12
            text: raiz.tr("Histórico de backups do cartão", "Card backup history")
            color: Tema.texto; font.pixelSize: 20
        }

        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 8
            text: Tema.t("partidasExplica")
            color: Tema.textoSuave
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
        Fila {
            titulo: Tema.t("partidaGuardar")
            descripcion: Tema.t("partidaGuardarDesc")
            anchoControl: 380
            RowLayout {
                anchors.right: parent.right
                width: 380
                spacing: 8
                TextField {
                    id: etiqueta
                    Layout.fillWidth: true
                    implicitHeight: 36
                    color: Tema.texto
                    font.pixelSize: 13
                    maximumLength: 40
                    placeholderText: Tema.t("partidaEtiqueta")
                    placeholderTextColor: Tema.textoTenue
                    leftPadding: 10
                    background: Rectangle {
                        radius: 4
                        color: Tema.campo
                        border.width: 1
                        border.color: etiqueta.activeFocus ? Tema.oro : Tema.borde
                    }
                }
                BotonSecundario {
                    text: Tema.t("partidaGuardarBoton")
                    enabled: !lanzador.jugando
                    onClicked: {
                        if (lanzador.guardarPartida(raiz.carpeta, raiz.elf, etiqueta.text.trim()).length > 0) {
                            etiqueta.text = ""
                            raiz.aviso(Tema.t("partidaGuardada"))
                        } else {
                            raiz.aviso(Tema.t("partidaSinTarjeta"))
                        }
                        raiz.refrescar()
                    }
                }
            }
        }
        Fila {
            titulo: Tema.t("partidaCarpeta")
            descripcion: Tema.t("partidaCarpetaDesc")
            Row {
                anchors.right: parent.right
                spacing: 8
                BotonSecundario {
                    text: Tema.t("partidaImportar")
                    onClicked: dialogoImportar.open()
                }
                BotonSecundario {
                    text: Tema.t("abrir")
                    onClicked: lanzador.abrirCarpeta(raiz.carpeta)
                }
            }
        }

        Text {
            Layout.topMargin: 14
            Layout.bottomMargin: 4
            text: Tema.t("partidasLista")
            color: Tema.texto
            font.pixelSize: 15
            font.weight: Font.Medium
        }
        Text {
            visible: raiz.lista.length === 0
            text: Tema.t("partidasNinguna")
            color: Tema.textoTenue
            font.pixelSize: 13
        }
        Repeater {
            model: raiz.lista
            delegate: Fila {
                required property var modelData
                required property int index
                separador: index < raiz.lista.length - 1
                titulo: (modelData.etiqueta.length > 0 ? modelData.etiqueta + "  ·  " : "") + modelData.fecha
                descripcion: Tema.t("partidaOrigen_" + (modelData.origen.length > 0 ? modelData.origen : "F1"))
                Row {
                    anchors.right: parent.right
                    spacing: 8
                    BotonSecundario {
                        text: Tema.t("partidaUsar")
                        enabled: !lanzador.jugando
                        onClicked: {
                            confirmar.nombre = modelData.nombre
                            confirmar.open()
                        }
                    }
                    BotonSecundario {
                        peligro: true
                        text: Tema.t("partidaBorrar")
                        onClicked: if (lanzador.borrarPartida(raiz.carpeta, modelData.nombre)) raiz.refrescar()
                    }
                }
            }
        }
    }

    Popup {
        id: confirmar
        property string nombre
        parent: Overlay.overlay
        anchors.centerIn: Overlay.overlay
        width: 520
        modal: true
        padding: 24
        Overlay.modal: Rectangle { color: "#a0000000" }
        background: Rectangle {
            radius: 6
            color: Tema.fondoAlto
            border.width: 1
            border.color: Tema.oro
        }
        contentItem: ColumnLayout {
            spacing: 14
            Text {
                Layout.fillWidth: true
                text: Tema.t("partidaUsarConfirma")
                color: Tema.texto
                font.pixelSize: 15
                wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 8
                BotonSecundario {
                    text: Tema.t("cancelar")
                    onClicked: confirmar.close()
                }
                BotonSecundario {
                    text: Tema.t("partidaUsar")
                    onClicked: {
                        confirmar.close()
                        raiz.aviso(Tema.t(lanzador.restaurarPartida(raiz.carpeta, confirmar.nombre, raiz.elf)
                                          ? "partidaRestaurada" : "partidaNoRestaurada"))
                        raiz.refrescar()
                    }
                }
            }
        }
    }

    Dialog {
        id: carregarSlot
        property int slot: -1
        anchors.centerIn: parent
        width: Math.min(460, raiz.width - 24)
        height: 220
        modal: true
        title: raiz.tr("Carregar save?", "Load save?")
        standardButtons: Dialog.Ok | Dialog.Cancel
        contentHeight: loadMessage.implicitHeight
        contentItem: Text {
            id: loadMessage
            width: carregarSlot.availableWidth
            text: raiz.tr("O progresso desde o último altar será perdido. O jogo carregará o slot escolhido.", "Progress since the last altar will be lost. The game will load the selected slot.")
            wrapMode: Text.WordWrap
            color: Tema.texto
        }
        background: Rectangle { color: Tema.fondoAlto; border.color: Tema.oro; radius: 6 }
        onAccepted: {
            if (lanzador.seleccionarPartida(raiz.elf, slot)) {
                if (!lanzador.jugando) raiz.iniciarSlot()
            } else raiz.aviso(raiz.tr("Não foi possível carregar este slot agora.", "This slot cannot be loaded now."))
        }
    }

    FileDialog {
        id: dialogoImportar
        title: Tema.t("partidaImportar")
        nameFilters: ["PCSX2 memory card (*.ps2)", "* (*)"]
        onAccepted: {
            raiz.aviso(Tema.t(lanzador.importarPartida(raiz.carpeta, lanzador.rutaDesdeUrl(selectedFile)).length > 0
                              ? "partidaImportada" : "partidaNoImportada"))
            raiz.refrescar()
        }
    }
}
