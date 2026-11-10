import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// Mods tab (launcher patch 73). Drop a .zip / folder anywhere on this page to install it, switch named
// profiles, search and batch-toggle the selection, export a mod to share, and read the runtime evidence
// that proves the overrides were actually used. Nothing is injected unless a mod is enabled.
Item {
    id: raiz
    required property var modelo
    required property var settings
    signal aviso(string texto)
    signal fallo(string texto, string detalle)

    readonly property var lista: modelo ? modelo.mods : []
    readonly property var diag: modelo ? modelo.diagnostics : []
    readonly property bool ocupado: modelo ? modelo.busy : false
    property string busqueda: ""
    property bool arrastrando: false
    readonly property var filtrados: {
        const q = raiz.busqueda.trim().toLowerCase()
        const out = []
        for (let i = 0; i < raiz.lista.length; ++i) {
            const m = raiz.lista[i]
            const texto = ((m.name || "") + " " + (m.mod || "") + " " + (m.description || "") + " "
                           + (m.author || "")).toLowerCase()
            if (q.length === 0 || texto.indexOf(q) >= 0)
                out.push(m)
        }
        return out
    }

    function alternar(fila, valor) {
        if (!modelo.setEnabled(fila.key, valor)) {
            fallo(Tema.t("modsNoChange"), modelo.lastError)
            modelo.refresh()
        }
    }
    function comprobar() {
        const r = modelo.analizar()
        if (!r.ok) {
            fallo(Tema.t("modsError"), r.error)
            return
        }
        aviso(Tema.tf("modsCheckResult", r.mods, r.diagnostics))
    }
    function restaurar() {
        if (modelo.descartar())
            aviso(Tema.t("modsRestoreDone"))
        else
            fallo(Tema.t("modsRestoreFailed"), modelo.lastError)
    }
    function seleccion(habilitar) {
        const claves = []
        for (let i = 0; i < raiz.filtrados.length; ++i) {
            const m = raiz.filtrados[i]
            if (habilitar && !m.valid) continue
            claves.push(m.key)
        }
        if (claves.length === 0) return
        if (!modelo.setEnabledBatch(claves, habilitar)) {
            fallo(Tema.t("modsNoChange"), modelo.lastError)
            modelo.refresh()
        }
    }
    function instalarSoltados(urls) {
        const rutas = []
        for (let i = 0; i < urls.length; ++i)
            rutas.push(lanzador.rutaDesdeUrl(urls[i]))
        const r = modelo.importarArchivos(rutas)
        if (r.ok)
            aviso(Tema.tf("modsDropInstalled", r.installed))
        else
            fallo(Tema.t("modsImportFailed"), r.message || "")
    }
    function exportarMod(clave) {
        const r = modelo.exportar(clave)
        if (r.ok)
            aviso(Tema.tf("modsExportDone", r.path))
        else
            fallo(Tema.t("modsExportFailed"), r.message || "")
    }

    Component.onCompleted: if (modelo) modelo.refresh()

    ScrollView {
        id: desplazamiento
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: desplazamiento.availableWidth
            spacing: 0

            Text {
                Layout.fillWidth: true
                Layout.bottomMargin: 12
                text: Tema.t("modsIntro")
                color: Tema.textoSuave
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }

        Text { text: Tema.t("textureMods"); Layout.fillWidth: true; Layout.topMargin: 14; Layout.bottomMargin: 6; color: Tema.oroClaro; font.family: Tema.fuenteTitulo; font.pixelSize: 18; font.bold: true; wrapMode: Text.WordWrap }
        // Texture pack in PCSX2's format (runtime patch 52): replaces the game's textures while playing, no rebuild
        Fila {
            titulo: Tema.t("pacoteTexturas")
            descripcion: raiz.settings.pacoteTexturas.length > 0 ? Tema.tf("pacoteTexturasPasta", raiz.settings.pacoteTexturas)
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
                    enabled: raiz.settings.pacoteTexturas.length > 0
                    checked: raiz.settings.usarPacoteTexturas
                    onToggled: raiz.settings.usarPacoteTexturas = checked
                }
            }
            FolderDialog {
                id: dialogoPacote
                title: Tema.t("pacoteTexturas")
                onAccepted: {
                    raiz.settings.pacoteTexturas = lanzador.rutaDesdeUrl(selectedFolder)
                    raiz.settings.usarPacoteTexturas = true
                }
            }
        }

            // Named mod sets: switch a whole selection at once.
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 10
                spacing: 8
                Text {
                    text: Tema.t("modsProfile")
                    color: Tema.textoSuave
                    font.pixelSize: 12
                }
                ComboBox {
                    id: selectorPerfil
                    Layout.preferredWidth: 180
                    model: raiz.modelo ? raiz.modelo.profiles : []
                    textRole: "name"
                    valueRole: "name"
                    // Match the launcher's dark theme instead of the platform's white control.
                    background: Rectangle {
                        radius: 6
                        color: Tema.campo
                        border.width: 1
                        border.color: Tema.borde
                    }
                    contentItem: Text {
                        text: selectorPerfil.displayText
                        color: Tema.texto
                        font.pixelSize: 13
                        leftPadding: 10
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    indicator: Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: "▾"
                        color: Tema.textoSuave
                        font.pixelSize: 14
                    }
                    delegate: ItemDelegate {
                        id: delegadoPerfil
                        required property var modelData
                        width: selectorPerfil.width
                        height: 30
                        contentItem: Text {
                            text: modelData.name
                            color: Tema.texto
                            font.pixelSize: 13
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            color: delegadoPerfil.highlighted ? Tema.oroOscuro : Tema.panelClaro
                            radius: 4
                        }
                    }
                    function sincronizar() {
                        const actual = raiz.modelo ? raiz.modelo.profile : "launcher"
                        for (let i = 0; i < count; ++i)
                            if (textAt(i) === actual) { currentIndex = i; return }
                    }
                    onModelChanged: sincronizar()
                    Component.onCompleted: sincronizar()
                    onActivated: {
                        const r = raiz.modelo.cambiarPerfil(currentValue)
                        if (!r.ok) raiz.fallo(Tema.t("modsProfileNew"), r.message || "")
                    }
                }
                BotonSecundario {
                    text: Tema.t("modsProfileNew")
                    enabled: !raiz.ocupado
                    onClicked: { nombrePerfil.text = ""; dialogoPerfil.open() }
                }
                BotonSecundario {
                    text: Tema.t("modsProfileDelete")
                    peligro: true
                    enabled: !raiz.ocupado && raiz.modelo && raiz.modelo.profile !== "launcher"
                    onClicked: {
                        const r = raiz.modelo.borrarPerfil(raiz.modelo.profile)
                        if (!r.ok) raiz.fallo(Tema.t("modsProfileDelete"), r.message || "")
                    }
                }
                Item { Layout.fillWidth: true }
            }

            // Search + batch actions.
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 10
                spacing: 8
                TextField {
                    id: buscador
                    Layout.fillWidth: true
                    placeholderText: Tema.t("modsSearch")
                    placeholderTextColor: Tema.textoTenue
                    color: Tema.texto
                    font.pixelSize: 13
                    background: Rectangle {
                        radius: 6
                        color: Tema.campo
                        border.width: 1
                        border.color: Tema.borde
                    }
                    onTextChanged: raiz.busqueda = text
                }
                BotonSecundario {
                    text: Tema.t("modsEnableAll")
                    enabled: !raiz.ocupado && raiz.filtrados.length > 0
                    onClicked: raiz.seleccion(true)
                }
                BotonSecundario {
                    text: Tema.t("modsDisableAll")
                    enabled: !raiz.ocupado && raiz.filtrados.length > 0
                    onClicked: raiz.seleccion(false)
                }
                BotonSecundario {
                    text: Tema.t("modsExportFolder")
                    onClicked: raiz.modelo.abrirExportaciones()
                }
            }

            // Status line: how many are installed/enabled and whether this profile is staged.
            Rectangle {
                Layout.fillWidth: true
                Layout.bottomMargin: 10
                implicitHeight: estado.implicitHeight + 20
                radius: 6
                color: "#191c22"
                border.width: 1
                border.color: Tema.borde
                RowLayout {
                    id: estado
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 12
                    spacing: 10
                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: raiz.ocupado ? Tema.aviso : (raiz.modelo && raiz.modelo.active ? Tema.bien : Tema.textoTenue)
                    }
                    Text {
                        Layout.fillWidth: true
                        text: raiz.modelo ? Tema.tf("modsCount", raiz.modelo.enabledCount, raiz.lista.length) : ""
                        color: Tema.texto
                        font.pixelSize: 13
                        font.weight: Font.Medium
                    }
                    Text {
                        visible: raiz.modelo && raiz.modelo.active
                        text: Tema.t("modsActive")
                        color: Tema.bien
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                    Text {
                        visible: raiz.modelo && !raiz.modelo.active
                        text: Tema.t("modsNotActive")
                        color: Tema.textoTenue
                        font.pixelSize: 12
                    }
                    Text {
                        visible: raiz.modelo && raiz.modelo.stale && raiz.modelo.active
                        text: Tema.t("modsStale")
                        color: Tema.aviso
                        font.pixelSize: 12
                    }
                }
            }

            // Runtime evidence: written by mod_vfs_table.cpp while the game runs.
            Text {
                Layout.fillWidth: true
                Layout.bottomMargin: 8
                visible: raiz.modelo && raiz.modelo.lastRun && raiz.modelo.lastRun.hits !== undefined
                text: raiz.modelo ? Tema.tf("modsLastRun", raiz.modelo.lastRun.hits || 0,
                                            raiz.modelo.lastRun.lookups || 0) : ""
                color: Tema.bien
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            // Data patches are interpreted by host C++ (runtime patch 84); an older runner ignores them.
            Text {
                Layout.fillWidth: true
                Layout.bottomMargin: 8
                visible: raiz.modelo && raiz.modelo.requiresRebuild
                text: Tema.t("modsRebuild")
                color: Tema.aviso
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            // Actions.
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 8
                spacing: 8
                BotonSecundario {
                    text: Tema.t("modsRefresh")
                    enabled: !raiz.ocupado
                    onClicked: raiz.modelo.refresh()
                }
                BotonSecundario {
                    text: Tema.t("modsOpenFolder")
                    onClicked: raiz.modelo.abrirCarpeta()
                }
                BotonSecundario {
                    text: Tema.t("modsCheck")
                    enabled: !raiz.ocupado
                    onClicked: raiz.comprobar()
                }
                BotonSecundario {
                    text: Tema.t("modsImport")
                    enabled: !raiz.ocupado
                    onClicked: dialogoCarpeta.open()
                }
                CheckBox {
                    id: reemplazar
                    text: Tema.t("modsReplace")
                    font.pixelSize: 12
                    palette.text: Tema.textoSuave
                    palette.windowText: Tema.textoSuave
                }
                Item { Layout.fillWidth: true }
                BotonSecundario {
                    text: Tema.t("modsRestore")
                    peligro: true
                    enabled: !raiz.ocupado && raiz.modelo && raiz.modelo.active
                    onClicked: raiz.restaurar()
                }
            }

            // Mod rows.
            Repeater {
                model: raiz.filtrados
                delegate: Rectangle {
                    id: tarjeta
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.bottomMargin: 8
                    implicitHeight: contenido.implicitHeight + 24
                    radius: 8
                    color: modelData.enabled ? "#1b1e25" : "#16181d"
                    border.width: 1
                    border.color: modelData.enabled ? Tema.bordeClaro : Tema.borde

                    RowLayout {
                        id: contenido
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 16
                        anchors.rightMargin: 16
                        spacing: 16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            RowLayout {
                                spacing: 8
                                Text {
                                    text: tarjeta.modelData.name
                                    color: Tema.texto
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Rectangle {
                                    implicitWidth: etiqueta.implicitWidth + 12
                                    implicitHeight: 20
                                    radius: 4
                                    color: tarjeta.modelData.valid ? "#1c3a2a" : "#3a1714"
                                    Text {
                                        id: etiqueta
                                        anchors.centerIn: parent
                                        text: tarjeta.modelData.valid ? Tema.t("modsValid") : Tema.t("modsInvalid")
                                        color: tarjeta.modelData.valid ? Tema.bien : Tema.mal
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: tarjeta.modelData.mod + " · " + tarjeta.modelData.type + " · "
                                      + Tema.t("modsPriority") + " " + tarjeta.modelData.priority
                                color: Tema.textoTenue
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: (tarjeta.modelData.description || "").length > 0
                                text: tarjeta.modelData.description || ""
                                textFormat: Text.PlainText
                                color: Tema.textoSuave
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: (tarjeta.modelData.author || "").length > 0
                                         || (tarjeta.modelData.homepage || "").length > 0
                                text: (tarjeta.modelData.author || "") + " · " + (tarjeta.modelData.homepage || "")
                                textFormat: Text.PlainText
                                color: Tema.textoTenue
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: textoCap.length > 0
                                text: textoCap
                                textFormat: Text.PlainText
                                color: Tema.textoSuave
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: tarjeta.modelData.issueCount > 0
                                text: tarjeta.modelData.issueText
                                       + (tarjeta.modelData.issueCount > 1
                                          ? "  (+" + (tarjeta.modelData.issueCount - 1) + ")" : "")
                                color: Tema.mal
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                        }

                        ColumnLayout {
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 6
                            Interruptor {
                                Layout.alignment: Qt.AlignHCenter
                                checked: tarjeta.modelData.enabled
                                enabled: tarjeta.modelData.valid && !raiz.ocupado
                                onToggled: raiz.alternar(tarjeta.modelData, checked)
                            }
                            BotonSecundario {
                                text: Tema.t("modsExport")
                                implicitWidth: 88
                                implicitHeight: 28
                                enabled: !raiz.ocupado
                                onClicked: raiz.exportarMod(tarjeta.modelData.key)
                            }
                        }
                    }

                    readonly property string textoCap: {
                        const caps = tarjeta.modelData.capabilities
                        return caps && caps.length > 0 ? Tema.t("modsCapabilities") + " " + caps.join(", ") : ""
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                Layout.bottomMargin: 8
                visible: raiz.filtrados.length === 0
                text: Tema.t("modsEmpty")
                color: Tema.textoTenue
                font.pixelSize: 13
                wrapMode: Text.WordWrap
            }

            // Plan diagnostics (errors, warnings, conflicts and excluded mods).
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 6
                visible: raiz.diag.length > 0
                implicitHeight: panelDiag.implicitHeight + 24
                radius: 8
                color: "#191c22"
                border.width: 1
                border.color: Tema.borde
                ColumnLayout {
                    id: panelDiag
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 14
                    spacing: 6
                    Text {
                        text: Tema.t("modsDiagTitle").toLocaleUpperCase()
                        color: Tema.textoTenue
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        font.letterSpacing: 1.4
                    }
                    Repeater {
                        model: raiz.diag
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 8
                            Rectangle {
                                width: 6
                                height: 6
                                radius: 3
                                color: modelData.severity === "warning" ? Tema.aviso : Tema.mal
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.message
                                color: Tema.textoSuave
                                font.pixelSize: 12
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            // Backend message / last error.
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 8
                visible: raiz.modelo && (raiz.modelo.lastError.length > 0 || raiz.modelo.notice.length > 0)
                text: raiz.modelo ? (raiz.modelo.lastError.length > 0 ? raiz.modelo.lastError : raiz.modelo.notice) : ""
                color: raiz.modelo && raiz.modelo.lastError.length > 0 ? Tema.mal : Tema.textoTenue
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: 6
                Layout.bottomMargin: 18
                text: raiz.modelo && !raiz.modelo.pythonReady ? Tema.t("modsNoPython") : Tema.t("modsScope")
                color: Tema.textoTenue
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }
        }
    }

    // Drag & drop overlay: drop a .zip or an unpacked folder anywhere on the Mods page.
    Rectangle {
        anchors.fill: parent
        visible: raiz.arrastrando
        z: 10
        radius: 10
        color: "#e6121419"
        border.width: 2
        border.color: Tema.oro
        Text {
            anchors.centerIn: parent
            text: Tema.t("modsDropHere")
            color: Tema.oroClaro
            font.pixelSize: 20
            font.weight: Font.Bold
        }
    }

    DropArea {
        anchors.fill: parent
        z: 11
        onEntered: (drag) => { raiz.arrastrando = true; drag.accept(Qt.CopyAction) }
        onExited: raiz.arrastrando = false
        onDropped: (drop) => {
            raiz.arrastrando = false
            raiz.instalarSoltados(drop.urls)
            drop.accept(Qt.CopyAction)
        }
    }

    FolderDialog {
        id: dialogoCarpeta
        title: Tema.t("modsImportTitle")
        onAccepted: {
            const r = raiz.modelo.importar(lanzador.rutaDesdeUrl(selectedFolder), reemplazar.checked)
            if (r.ok) {
                raiz.aviso(Tema.t("modsImportDone"))
                raiz.modelo.refresh()
            } else {
                raiz.fallo(Tema.t("modsImportFailed"), r.message || "")
            }
        }
    }

    Dialog {
        id: dialogoPerfil
        title: Tema.t("modsProfileNew")
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        ColumnLayout {
            anchors.fill: parent
            TextField {
                id: nombrePerfil
                Layout.fillWidth: true
                placeholderText: Tema.t("modsProfileName")
                placeholderTextColor: Tema.textoTenue
                color: Tema.texto
                background: Rectangle {
                    radius: 6
                    color: Tema.campo
                    border.width: 1
                    border.color: Tema.borde
                }
            }
            CheckBox {
                id: copiarActual
                text: Tema.t("modsProfileCopy")
                checked: true
                font.pixelSize: 12
                palette.text: Tema.textoSuave
                palette.windowText: Tema.textoSuave
            }
        }
        onAccepted: {
            const nombre = nombrePerfil.text.trim()
            if (nombre.length === 0) return
            const r = raiz.modelo.crearPerfil(nombre, copiarActual.checked ? raiz.modelo.profile : "")
            if (!r.ok)
                raiz.fallo(Tema.t("modsProfileNew"), r.message || "")
            else
                raiz.modelo.cambiarPerfil(nombre)
        }
    }
}
