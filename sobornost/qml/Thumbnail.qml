import QtQuick
import Sobornost 1.0

Item {
    id: root
    width: bridge.thumbnailWidth + (bridge.active ? 2 * bridge.highlightThickness : 0)
    height: bridge.thumbnailHeight + (bridge.active ? 2 * bridge.highlightThickness : 0)

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: bridge.active ? bridge.highlightColor : "transparent"
        border.width: bridge.active ? bridge.highlightThickness : 0
    }

    ThumbnailPaintItem {
        id: paintItem
        objectName: "paintItem"
        anchors.fill: parent
        anchors.margins: bridge.active ? bridge.highlightThickness : 0
    }

    Text {
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: bridge.active ? bridge.highlightThickness : 0
        text: bridge.characterName
        visible: bridge.labelOverlay
        font.pixelSize: bridge.labelFontSize
        color: "white"
        style: Text.Outline
        styleColor: "#A0000000"
    }

    Item {
        id: dragDummy
        visible: false
    }

    MouseArea {
        anchors.fill: parent
        drag.target: dragDummy
        drag.threshold: 3

        onPressed: function(mouse) {
            var g = mapToGlobal(Qt.point(mouse.x, mouse.y))
            bridge.dragStarted(g.x, g.y)
        }
        onPositionChanged: function(mouse) {
            if (pressed) {
                var g = mapToGlobal(Qt.point(mouse.x, mouse.y))
                bridge.dragMoved(g.x, g.y)
            }
        }
        onReleased: bridge.dragEnded()
        onClicked: function(mouse) {
            if (mouse.modifiers & Qt.ControlModifier)
                bridge.ctrlClicked()
            else
                bridge.clicked()
        }
    }
}
