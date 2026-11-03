import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Textos.js" as T

ApplicationWindow {
    id: root
    visible: true
    width: 860; height: 700
    minimumWidth: 640; minimumHeight: 540
    title: t("diagTitle")
    color: "#151719"
    palette.windowText: "#eeeeee"
    palette.text: "#eeeeee"
    palette.buttonText: "#eeeeee"
    palette.button: "#35393e"
    palette.base: "#202327"
    palette.placeholderText: "#b8bdc4"
    palette.highlight: "#bd4137"
    font.pixelSize: 15
    function t(key) { return T.texto(key, "pt") }
    ScrollView {
        anchors.fill: parent; anchors.margins: 24
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width; spacing: 14
            Label { text: root.t("diagTitle"); font.pixelSize: 28; font.bold: true }
            Label { text: root.t("diagIntro").replace("%1", diagnosticKit.elfName); wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Button {
                text: root.t("diagSelectGame"); enabled: !diagnosticKit.running
                onClicked: diagnosticKit.chooseGame(text)
                Accessible.name: text
            }
            TextField { text: diagnosticKit.gamePath; readOnly: true; Layout.fillWidth: true; Accessible.name: root.t("diagSelectGame") }
            RowLayout {
                CheckBox { id: fast; text: root.t("vuRapida"); enabled: !diagnosticKit.running; Accessible.name: text }
                Label { text: root.t("diagScale") }
                ComboBox { id: scale; model: ["1×", "2×"]; enabled: !diagnosticKit.running; Accessible.name: root.t("diagScale") }
            }
            Label { text: root.t("diagModes"); wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                Button { text: root.t("diagBasic"); enabled: !diagnosticKit.running && diagnosticKit.gamePath.length > 0; onClicked: diagnosticKit.start(false, fast.checked, scale.currentIndex+1) }
                Button { text: root.t("diagDetailed"); enabled: !diagnosticKit.running && diagnosticKit.gamePath.length > 0; onClicked: diagnosticKit.start(true, fast.checked, scale.currentIndex+1) }
                Button { text: root.t("diagStop"); enabled: diagnosticKit.running; onClicked: diagnosticKit.stop() }
            }
            RowLayout {
                TextField { id: note; placeholderText: root.t("diagNote"); maximumLength: 1000; Layout.fillWidth: true; Accessible.name: root.t("diagNote") }
                Button { text: root.t("diagMark"); enabled: diagnosticKit.running; onClicked: diagnosticKit.mark(note.text) }
            }
            Label { text: root.t(diagnosticKit.statusKey); font.bold: true; color: "#f0c7a4"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Label { text: diagnosticKit.detail; visible: text.length>0; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
            RowLayout {
                Button { text: root.t("diagExport"); onClicked: diagnosticKit.exportReport() }
                Button { text: root.t("diagOpenReports"); onClicked: diagnosticKit.openReports() }
            }
            TextArea {
                text: diagnosticKit.report; readOnly: true; selectByMouse: true; wrapMode: Text.WordWrap
                Layout.fillWidth: true; Layout.preferredHeight: 200
                Accessible.name: root.t("diagSummary")
            }
            Label { text: root.t("diagPrivacy"); wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#b8bdc4" }
        }
    }
}
