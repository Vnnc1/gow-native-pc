import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Loading screen over the whole launcher while the pipeline builds the game (any run with a compile or a recording in
// it): one bar from start to end, the time left, the current step by its friendly name, the player's own pictures
// (data/<game>/loading, installer.loadingArt()) or the cover image fading one into the other, and tips. At the end:
// "Ready! Click PLAY" (or the failure with the log). It follows "installer" (src/installer_backend.cpp) by itself; the
// Install tab keeps its own progress lines underneath.
Item {
    id: raiz
    property string portada: ""              // the cover chosen on Home (a file path), shown when there are no pictures
    signal jugar()                           // "PLAY" on the finished screen

    // ------------------------------------------------------------------------------------------------ the plan
    // Each pipeline stage is one or more steps ("=== <step> ===" lines of tools/pipeline/build.ps1). w: expected minutes
    // on a mid-range PC (only the weights' ratios and the first estimate use them; the time left is corrected by how
    // fast this machine went so far). fixed: real-time steps (the game playing itself), not scaled.
    readonly property var etapas: ({
        tools: [{ id: "tools", w: 1 }],
        verify: [{ id: "verify", w: 5 }],
        fetch: [{ id: "fetch", w: 1.5 }],
        discs: [{ id: "discs", w: 2 }],
        configure: [{ id: "configure", w: 1 }],
        recomp: [{ id: "recomp", w: 5 }],
        sync: [{ id: "sync", w: 0.5 }],
        build: [{ id: "build", w: 12 }],
        pgo: [{ id: "pgoBuild", w: 12 }, { id: "pgoPlay", w: 4, fixed: true }, { id: "pgoRebuild", w: 12 }],
        optimize: [{ id: "record", w: 4, fixed: true }, { id: "native", w: 0.5 }, { id: "rebuild", w: 2 }],
        // tune (install with first-play preparation): instrumented build, one recorded run, final build with the profile
        tune: [{ id: "pgoBuild", w: 10 }, { id: "pgoPlay", w: 4, fixed: true }, { id: "native", w: 0.5 }, { id: "pgoRebuild", w: 9 }],
        native: [{ id: "native", w: 0.5 }, { id: "rebuild", w: 2 }],
        vu1disc: [{ id: "vu1disc", w: 3 }]
    })
    // the step of a "=== <step> ===" line (the texts build.ps1 writes)
    function pasoDe(s) {
        var map = [["verify runtime", "verify"], ["build tools", "tools"], ["runtime", "fetch"], ["discs", "discs"], ["configure", "configure"],
                   ["recompile the executable", "recomp"], ["generated code", "sync"], ["build the game", "build"],
                   ["profile-guided optimisation: instrumented", "pgoBuild"], ["profile-guided optimisation: the game", "pgoPlay"],
                   ["rebuild with the profile", "pgoRebuild"], ["record", "record"], ["native VU1", "native"], ["rebuild", "rebuild"],
                   ["VU1 microcode from the disc", "vu1disc"]]
        for (var i = 0; i < map.length; ++i)
            if (s.indexOf(map[i][0]) === 0) return map[i][1]
        return ""
    }
    function nombrePaso(id) {
        var map = { verify: "instStepVerify", tools: "instStepTools", fetch: "instStepRuntime", discs: "instStepDiscs", configure: "instStepConfigure",
                    recomp: "instStepRecomp", sync: "instStepSync", build: "instStepBuild", pgoBuild: "instStepPgo",
                    pgoPlay: "cargaPasoGrabar", pgoRebuild: "instStepPgo", record: "cargaPasoGrabar", native: "instStepNative",
                    rebuild: "cargaPasoFinal", vu1disc: "instStepVu1Disc" }
        return map[id] ? Tema.t(map[id]) : ""
    }
    function planDe(stages) {
        var out = [], lista = stages.split(",")
        for (var i = 0; i < lista.length; ++i) {
            var e = etapas[lista[i].trim()]
            if (!e) continue
            // "native" right after "optimize" is the same work (optimize already runs it)
            if (lista[i].trim() === "native" && lista.indexOf("optimize") >= 0) continue
            for (var j = 0; j < e.length; ++j) out.push({ id: e[j].id, w: e[j].w, fixed: !!e[j].fixed, real: -1 })
        }
        return out
    }
    // a run that takes long enough to deserve the screen (not "tools" or "tools,fetch" alone)
    function esLarga(stages) {
        return /(^|,)(recomp|build|optimize|native|pgo|tune|vu1disc)(,|$)/.test(stages)
    }

    // ------------------------------------------------------------------------------------------------ state
    property string estado: ""                 // "" hidden, "running", "done", "failed"
    property var plan: []
    property int actual: -1                    // index in plan of the running step
    property int hechos: 0
    property int total: 0
    property string estadoTexto: ""            // the step's @@status line
    property real inicio: 0                    // ms: run start
    property real inicioPaso: 0                // ms: step start
    property real ahora: Date.now()
    property var registro: []
    property bool verRegistro: false
    property int codigo: 0

    readonly property real fraccionPaso: total > 0 ? Math.min(1, hechos / total) : 0
    readonly property real pesoTotal: {
        var s = 0
        for (var i = 0; i < plan.length; ++i) s += plan[i].w
        return s
    }
    // Update only after a complete step/progress event, never from intermediate property assignments.
    // A revised Ninja total may lower the estimate, but must not move the overall bar backwards.
    property real progressValue: 0
    readonly property real fraccion: estado === "done" ? 1 : progressValue
    function updateProgress() {
        if (pesoTotal <= 0 || actual < 0) return
        var s = 0
        for (var i = 0; i < actual && i < plan.length; ++i) s += plan[i].w
        if (actual < plan.length) s += plan[actual].w * fraccionPaso
        // 100% belongs to the successful process exit, not its last compiler output line.
        progressValue = Math.max(progressValue, Math.min(0.99, s / pesoTotal))
    }
    // how much slower (> 1) or faster than the expected weights this machine is, from the finished scaled steps
    readonly property real ritmo: {
        var esperado = 0, real = 0
        for (var i = 0; i < actual && i < plan.length; ++i)
            if (!plan[i].fixed && plan[i].real >= 0) { esperado += plan[i].w * 60; real += plan[i].real }
        if (esperado < 60) return 1
        return Math.max(0.3, Math.min(4, real / esperado))
    }
    // seconds left: the steps still to come at this machine's pace plus what is left of the current one
    readonly property real restante: {
        if (actual < 0 || actual >= plan.length) return -1
        var p = plan[actual]
        var transcurrido = (ahora - inicioPaso) / 1000
        var resto
        if (p.fixed) resto = total > 0 ? Math.max(0, total - hechos) : Math.max(0, p.w * 60 - transcurrido)
        else {
            var previsto = p.w * 60 * ritmo
            resto = Math.max(previsto - transcurrido, previsto * 0.05)
            if (fraccionPaso > 0.08) resto = (resto + transcurrido * (1 - fraccionPaso) / fraccionPaso) / 2
        }
        for (var i = actual + 1; i < plan.length; ++i) resto += plan[i].w * 60 * (plan[i].fixed ? 1 : ritmo)
        return resto
    }
    function mmss(s) {
        s = Math.max(0, Math.round(s))
        var m = Math.floor(s / 60), r = s % 60
        return m + ":" + (r < 10 ? "0" : "") + r
    }
    function textoRestante(s) {
        if (s < 0) return ""
        if (s < 60) return Tema.t("cargaMenosMinuto")
        var m = Math.round(s / 60)
        return m >= 60 ? Tema.tf("cargaRestanteH", Math.floor(m / 60), m % 60) : Tema.tf("cargaRestante", m)
    }
    readonly property bool tieneGrabacion: {
        for (var i = 0; i < plan.length; ++i) if (plan[i].id === "record") return true
        return false
    }
    readonly property string pasoActual: actual >= 0 && actual < plan.length ? plan[actual].id : ""
    readonly property string titulo: {
        if (pasoActual === "record" || pasoActual === "pgoPlay")
            return Tema.tf("cargaPasoGrabarReloj", mmss(hechos), total > 0 ? mmss(total) : "4:00")
        return nombrePaso(pasoActual)
    }

    visible: estado.length > 0
    opacity: visible ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 300 } }

    Timer { interval: 1000; repeat: true; running: raiz.estado === "running"; onTriggered: raiz.ahora = Date.now() }

    Connections {
        target: installer
        function onRunningChanged() {
            if (!installer.running || !raiz.esLarga(installer.stages)) return
            raiz.plan = raiz.planDe(installer.stages)
            raiz.actual = -1; raiz.hechos = 0; raiz.total = 0; raiz.estadoTexto = ""; raiz.registro = []
            raiz.verRegistro = false; raiz.inicio = raiz.inicioPaso = raiz.ahora = Date.now()
            raiz.arte = installer.loadingArt()
            raiz.iniciarArte()
            raiz.progressValue = 0
            raiz.estado = "running"
        }
        function onStepChanged(s) {
            if (raiz.estado !== "running") return
            raiz.addLog("— " + s)
            var id = raiz.pasoDe(s)
            if (!id) return
            // the next step of the plan with this id (a step not in the plan, e.g. a stage's own configure, stays in the current one)
            for (var i = Math.max(0, raiz.actual + 1); i < raiz.plan.length; ++i)
                if (raiz.plan[i].id === id) {
                    var p = raiz.plan.slice()
                    if (raiz.actual >= 0) p[raiz.actual].real = (Date.now() - raiz.inicioPaso) / 1000
                    for (var k = raiz.actual + 1; k < i; ++k) p[k].real = 0   // skipped (nothing to do)
                    raiz.plan = p
                    raiz.actual = i; raiz.hechos = 0; raiz.total = 0; raiz.estadoTexto = ""
                    raiz.inicioPaso = raiz.ahora = Date.now()
                    raiz.updateProgress()
                    return
                }
        }
        function onProgress(d, t) {
            if (raiz.estado !== "running" || raiz.actual < 0 || t <= 0 || d < 0 || d > t) return
            raiz.hechos = d; raiz.total = t
            raiz.updateProgress()
        }
        function onStatusText(t) { if (raiz.estado === "running") raiz.estadoTexto = t }
        function onLogLine(l) { if (raiz.estado === "running") raiz.addLog(l) }
        function onFinished(ok, code) {
            if (raiz.estado !== "running") return
            raiz.codigo = code
            raiz.estado = ok ? "done" : "failed"
            if (!ok) raiz.verRegistro = true
        }
    }
    function addLog(line) {
        var l = registro.slice(-300)
        l.push(line)
        registro = l
    }

    // ------------------------------------------------------------------------------------------------ pictures
    property var arte: []
    readonly property var imagenes: arte.length > 0 ? arte : (portada.length > 0 ? [lanzador.urlDesdeRuta(portada)] : [])
    property int imagenActual: 0
    property bool capaA: true                // layer 0 in front (else layer 1)
    property url fuenteA: ""
    property url fuenteB: ""
    function iniciarArte() {
        imagenActual = 0; capaA = true
        fuenteA = imagenes.length > 0 ? imagenes[0] : ""
        fuenteB = imagenes.length > 1 ? imagenes[1] : ""
    }
    onImagenesChanged: iniciarArte()

    Rectangle { anchors.fill: parent; color: Tema.fondo }
    // two layers cross-fading, the front one slowly zooming; the back one already holds the next picture (every 9 s)
    Repeater {
        model: 2
        delegate: Image {
            required property int index
            readonly property bool delante: (index === 0) === raiz.capaA
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            source: index === 0 ? raiz.fuenteA : raiz.fuenteB
            opacity: delante ? 0.85 : 0
            Behavior on opacity { NumberAnimation { duration: 1500; easing.type: Easing.InOutQuad } }
            scale: delante ? 1.08 : 1.0
            Behavior on scale { NumberAnimation { duration: 9000; easing.type: Easing.Linear } }
        }
    }
    Timer {
        interval: 9000; repeat: true
        running: raiz.visible && raiz.imagenes.length > 1
        onTriggered: {
            raiz.capaA = !raiz.capaA
            raiz.imagenActual = (raiz.imagenActual + 1) % raiz.imagenes.length
            precarga.restart()
        }
    }
    Timer {
        // after the fade: the layer now at the back loads the picture after this one
        id: precarga
        interval: 1700
        onTriggered: {
            var siguiente = raiz.imagenes[(raiz.imagenActual + 1) % raiz.imagenes.length]
            if (raiz.capaA) raiz.fuenteB = siguiente; else raiz.fuenteA = siguiente
        }
    }
    Rectangle {
        // darkens towards the bottom, where the text is
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#300b0c0f" }
            GradientStop { position: 0.45; color: "#900b0c0f" }
            GradientStop { position: 1.0; color: Tema.fondo }
        }
    }
    Ascuas { anchors.fill: parent; intensidad: raiz.imagenes.length > 0 ? 0.6 : 1.2 }
    MouseArea { anchors.fill: parent; hoverEnabled: true }   // the launcher underneath takes no clicks

    // ------------------------------------------------------------------------------------------------ content
    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 56
        anchors.bottomMargin: 44
        spacing: 14

        Text {
            text: "GOD OF WAR"
            color: Tema.oroClaro
            font.family: Tema.fuenteTitulo
            font.pixelSize: 15
            font.letterSpacing: 8
            font.weight: Font.Bold
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: raiz.estado === "done" ? Tema.t("cargaListo")
                  : raiz.estado === "failed" ? Tema.tf("instFailed", raiz.codigo) : Tema.t("cargaTitulo")
            color: raiz.estado === "failed" ? Tema.mal : Tema.texto
            font.family: Tema.fuenteTitulo
            font.pixelSize: 38
            font.weight: Font.Black
        }

        // tip card (changes every 10 s while building)
        Rectangle {
            id: cartaDica
            visible: raiz.estado === "running"
            Layout.fillWidth: true
            Layout.maximumWidth: 760
            implicitHeight: dica.implicitHeight + 30
            radius: 6
            color: "#cc14161b"
            border.color: Tema.borde
            property int n: 0
            Timer {
                interval: 10000; repeat: true; running: raiz.estado === "running"
                onTriggered: { dicaFade.restart() }
            }
            SequentialAnimation {
                id: dicaFade
                NumberAnimation { target: dica; property: "opacity"; to: 0; duration: 400 }
                ScriptAction { script: cartaDica.n = (cartaDica.n + 1) % raiz.numeroDicas }
                NumberAnimation { target: dica; property: "opacity"; to: 1; duration: 400 }
            }
            Column {
                id: dica
                anchors.fill: parent
                anchors.margins: 15
                spacing: 4
                Text { text: Tema.t("cargaDica"); color: Tema.oro; font.pixelSize: 12; font.weight: Font.Bold; font.letterSpacing: 2 }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: Tema.t("cargaDica" + (cartaDica.n + 1))
                    color: Tema.texto
                    font.pixelSize: 15
                }
            }
        }

        // the step, the bar, the times
        RowLayout {
            visible: raiz.estado === "running"
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: raiz.titulo
                color: Tema.texto
                font.pixelSize: 16
                font.weight: Font.Medium
            }
            Text {
                text: Math.floor(100 * raiz.fraccion) + "%"
                color: Tema.oroClaro
                font.pixelSize: 16
                font.weight: Font.Bold
            }
        }
        Rectangle {
            id: trilho
            Layout.fillWidth: true
            height: 10
            radius: 5
            color: Tema.campo
            border.color: Tema.borde
            clip: true
            Rectangle {
                width: trilho.width * raiz.fraccion
                height: parent.height
                radius: 5
                color: raiz.estado === "failed" ? Tema.mal : (raiz.estado === "done" ? Tema.bien : Tema.oro)
                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
            }
        }
        RowLayout {
            visible: raiz.estado === "running"
            Layout.fillWidth: true
            spacing: 18
            Text {
                text: raiz.textoRestante(raiz.restante)
                color: Tema.textoSuave
                font.pixelSize: 13
            }
            Text {
                text: Tema.tf("cargaTranscurrido", raiz.mmss((raiz.ahora - raiz.inicio) / 1000))
                color: Tema.textoTenue
                font.pixelSize: 13
            }
            Text {
                Layout.fillWidth: true
                elide: Text.ElideRight
                text: raiz.estadoTexto
                color: Tema.textoTenue
                font.pixelSize: 12
            }
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: raiz.estado === "running" ? Tema.t("cargaUsarPc")
                  : raiz.estado === "failed" ? Tema.t("cargaFalloDesc")
                  : raiz.tieneGrabacion ? Tema.t("cargaListoDesc") : Tema.t("cargaListoDescSimple")
            color: Tema.textoSuave
            font.pixelSize: 13
        }

        RowLayout {
            spacing: 12
            BotonJugar {
                visible: raiz.estado === "done"
                Layout.preferredWidth: 290
                text: Tema.t("jugar")
                onClicked: { raiz.estado = ""; raiz.jugar() }
            }
            BotonSecundario {
                text: raiz.verRegistro ? Tema.t("instHideLog") : Tema.t("instShowLog")
                onClicked: raiz.verRegistro = !raiz.verRegistro
            }
            BotonSecundario {
                visible: raiz.estado === "running"
                text: Tema.t("instCancel")
                peligro: true
                onClicked: installer.cancel()
            }
            BotonSecundario {
                visible: raiz.estado === "done" || raiz.estado === "failed"
                text: Tema.t("cerrar")
                onClicked: raiz.estado = ""
            }
        }
        Rectangle {
            visible: raiz.verRegistro
            Layout.fillWidth: true
            Layout.preferredHeight: 190
            color: "#e615171c"
            border.color: Tema.borde
            radius: 4
            ListView {
                id: vistaRegistro
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                model: raiz.registro
                onCountChanged: positionViewAtEnd()
                delegate: Text {
                    required property var modelData
                    width: vistaRegistro.width
                    text: modelData
                    color: Tema.textoSuave
                    font.family: "Consolas"
                    font.pixelSize: 12
                    wrapMode: Text.WrapAnywhere
                }
            }
        }
    }
    readonly property int numeroDicas: 12
}
