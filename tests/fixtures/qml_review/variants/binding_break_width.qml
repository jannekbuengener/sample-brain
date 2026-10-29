// Variant: imperative assignment destroys declarative width binding.
import QtQuick

Item {
    id: root
    width: 400
    height: 200

    ListView {
        id: browser
        anchors.fill: parent
        model: 8
        reuseItems: true

        delegate: Rectangle {
            id: row
            // Binding starts correct...
            width: browser.width
            height: 32
            color: "#222"

            Component.onCompleted: {
                // Defect: imperative write replaces the binding. Later browser
                // width changes leave the row geometrically stale.
                width = browser.width
            }
        }
    }
}
