import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// gow-native-pc: "Saves" tab. A save is a copy of the memory card (Mcd001.ps2) as the game last wrote it at a save
// altar: F1 > Saves in game makes one, and so does "Save a copy" here. "Use" puts a copy back as the card with the game
// closed (the current card is kept first as a "backup" copy), so a test can start again from an area reached earlier.
ScrollView {
    id: raiz
    required property string carpeta
    property string elf
    signal aviso(string texto)
    property var lista: []
    contentWidth: availableWidth
    clip: true

    function refrescar() { lista = lanzador.partidas(carpeta) }
    Component.onCompleted: refrescar()
    Connections {
        target: lanzador
        function onJugandoCambiado() { raiz.refrescar() } // copies made with F1 while playing show up afterwards
    }

    ColumnLayout {
        width: raiz.availableWidth
        spacing: 0

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
