import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

// Install tab: three steps, each one click. 1. the build tools (downloaded into data/_tools), 2. the game ISO (language
// detected), 3. install: runtime, disc, build and the first-play preparation in one run, with one progress bar.
// Maintenance actions (runtime repair, quick rebuild, visited areas) are folded away below. Backed by "installer"
// (src/installer_backend.cpp), which runs tools/pipeline/build.ps1.
ScrollView {
    id: root
    contentWidth: availableWidth
    clip: true

    property var env: installer.environment()
    property var discs: []          // identified ISOs: [{path, label, language, kind, compatible, problems}]
    property var languages: installer.languages()
    property var pendingIsos: []    // chosen before the tools existed: identified once they are downloaded
    property string step: ""
    property string status: ""
    property int done: 0
    property int total: 0
    property int stepIndex: 0       // steps seen in the current run (for the overall progress line)
    property var log: []
    property bool showLog: false
    property bool showMore: false
    property bool prepareFirstPlay: true   // the install ends with the first-play preparation (optimize stage)
    property bool scanDisc: false
    property var scanReport: installer.discScanReport()
    property bool lastOk: true

    function refresh() {
        env = installer.environment()
        languages = installer.languages()
        scanReport = installer.discScanReport()
    }
    function compatibleIsos() {
        var out = []
        for (var i = 0; i < discs.length; ++i)
            if (discs[i].compatible) out.push(discs[i].path)
        return out
    }
    function addLog(line) {
        var l = log.slice(-400)
        l.push(line)
        log = l
    }
    function begin() { log = []; done = 0; total = 0; status = ""; stepIndex = 0; lastOk = true }
    function install() {
        begin()
        var stages = "tools,fetch"
        if (compatibleIsos().length > 0) stages += ",discs"
        if (scanDisc) stages += ",vu1disc"
        stages += ",configure,recomp,sync"
        // with the first-play preparation one "tune" pass replaces build + optimize and adds the profile-guided build
        // (build.ps1 stage tune); without it the plain build
        // On small CPUs (4 threads or fewer) the profile-guided pass is two full -O3 builds, about an extra hour or more:
        // record the game on the plain build instead (build + optimize); the "pgo" maintenance button stays available.
        if (!prepareFirstPlay) stages += ",build"
        else stages += installer.cpuThreads() <= 4 ? ",build,optimize" : ",tune"
        installer.run(stages, { isos: compatibleIsos(), config: "Release" })
    }
    function maintenance(stages) { begin(); installer.run(stages, { config: "Release" }) }
    function pickIsos(paths) {
        if (env.tools) { installer.identify(paths); return }
        pendingIsos = paths                 // reading an ISO needs the portable Python: fetch the tools first
        begin()
        installer.run("tools", {})
    }
    // friendly name of a pipeline step ("=== <step> ===" lines of build.ps1)
    function stepLabel(s) {
        var map = [["verify runtime", "instStepVerify"], ["build tools", "instStepTools"], ["runtime", "instStepRuntime"], ["discs", "instStepDiscs"],
                   ["configure", "instStepConfigure"], ["recompile", "instStepRecomp"], ["generated code", "instStepSync"],
                   ["build the game", "instStepBuild"], ["record", "instStepRecord"], ["native VU1", "instStepNative"],
                   ["rebuild", "instStepBuild"], ["profile-guided", "instStepPgo"], ["VU1 microcode from the disc", "instStepVu1Disc"]]
        for (var i = 0; i < map.length; ++i)
            if (s.indexOf(map[i][0]) === 0 || s.indexOf(map[i][0]) > 0) return Tema.t(map[i][1])
        return s
    }
    readonly property bool canInstall: !installer.running && (compatibleIsos().length > 0 || languages.length > 0)

    Connections {
        target: installer
        function onIdentified(list) {
            var merged = root.discs.slice()
            for (var i = 0; i < list.length; ++i) {
                var dup = false
                for (var j = 0; j < merged.length; ++j) if (merged[j].path === list[i].path) dup = true
                if (!dup) merged.push(list[i])
            }
            root.discs = merged
        }
        function onStepChanged(s) {
            root.step = s; root.status = ""; root.done = 0; root.total = 0; root.stepIndex += 1
            root.addLog("— " + s)
        }
        function onProgress(d, t) { root.done = d; root.total = t }
        function onStatusText(t) { root.status = t }
        function onLogLine(l) { root.addLog(l) }
        function onFinished(ok, code) {
            root.lastOk = ok
            root.step = ok ? Tema.t("instDone") : Tema.tf("instFailed", code)
            if (!ok) root.showLog = true
            root.refresh()
            if (ok && root.pendingIsos.length > 0) {
                var p = root.pendingIsos
                root.pendingIsos = []
                installer.identify(p)
            }
        }
    }

    FileDialog {
        id: isoDialog
        title: Tema.t("instPickIso")
        fileMode: FileDialog.OpenFiles
        nameFilters: ["ISO (*.iso *.ISO)", "* (*)"]
        onAccepted: {
            var paths = []
            for (var i = 0; i < selectedFiles.length; ++i) paths.push(lanzador.rutaDesdeUrl(selectedFiles[i]))
            root.pickIsos(paths)
        }
    }

    // one numbered step: a title line with a status mark, a description and its controls
    component Paso: ColumnLayout {
        id: paso
        property int numero: 1
        property string titulo
        property string descripcion
        property bool hecho: false
        property bool activo: true
        default property alias contenido: cuerpo.data
        Layout.fillWidth: true
        spacing: 8
        opacity: activo ? 1.0 : 0.55
        RowLayout {
            spacing: 12
            Rectangle {
                width: 30; height: 30; radius: 15
                color: paso.hecho ? Tema.bien : "transparent"
                border.color: paso.hecho ? Tema.bien : Tema.oro
                border.width: 2
                Text {
                    anchors.centerIn: parent
                    text: paso.hecho ? "✔" : paso.numero
                    color: paso.hecho ? Tema.fondo : Tema.oro
                    font.pixelSize: 14; font.weight: Font.Bold
                }
            }
            Text { text: paso.titulo; color: Tema.oroClaro; font.pixelSize: 17; font.weight: Font.Medium; Layout.fillWidth: true }
        }
        Text {
            visible: paso.descripcion.length > 0
            Layout.fillWidth: true
            Layout.leftMargin: 42
            wrapMode: Text.WordWrap
            color: Tema.textoSuave
            font.pixelSize: 13
            text: paso.descripcion
        }
        ColumnLayout { id: cuerpo; Layout.fillWidth: true; Layout.leftMargin: 42; spacing: 8 }
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: 22

        // after a launcher update that changed the runtime patches (data/needs-rebuild.txt)
        Rectangle {
            visible: installer.needsRebuild() && root.env.game && !installer.running
            Layout.fillWidth: true
            implicitHeight: aviso.implicitHeight + 28
            radius: 6
            color: "#2a1d0c"
            border.color: Tema.aviso
            RowLayout {
                id: aviso
                anchors.fill: parent
                anchors.margins: 14
                spacing: 14
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: Tema.texto
                    font.pixelSize: 13
                    text: Tema.t("instUpdateRebuild")
                }
                BotonSecundario {
                    text: Tema.t("instUpdateRebuildRun")
                    onClicked: root.maintenance("tools,fetch,configure,recomp,sync,build")
                }
            }
        }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Tema.textoSuave
            font.pixelSize: 13
            text: Tema.t("instIntro")
        }

        // ---------------------------------------------------------------- 1. tools
        Paso {
            numero: 1
            titulo: Tema.t("instToolsTitle")
            descripcion: root.env.tools ? Tema.t("instToolsOk") : Tema.t("instToolsDesc")
            hecho: root.env.tools
            BotonSecundario {
                visible: !root.env.tools
                text: Tema.t("instToolsGet")
                enabled: !installer.running
                onClicked: root.maintenance("tools")
            }
        }

        // ---------------------------------------------------------------- 2. ISO
        Paso {
            numero: 2
            titulo: Tema.t("instIsoTitle")
            descripcion: Tema.t("instDiscsDesc")
            hecho: root.compatibleIsos().length > 0 || root.languages.length > 0
            Repeater {
                model: root.discs
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: (modelData.compatible ? "✔  " : "✖  ") + (modelData.label || modelData.path)
                        color: modelData.compatible ? Tema.bien : Tema.mal
                        font.pixelSize: 14
                    }
                    Text {
                        text: modelData.path + (modelData.problems && modelData.problems.length ? " — " + modelData.problems.join("; ") : "")
                        color: Tema.textoTenue
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
            }
            Repeater {
                model: root.discs.length === 0 ? root.languages : []
                delegate: Text {
                    required property var modelData
                    text: "●  " + modelData.label + "  (" + Tema.t("instQuality_" + modelData.quality) + ")"
                    color: Tema.texto
                    font.pixelSize: 13
                }
            }
            Text {
                visible: root.pendingIsos.length > 0
                text: Tema.t("instIsoWaitTools")
                color: Tema.aviso
                font.pixelSize: 13
            }
            RowLayout {
                spacing: 10
                BotonSecundario { text: Tema.t("instAddIso"); enabled: !installer.running; onClicked: isoDialog.open() }
                BotonSecundario {
                    text: Tema.t("instClearIso")
                    visible: root.discs.length > 0
                    enabled: !installer.running
                    onClicked: root.discs = []
                }
            }
        }

        // ---------------------------------------------------------------- 3. install
        BotonSecundario {
            text: Tema.t("openGameExecutable")
            visible: root.env.game
            onClicked: installer.openRunnerFolder()
        }
        Paso {
            numero: 3
            titulo: root.env.game ? Tema.t("instGameReady") : Tema.t("instInstallTitle")
            descripcion: root.env.game ? Tema.t("instGameReadyDesc") : Tema.t("instInstallDesc")
            hecho: root.env.game && !installer.running
            activo: root.canInstall || installer.running || root.env.game
            Fila {
                titulo: Tema.t("instDiscScanOption")
                descripcion: Tema.t("instVu1DiscDesc")
                Interruptor { checked: root.scanDisc; enabled: !installer.running; onToggled: root.scanDisc = checked }
            }
            Fila {
                titulo: Tema.t("instFirstPlay")
                descripcion: Tema.t("instFirstPlayDesc")
                Interruptor { checked: root.prepareFirstPlay; onToggled: root.prepareFirstPlay = checked }
            }
            RowLayout {
                spacing: 10
                BotonSecundario {
                    text: root.env.game ? Tema.t("instRebuildAll") : Tema.t("instInstall")
                    enabled: root.canInstall
                    onClicked: root.install()
                }
                BotonSecundario {
                    text: Tema.t("instCancel")
                    peligro: true
                    visible: installer.running
                    onClicked: installer.cancel()
                }
            }
        }

        // ---------------------------------------------------------------- progress
        ColumnLayout {
            visible: installer.running || root.step.length > 0
            Layout.fillWidth: true
            spacing: 6
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: (installer.running ? root.stepLabel(root.step) : root.step)
                      + (installer.running && root.total > 0 ? "  —  " + Math.round(100 * root.done / root.total) + "%" : "")
                color: root.lastOk ? Tema.texto : Tema.mal
                font.pixelSize: 15
                font.weight: Font.Medium
            }
            Text {
                visible: installer.running && root.status.length > 0
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: root.status
                color: Tema.textoSuave
                font.pixelSize: 12
            }
            Rectangle {
                id: trilho
                Layout.fillWidth: true
                height: 8
                radius: 4
                color: Tema.campo
                border.color: Tema.borde
                clip: true
                // a step with a count: the bar grows from the left edge
                Rectangle {
                    visible: root.total > 0
                    x: 0
                    width: root.total > 0 ? trilho.width * Math.min(1, root.done / root.total) : 0
                    height: parent.height
                    radius: 4
                    color: Tema.oro
                    Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                }
                // a step without a count yet: a block sweeping back and forth
                Rectangle {
                    id: varredura
                    visible: installer.running && root.total === 0
                    width: trilho.width * 0.25
                    height: parent.height
                    radius: 4
                    color: Tema.oro
                    opacity: 0.8
                    SequentialAnimation on x {
                        running: varredura.visible
                        loops: Animation.Infinite
                        NumberAnimation { from: 0; to: trilho.width - varredura.width; duration: 1200; easing.type: Easing.InOutSine }
                        NumberAnimation { from: trilho.width - varredura.width; to: 0; duration: 1200; easing.type: Easing.InOutSine }
                    }
                }
            }
            BotonSecundario {
                text: root.showLog ? Tema.t("instHideLog") : Tema.t("instShowLog")
                visible: root.log.length > 0
                onClicked: root.showLog = !root.showLog
            }
            Rectangle {
                visible: root.showLog && root.log.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: 200
                color: Tema.campo
                border.color: Tema.borde
                radius: 4
                ListView {
                    id: logView
                    anchors.fill: parent
                    anchors.margins: 8
                    clip: true
                    model: root.log
                    onCountChanged: positionViewAtEnd()
                    delegate: Text {
                        required property var modelData
                        width: logView.width
                        text: modelData
                        color: Tema.textoSuave
                        font.family: "Consolas"
                        font.pixelSize: 12
                        wrapMode: Text.WrapAnywhere
                    }
                }
            }
        }

        // ---------------------------------------------------------------- maintenance (folded)
        BotonSecundario {
            text: (root.showMore ? "▾  " : "▸  ") + Tema.t("instMore")
            onClicked: root.showMore = !root.showMore
        }
        ColumnLayout {
            visible: root.showMore
            Layout.fillWidth: true
            spacing: 10
            Fila {
                titulo: Tema.t("instNative")
                descripcion: Tema.t("instNativeDesc")
                BotonSecundario { text: Tema.t("instRun"); enabled: !installer.running && root.env.game; onClicked: root.maintenance("native") }
            }
            Fila {
                titulo: Tema.t("instQuick")
                descripcion: Tema.t("instQuickDesc")
                BotonSecundario { text: Tema.t("instRun"); enabled: !installer.running && root.env.game; onClicked: root.maintenance("sync,build") }
            }
            Fila {
                titulo: Tema.t("instVu1Disc")
                descripcion: Tema.t("instVu1DiscDesc")
                BotonSecundario { text: Tema.t("instRun"); enabled: !installer.running && root.env.game; onClicked: root.maintenance("vu1disc,native") }
            }
            Text {
                visible: root.scanReport.complete === true
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: Tema.tf("instDiscReport", root.scanReport.files || 0, root.scanReport.blocks || 0)
                color: Tema.textoSuave
                font.pixelSize: 13
            }
            Fila {
                // the installed game's build tells whether the profile is in use (InstallerBackend::pgoApplied)
                readonly property bool aplicado: root.env.game && !installer.running && installer.pgoApplied()
                titulo: Tema.t("instPgo") + (aplicado ? "  ·  " + Tema.t("instPgoOn") : (root.env.game ? "  ·  " + Tema.t("instPgoRec") : ""))
                descripcion: Tema.t("instPgoDesc")
                BotonSecundario { text: Tema.t("instRun"); enabled: !installer.running && root.env.game; onClicked: root.maintenance("pgo") }
            }
            Fila {
                titulo: Tema.t("instRuntime")
                descripcion: root.env.runtime ? Tema.t("instRuntimeOk") : Tema.t("instRuntimeMissing")
                BotonSecundario { text: Tema.t("instRuntimeUpdate"); enabled: !installer.running; onClicked: root.maintenance("tools,fetch") }
            }
        }
        Item { Layout.preferredHeight: 12 }
    }
}
