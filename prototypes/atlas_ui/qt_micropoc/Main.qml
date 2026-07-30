import QtQuick
import QtQuick.Window

// Réplica del micro-PoC de referencia (glow + partículas orbitando, fps en
// vivo, cliente WS real contra el bridge de Atlas) — mismos criterios que
// prototypes/atlas_ui/flutter_micropoc/ y compose_micropoc/ para
// comparación directa. Nota: MultiEffect (Qt Quick Effects) requiere Qt
// 6.5+; esta máquina tiene Qt 6.4.2 (repos de Linux Mint 22.3/Ubuntu
// noble), así que el glow usa un ShaderEffect GLSL custom en su lugar —
// misma técnica de fondo que Flutter (SkSL/GLSL) y Compose (SkSL), sin la
// capa de conveniencia que citaba research-kmp-qt-slint.md.

Window {
    id: root
    width: 900
    height: 700
    visible: true
    title: "Atlas micro-PoC (Qt6/QML)"
    color: "black"

    ShaderEffect {
        id: glow
        anchors.fill: parent
        property real uTime: 0
        property size uSize: Qt.size(width, height)
        fragmentShader: "qrc:/shaders/shaders/glow.frag.qsb"

        NumberAnimation on uTime {
            from: 0
            to: 100000
            duration: 100000000
            loops: Animation.Infinite
            running: true
        }
    }

    property real orbitAngle: 0
    NumberAnimation on orbitAngle {
        from: 0
        to: 2 * Math.PI
        duration: 8000
        loops: Animation.Infinite
        running: true
    }

    Repeater {
        model: 24
        delegate: Rectangle {
            width: 8
            height: 8
            radius: 4
            color: "#00D9FF"
            property real angleOffset: index * (2 * Math.PI / 24)
            property real orbitRadius: Math.min(root.width, root.height) * 0.32
            x: root.width / 2 + orbitRadius * Math.cos(root.orbitAngle + angleOffset) - width / 2
            y: root.height / 2 + orbitRadius * Math.sin(root.orbitAngle + angleOffset) - height / 2
        }
    }

    Column {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 16
        spacing: 4
        Text {
            text: "fps: " + Math.round(statsController.fps)
            color: "white"
            font.pixelSize: 16
        }
        Text {
            text: "ws: " + statsController.wsStatus + "  events: " + statsController.wsEvents
            color: "white"
            font.pixelSize: 12
        }
    }
}
