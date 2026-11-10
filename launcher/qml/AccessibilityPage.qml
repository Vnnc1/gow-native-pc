import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// Accessibility and installed visual modifications share the existing persisted settings.
ScrollView {
    id: root
    required property var settings
    signal openControls()
    contentWidth: availableWidth
    clip: true

    component SectionTitle: Text {
        Layout.fillWidth: true
        Layout.topMargin: 14
        Layout.bottomMargin: 6
        color: Tema.oroClaro
        font.family: Tema.fuenteTitulo
        font.pixelSize: 18
        font.weight: Font.Bold
        wrapMode: Text.WordWrap
    }
    ColumnLayout {
        width: root.availableWidth
        spacing: 0
        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 12
            text: Tema.t("accessibilityIntro")
            color: Tema.textoSuave
            font.pixelSize: 14
            wrapMode: Text.WordWrap
        }
        SectionTitle { text: Tema.t("inputAssistance") }
        Fila {
            titulo: Tema.t("cancelarAnimaciones")
            descripcion: Tema.t("cancelarAnimacionesDesc")
            Interruptor {
                checked: root.settings.cancelarAnimaciones
                onToggled: root.settings.cancelarAnimaciones = checked
            }
        }
        Fila {
            titulo: Tema.t("qteAuto")
            descripcion: Tema.t("qteAutoDesc")
            Interruptor {
                checked: root.settings.qteAuto
                onToggled: root.settings.qteAuto = checked
            }
        }
        Fila {
            // gow-native-pc: accessibility — holding a button instead of mashing it in the minigames (GOW_QTE_HOLD)
            titulo: Tema.t("qteHold")
            descripcion: Tema.t("qteHoldDesc")
            Interruptor {
                checked: root.settings.qteHold
                onToggled: root.settings.qteHold = checked
            }
        }
        Fila {
            titulo: Tema.t("qteHoldButtons")
            descripcion: Tema.t("qteHoldButtonsDesc")
            habilitada: root.settings.qteHold
            Selector {
                opciones: [
                    { texto: Tema.t("qteHoldCircle"), valor: "circle" },
                    { texto: Tema.t("qteHoldFace"), valor: "face" }
                ]
                valor: root.settings.qteHoldButtons
                onElegido: (v) => root.settings.qteHoldButtons = v
            }
        }
        Repeater {
            model: [ { button: "L1", setting: "qteHoldL1" }, { button: "L2", setting: "qteHoldL2" },
                     { button: "R1", setting: "qteHoldR1" }, { button: "R2", setting: "qteHoldR2" } ]
            delegate: Fila {
                required property var modelData
                titulo: Tema.t("qteHold") + " · " + modelData.button
                habilitada: root.settings.qteHold
                Interruptor {
                    checked: root.settings[modelData.setting]
                    onToggled: root.settings[modelData.setting] = checked
                }
            }
        }
        Fila {
            titulo: Tema.t("qteStick")
            descripcion: Tema.t("qteStickDesc")
            Selector {
                opciones: [{ texto: Tema.t("qteStickOff"), valor: "off" },
                           { texto: Tema.t("qteStickShake"), valor: "shake" },
                           { texto: Tema.t("qteStickRotate"), valor: "rotate" }]
                valor: root.settings.qteStickMode
                onElegido: (v) => root.settings.qteStickMode = v
            }
        }
        Fila {
            titulo: Tema.t("qteHoldRate")
            descripcion: Tema.t("qteHoldRateDesc")
            habilitada: root.settings.qteHold
            Selector {
                opciones: [{ texto: "6", valor: 6 }, { texto: "10", valor: 10 }, { texto: "14", valor: 14 },
                           { texto: "20", valor: 20 }]
                valor: root.settings.qteHoldRate
                onElegido: (v) => root.settings.qteHoldRate = v
            }
        }
        Fila {
            titulo: Tema.t("keyboardChords")
            descripcion: Tema.t("keyboardChordsDesc")
            BotonSecundario {
                anchors.right: parent.right
                text: Tema.t("pestControles")
                onClicked: root.openControls()
            }
        }
        SectionTitle { text: Tema.t("textureMods") }
        // Texture pack in PCSX2's format (runtime patch 52): replaces the game's textures while playing, no rebuild
        Fila {
            titulo: Tema.t("pacoteTexturas")
            descripcion: root.settings.pacoteTexturas.length > 0 ? Tema.tf("pacoteTexturasPasta", root.settings.pacoteTexturas)
                                                                : Tema.t("pacoteTexturasDesc")
            RowLayout {
                anchors.right: parent.right
                spacing: 10
                BotonSecundario {
                    text: Tema.t("pacoteTexturasEscolher")
                    onClicked: dialogoPacote.open()
                }
                Interruptor {
                    anchors.right: undefined
                    Layout.alignment: Qt.AlignRight
                    enabled: root.settings.pacoteTexturas.length > 0
                    checked: root.settings.usarPacoteTexturas
                    onToggled: root.settings.usarPacoteTexturas = checked
                }
            }
            FolderDialog {
                id: dialogoPacote
                title: Tema.t("pacoteTexturas")
                onAccepted: {
                    root.settings.pacoteTexturas = lanzador.rutaDesdeUrl(selectedFolder)
                    root.settings.usarPacoteTexturas = true
                }
            }
        }
    }
}
