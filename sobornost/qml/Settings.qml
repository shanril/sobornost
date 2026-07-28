import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    title: "sobornost - Settings"
    width: 500
    height: 420
    minimumWidth: 500
    minimumHeight: 420
    maximumWidth: 500
    maximumHeight: 420
    visible: true

    signal saved()
    signal canceled()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        TabBar {
            id: tabBar
            Layout.fillWidth: true

            TabButton { text: "General" }
            TabButton { text: "Display" }
            TabButton { text: "Stats" }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // ---- General tab ----
            ScrollView {
                contentWidth: availableWidth
                clip: true

                GridLayout {
                    width: parent.width
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 6

                    anchors.margins: 12

                    Label { text: "Thumbnail Width:" }
                    SpinBox {
                        from: 100; to: 640; stepSize: 10; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.thumbnailWidth
                        onValueModified: bridge.thumbnailWidth = value
                    }

                    Label { text: "Thumbnail Height:" }
                    SpinBox {
                        from: 80; to: 400; stepSize: 10; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.thumbnailHeight
                        onValueModified: bridge.thumbnailHeight = value
                    }

                    Label { text: "Opacity:" }
                    RowLayout {
                        Slider {
                            from: 0.2; to: 1.0; stepSize: 0.05
                            Layout.preferredWidth: 150
                            value: bridge.thumbnailOpacity
                            onMoved: bridge.thumbnailOpacity = value
                        }
                        Label {
                            text: (bridge.thumbnailOpacity).toFixed(2)
                            Layout.preferredWidth: 40
                        }
                    }

                    Label { text: "Refresh Rate (ms):" }
                    SpinBox {
                        from: 50; to: 1000; stepSize: 50; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.previewRefreshMs
                        onValueModified: bridge.previewRefreshMs = value
                    }

                    CheckBox {
                        text: "Track Client Locations"
                        Layout.columnSpan: 2
                        checked: bridge.trackClientLocations
                        onToggled: bridge.trackClientLocations = checked
                    }

                    // --- Hotkey section ---
                    Rectangle {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: palette.mid
                    }

                    Label {
                        text: "Switch Client:  " + bridge.hotkeyDescription
                        font.bold: true
                        Layout.columnSpan: 2
                    }

                    // Modifier checkboxes
                    Repeater {
                        model: bridge.modLabels
                        CheckBox {
                            required property string name
                            required property string label
                            text: label
                            checked: name === "Control" ? bridge.ctrlMod
                                   : name === "Shift" ? bridge.shiftMod
                                   : name === "Option" ? bridge.optMod
                                   : name === "Command" ? bridge.cmdMod
                                   : false
                            onToggled: {
                                if (name === "Control") bridge.ctrlMod = checked
                                else if (name === "Shift") bridge.shiftMod = checked
                                else if (name === "Option") bridge.optMod = checked
                                else if (name === "Command") bridge.cmdMod = checked
                            }
                        }
                    }

                    Label { text: "Key:" }
                    ComboBox {
                        id: keyCombo
                        Layout.preferredWidth: 180
                        model: bridge.keyModel
                        textRole: "display"
                        valueRole: "value"
                        currentIndex: bridge.hotkeyKey ? (function() {
                            for (let i = 0; i < model.length; i++) {
                                if (model[i].value === bridge.hotkeyKey) return i
                            }
                            return 0
                        })() : 0
                        onActivated: {
                            bridge.hotkeyKey = currentValue
                        }
                    }
                }
            }

            // ---- Display tab ----
            ScrollView {
                contentWidth: availableWidth
                clip: true

                GridLayout {
                    width: parent.width
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 6
                    anchors.margins: 12

                    Label { text: "Highlight Color:" }
                    TextField {
                        Layout.preferredWidth: 140
                        text: bridge.highlightColor
                        onTextEdited: bridge.highlightColor = text
                    }

                    CheckBox {
                        text: "Show Label Overlay"
                        Layout.columnSpan: 2
                        checked: bridge.labelOverlay
                        onToggled: bridge.labelOverlay = checked
                    }

                    Label { text: "Label Font Size:" }
                    SpinBox {
                        from: 6; to: 48; stepSize: 1; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.labelFontSize
                        onValueModified: bridge.labelFontSize = value
                    }
                }
            }

            // ---- Stats tab ----
            ScrollView {
                contentWidth: availableWidth
                clip: true

                GridLayout {
                    width: parent.width
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 6
                    anchors.margins: 12

                    CheckBox {
                        text: "Enable Stats Overlay"
                        Layout.columnSpan: 2
                        checked: bridge.statsEnabled
                        onToggled: bridge.statsEnabled = checked
                    }

                    Label { text: "Endpoint URL:" }
                    TextField {
                        Layout.fillWidth: true
                        text: bridge.statsEndpoint
                        onTextEdited: bridge.statsEndpoint = text
                    }

                    Label { text: "Update Interval (ms):" }
                    SpinBox {
                        from: 1000; to: 60000; stepSize: 1000; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.statsRefreshMs
                        onValueModified: bridge.statsRefreshMs = value
                    }

                    Label { text: "DPS Window (s):" }
                    SpinBox {
                        from: 5; to: 600; stepSize: 5; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.statsDpsWindowSecs
                        onValueModified: bridge.statsDpsWindowSecs = value
                    }

                    Label { text: "Mining Window (s):" }
                    SpinBox {
                        from: 30; to: 3600; stepSize: 30; editable: true
                        Layout.preferredWidth: 140
                        value: bridge.statsMiningWindowSecs
                        onValueModified: bridge.statsMiningWindowSecs = value
                    }
                }
            }
        }

        // --- Buttons ---
        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignRight

            Button {
                text: "Cancel"
                onClicked: {
                    win.canceled()
                    win.close()
                }
            }
            Button {
                text: "Save"
                onClicked: {
                    bridge.save()
                    win.saved()
                    win.close()
                }
                highlighted: true
            }
        }
    }
}