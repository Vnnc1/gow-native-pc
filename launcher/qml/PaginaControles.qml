import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Teclas.js" as Teclas

// "Controls" tab: gamepad layout (fixed or button by button, TOBIICHI_MANDO), Escape, fully configurable keyboard/mouse
// (TOBIICHI_TECLAS).
ScrollView {
    id: raiz
    required property var ajustes
    readonly property var mapa: Teclas.leer(ajustes.teclas)
    readonly property var mapaMando: Teclas.leerMando(ajustes.mando, ajustes.controlesDmc5)
    property string capturaAccion: ""
    property int capturaIndice: 0
    property bool capturaEsMando: false   // the capture waits for a controller button (mando.boton)
    contentWidth: availableWidth
    clip: true

    function guardar(nuevo) {
        ajustes.teclas = JSON.stringify(nuevo)
    }

    function textoAviso(accion, codigo) {
        if (!codigo)
            return ""
        if (Teclas.reservada(codigo))
            return Tema.t("reservadaAviso")
        const otras = Teclas.conflictos(mapa, accion, codigo)
        if (otras.length === 0)
            return ""
        return Tema.tf("conflicto", otras.map((id) => Tema.t("acc_" + id)).join(", "))
    }

    function abrirCaptura(accion, indice) {
        capturaEsMando = false
        capturaAccion = accion
        capturaIndice = indice
        captura.open()
    }

    function asignar(codigo) {
        if (codigo > 0)
            guardar(Teclas.asignar(mapa, capturaAccion, capturaIndice, codigo))
        captura.close()
    }

    // controller layout: saved only once changed (empty = the fixed layout chosen above)
    function guardarMando(nuevo) {
        ajustes.mando = JSON.stringify(nuevo)
    }
    function textoAvisoMando(accion, codigo) {
        if (!codigo)
            return ""
        const otras = Teclas.conflictosMando(mapaMando, accion, codigo)
        return otras.length === 0 ? "" : Tema.tf("conflicto", otras.map((id) => Tema.t("acc_" + id)).join(", "))
    }
    function abrirCapturaMando(accion, indice) {
        capturaEsMando = true
        capturaAccion = accion
        capturaIndice = indice
        mando.escuchar(true)
        captura.open()
    }
    function asignarMando(codigo) {
        if (codigo > 0)
            guardarMando(Teclas.asignar(mapaMando, capturaAccion, capturaIndice, codigo))
        captura.close()
    }

    Connections {
        target: mando
        function onBoton(codigo) { if (captura.opened && raiz.capturaEsMando) raiz.asignarMando(codigo) }
    }

    // a row of the controller section: PS2 button, action, two controller-button slots
    component FilaMando: Rectangle {
        id: filaMando
        required property var modelData
        readonly property var codigos: raiz.mapaMando[modelData.id] || []
        Layout.fillWidth: true
        implicitHeight: 42
        radius: 5
        color: zonaMando.containsMouse ? "#181b21" : "transparent"
        MouseArea {
            id: zonaMando
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 4
            spacing: 12
            Rectangle {
                Layout.preferredWidth: 58
                Layout.preferredHeight: 24
                radius: 12
                color: "#1c1f26"
                border.width: 1
                border.color: Tema.borde
                Text {
                    anchors.centerIn: parent
                    text: filaMando.modelData.boton
                    color: Tema.textoSuave
                    font.pixelSize: filaMando.modelData.boton.length > 4 ? 10 : 12
                    font.weight: Font.DemiBold
                }
            }
            Text {
                Layout.fillWidth: true
                text: Tema.t("acc_" + filaMando.modelData.id)
                color: Tema.texto
                font.pixelSize: 14
                elide: Text.ElideRight
            }
            Repeater {
                model: 2
                delegate: TeclaAsignable {
                    required property int index
                    readonly property int miCodigo: index < filaMando.codigos.length ? filaMando.codigos[index] : 0
                    esMando: true
                    codigo: miCodigo
                    capturando: captura.opened && raiz.capturaEsMando && raiz.capturaAccion === filaMando.modelData.id && raiz.capturaIndice === index
                    aviso: raiz.textoAvisoMando(filaMando.modelData.id, miCodigo)
                    conflicto: aviso.length > 0
                    onElegir: raiz.abrirCapturaMando(filaMando.modelData.id, Math.min(index, filaMando.codigos.length))
                    onBorrar: if (miCodigo !== 0) raiz.guardarMando(Teclas.asignar(raiz.mapaMando, filaMando.modelData.id, index, 0))
                }
            }
        }
    }

    component Grupo: Text {
        Layout.topMargin: 18
        Layout.bottomMargin: 6
        color: Tema.oro
        font.family: Tema.fuenteTitulo
        font.pixelSize: 14
        font.weight: Font.Bold
        font.letterSpacing: 2
    }

    component FilaAccion: Rectangle {
        id: fila
        required property var modelData
        readonly property var codigos: raiz.mapa[modelData.id] || []
        Layout.fillWidth: true
        implicitHeight: 42
        radius: 5
        color: zonaFila.containsMouse ? "#181b21" : "transparent"
        MouseArea {
            id: zonaFila
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 4
            spacing: 12
            Rectangle {
                // The PS2 pad button the action maps to.
                Layout.preferredWidth: 58
                Layout.preferredHeight: 24
                radius: 12
                color: "#1c1f26"
                border.width: 1
                border.color: Tema.borde
                Text {
                    anchors.centerIn: parent
                    text: fila.modelData.boton
                    color: Tema.textoSuave
                    font.pixelSize: fila.modelData.boton.length > 4 ? 10 : 12
                    font.weight: Font.DemiBold
                }
            }
            Text {
                Layout.fillWidth: true
                text: Tema.t("acc_" + fila.modelData.id)
                color: Tema.texto
                font.pixelSize: 14
                elide: Text.ElideRight
            }
            Repeater {
                model: 2
                delegate: TeclaAsignable {
                    required property int index
                    readonly property int miCodigo: index < fila.codigos.length ? fila.codigos[index] : 0
                    codigo: miCodigo
                    capturando: captura.opened && raiz.capturaAccion === fila.modelData.id && raiz.capturaIndice === index
                    aviso: raiz.textoAviso(fila.modelData.id, miCodigo)
                    conflicto: aviso.length > 0
                    onElegir: raiz.abrirCaptura(fila.modelData.id, Math.min(index, fila.codigos.length))
                    onBorrar: if (miCodigo !== 0) raiz.guardar(Teclas.asignar(raiz.mapa, fila.modelData.id, index, 0))
                }
            }
        }
    }

    ColumnLayout {
        width: raiz.availableWidth
        spacing: 0

        Fila {
            titulo: Tema.t("mandoEsquema")
            descripcion: Tema.t("mandoEsquemaDesc")
            Selector {
                opciones: [{ texto: Tema.t("mandoModerno"), valor: true }, { texto: Tema.t("mandoClasico"), valor: false }]
                valor: raiz.ajustes.controlesDmc5
                // a fixed layout replaces a controller layout changed button by button
                onElegido: (v) => { raiz.ajustes.controlesDmc5 = v; raiz.ajustes.mando = "" }
            }
        }
        Fila {
            titulo: Tema.t("cancelarAnimaciones")
            descripcion: Tema.t("cancelarAnimacionesDesc")
            Interruptor {
                checked: raiz.ajustes.cancelarAnimaciones
                onToggled: raiz.ajustes.cancelarAnimaciones = checked
            }
        }
        Fila {
            // gow-native-pc: accessibility — holding a button instead of mashing it in the minigames (GOW_QTE_HOLD)
            titulo: Tema.t("qteHold")
            descripcion: Tema.t("qteHoldDesc")
            Interruptor {
                checked: raiz.ajustes.qteHold
                onToggled: raiz.ajustes.qteHold = checked
            }
        }
        Fila {
            titulo: Tema.t("qteHoldButtons")
            descripcion: Tema.t("qteHoldButtonsDesc")
            habilitada: raiz.ajustes.qteHold
            Selector {
                opciones: [
                    { texto: Tema.t("qteHoldCircle"), valor: "circle" },
                    { texto: Tema.t("qteHoldFace"), valor: "face" }
                ]
                valor: raiz.ajustes.qteHoldButtons
                onElegido: (v) => raiz.ajustes.qteHoldButtons = v
            }
        }
        Fila {
            titulo: Tema.t("qteHoldRate")
            descripcion: Tema.t("qteHoldRateDesc")
            habilitada: raiz.ajustes.qteHold
            Selector {
                opciones: [{ texto: "6", valor: 6 }, { texto: "10", valor: 10 }, { texto: "14", valor: 14 },
                           { texto: "20", valor: 20 }]
                valor: raiz.ajustes.qteHoldRate
                onElegido: (v) => raiz.ajustes.qteHoldRate = v
            }
        }
        Fila {
            titulo: Tema.t("escSalir")
            descripcion: Tema.t("escSalirDesc")
            separador: false
            Interruptor {
                checked: raiz.ajustes.escSalir
                onToggled: raiz.ajustes.escSalir = checked
            }
        }

        // ---------------------------------------------------------------- controller, button by button
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 22
            spacing: 12
            Text {
                Layout.fillWidth: true
                text: Tema.t("mandoTitulo").toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
                color: Tema.oroClaro
                font.family: Tema.fuenteTitulo
                font.pixelSize: 17
                font.weight: Font.Bold
                font.letterSpacing: 2
            }
            BotonSecundario {
                text: Tema.t("tecladoRestablecer")
                enabled: raiz.ajustes.mando.length > 0
                onClicked: raiz.ajustes.mando = ""
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: (mando.conectado ? "●  " + Tema.t("mandoConectado") : "○  " + Tema.t("mandoNinguno"))
            color: mando.conectado ? Tema.bien : Tema.aviso
            font.pixelSize: 13
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: Tema.t("mandoDesc")
            color: Tema.textoTenue
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }
        Repeater {
            model: Teclas.grupos.filter((g) => g !== "grupoMovimiento" && g !== "grupoAvanzado")
            delegate: ColumnLayout {
                id: grupoMando
                required property string modelData
                Layout.fillWidth: true
                spacing: 2
                Grupo {
                    text: Tema.t(grupoMando.modelData).toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
                }
                Repeater {
                    model: Teclas.accionesMando.filter((a) => a.grupo === grupoMando.modelData)
                    delegate: FilaMando {}
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 22
            spacing: 12
            Text {
                Layout.fillWidth: true
                text: Tema.t("tecladoTitulo").toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
                color: Tema.oroClaro
                font.family: Tema.fuenteTitulo
                font.pixelSize: 17
                font.weight: Font.Bold
                font.letterSpacing: 2
            }
            BotonSecundario {
                text: Tema.t("tecladoRestablecer")
                onClicked: raiz.ajustes.teclas = ""
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: Tema.t("tecladoDesc")
            color: Tema.textoTenue
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }

        Repeater {
            model: Teclas.grupos
            delegate: ColumnLayout {
                id: grupo
                required property string modelData
                Layout.fillWidth: true
                spacing: 2
                Grupo {
                    text: Tema.t(grupo.modelData).toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
                }
                Repeater {
                    model: Teclas.acciones.filter((a) => a.grupo === grupo.modelData)
                    delegate: FilaAccion {}
                }
            }
        }

        Grupo {
            text: Tema.t("teclasSistema").toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.bottomMargin: 12
            columns: 4
            columnSpacing: 12
            rowSpacing: 8
            Tecla { texto: "F11" }
            Text { text: Tema.t("tPantalla"); color: Tema.textoSuave; font.pixelSize: 14; Layout.fillWidth: true }
            Tecla { texto: "F1" }
            Text { text: Tema.t("tPanel"); color: Tema.textoSuave; font.pixelSize: 14; Layout.fillWidth: true }
            Tecla { texto: "F2" }
            Text { text: Tema.t("tTrucos"); color: Tema.textoSuave; font.pixelSize: 14; Layout.fillWidth: true }
        }
    }

    // Key capture: covers the whole window so mouse clicks are caught too.
    Popup {
        id: captura
        parent: Overlay.overlay
        x: 0
        y: 0
        width: parent ? parent.width : 800
        height: parent ? parent.height : 600
        modal: true
        closePolicy: Popup.NoAutoClose
        padding: 0
        background: Rectangle { color: "#c8060709" }
        onOpened: contenido.forceActiveFocus()
        onClosed: if (raiz.capturaEsMando) mando.escuchar(false)
        contentItem: Item {
            id: contenido
            focus: true
            Keys.onPressed: (evento) => {
                evento.accepted = true
                if (evento.isAutoRepeat)
                    return
                if (evento.key === Qt.Key_Escape) {
                    captura.close()
                    return
                }
                if (raiz.capturaEsMando)
                    return // controller capture: only a controller button (or Esc / a click) ends it
                raiz.asignar(Teclas.desdeEvento(evento, typeof lanzador !== "undefined" && lanzador.sistema === "linux"))
            }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.AllButtons
                onPressed: (raton) => raiz.capturaEsMando ? captura.close() : raiz.asignar(Teclas.desdeRaton(raton.button))
            }
            Rectangle {
                anchors.centerIn: parent
                width: 470
                height: 190
                radius: 8
                color: "#14161b"
                border.width: 1
                border.color: Tema.oro
                ColumnLayout {
                    anchors.centerIn: parent
                    width: parent.width - 48
                    spacing: 12
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: Tema.t("capturaTitulo").toLocaleUpperCase(Tema.idioma === "tr" ? "tr-TR" : "en-US")
                        color: Tema.oroClaro
                        font.family: Tema.fuenteTitulo
                        font.pixelSize: 22
                        font.weight: Font.Bold
                        font.letterSpacing: 2
                    }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: Tema.tf(raiz.capturaEsMando ? "capturaMandoDesc" : "capturaDesc",
                                      raiz.capturaAccion.length > 0 ? "«" + Tema.t("acc_" + raiz.capturaAccion) + "»" : "")
                        color: Tema.textoSuave
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                    }
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 64
                        height: 4
                        radius: 2
                        color: Tema.oro
                        SequentialAnimation on opacity {
                            running: captura.opened
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.25; duration: 600 }
                            NumberAnimation { to: 1.0; duration: 600 }
                        }
                    }
                }
            }
        }
    }
}
