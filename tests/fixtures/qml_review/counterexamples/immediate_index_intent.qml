// Valid pattern: resolve visual index immediately into Python intent.
// Must NOT be flagged as DELEGATE_IDENTITY_AS_AUTHORITY.
import QtQuick

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
            width: browser.width
            height: 36
            color: index === root.screenData.selectedBrowserIndex
                   ? "#334" : "transparent"

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    // Immediate handoff: Python owns sample identity resolution.
                    root.interaction.selectRow(index)
                }
            }

            ListView.onPooled: {
                // Presentation-only cleanup is fine.
            }
        }
    }
}
