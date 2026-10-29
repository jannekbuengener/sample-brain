// Variant: QML mutates a musical field that Python owns.
import QtQuick
import QtQuick.Controls

Item {
    id: root
    property var interaction
    property var screenData
    width: 480
    height: 120

    ListView {
        id: browser
        anchors.fill: parent
        model: root.screenData.browserRows
        reuseItems: true

        delegate: Row {
            spacing: 8
            // Defect: local shadow of authoritative BPM; QML "corrects" product truth.
            property real displayBpm: Number(modelData.bpm)

            Label {
                text: modelData.name
            }
            Label {
                text: String(displayBpm)
            }
            MouseArea {
                width: 64
                height: 24
                onClicked: {
                    // Defect: musical correction stays in QML instead of typed intent
                    // into Python analysis/session authority.
                    displayBpm = Math.round(displayBpm)
                }
            }
        }
    }
}
