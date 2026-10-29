// Synthetic Screen-1-shaped review fixture for #1303 RED baseline.
// Not production QML. No private sample paths.
import QtQuick
import QtQuick.Controls

Item {
    id: root
    property var interaction
    property var screenData
    width: 640
    height: 400

    ListView {
        id: browser
        anchors.fill: parent
        model: root.screenData.browserRows
        clip: true
        reuseItems: true

        delegate: Rectangle {
            id: browserRow
            width: browser.width
            height: 36
            // Defect: cache transient visual index as if it were sample identity.
            property int cachedSampleIndex: index
            color: index === root.screenData.selectedBrowserIndex
                   ? "#334" : "transparent"

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    // Looks idiomatic; index is resolved immediately — acceptable.
                    root.interaction.selectRow(index)
                }
                onPressAndHold: {
                    // Defect: delayed path uses cached visual index after possible
                    // reuse/filter. Python may resolve the wrong sample.
                    favoriteDelay.restart()
                }
            }

            Timer {
                id: favoriteDelay
                interval: 250
                repeat: false
                onTriggered: root.interaction.toggleFavorite(browserRow.cachedSampleIndex)
            }

            ListView.onPooled: {
                // Hover cleanup only — cachedSampleIndex is left intact (defect).
            }
        }
    }
}
