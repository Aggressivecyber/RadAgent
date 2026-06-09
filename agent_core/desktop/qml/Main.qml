import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1366
    height: 820
    visible: true
    title: "RadAgent Workbench"
    color: "#111318"

    Shortcut {
        sequence: "Ctrl+L"
        onActivated: composer.forceActiveFocus()
    }

    Shortcut {
        sequence: "Ctrl+R"
        onActivated: runButton.clicked()
    }

    Connections {
        target: radAgent
        function onErrorOccurred(message) {
            errorBanner.text = message
            errorBanner.visible = true
        }
        function onArtifactOpened(content) {
            artifactPreview.content = content
            artifactPreview.open()
        }
    }

    Dialog {
        id: artifactPreview
        property var content: ({})
        modal: true
        width: Math.min(root.width * 0.72, 980)
        height: Math.min(root.height * 0.72, 620)
        anchors.centerIn: parent
        title: content.path || "Artifact"
        standardButtons: Dialog.Close

        ScrollView {
            anchors.fill: parent
            TextArea {
                readOnly: true
                wrapMode: TextEdit.NoWrap
                text: artifactPreview.content.kind === "binary"
                    ? "Binary artifact: " + artifactPreview.content.path
                    : artifactPreview.content.text || ""
                color: "#d9dde7"
                selectionColor: "#3d6fd8"
                selectedTextColor: "white"
                background: Rectangle { color: "#151922"; radius: 6 }
                font.family: "monospace"
                font.pixelSize: 12
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            color: "#161a22"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                Label {
                    text: "RadAgent"
                    color: "#f3f5f8"
                    font.pixelSize: 18
                    font.bold: true
                }

                Label {
                    text: "desktop workbench"
                    color: "#8c96a8"
                    font.pixelSize: 12
                }

                Item { Layout.fillWidth: true }

                BusyIndicator {
                    running: radAgent.busy
                    visible: running
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                }

                Label {
                    text: {
                        const s = radAgent.status
                        if (!s || !s.job_id) return "No active job"
                        return s.job_id + "  ·  " + (s.current_phase || "complete")
                    }
                    color: "#aab3c3"
                    elide: Text.ElideMiddle
                    maximumLineCount: 1
                    Layout.maximumWidth: 520
                }
            }
        }

        Rectangle {
            id: errorBanner
            property alias text: errorText.text
            visible: false
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 34 : 0
            color: "#3b1f24"
            clip: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                Label {
                    id: errorText
                    color: "#ffd7dc"
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Button {
                    text: "Dismiss"
                    flat: true
                    onClicked: errorBanner.visible = false
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            Rectangle {
                SplitView.preferredWidth: 270
                SplitView.minimumWidth: 220
                color: "#12161d"
                border.color: "#242a35"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 10

                    Label {
                        text: "Jobs"
                        color: "#e8ebf2"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Button {
                        text: "Refresh"
                        Layout.fillWidth: true
                        onClicked: radAgent.refreshJobs()
                    }

                    ListView {
                        id: jobList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 6
                        model: radAgent.jobs

                        delegate: Rectangle {
                            width: jobList.width
                            height: 78
                            radius: 6
                            color: modelData.job_id === radAgent.status.job_id ? "#1f2b3d" : "#181d26"
                            border.color: "#2b3444"

                            Column {
                                anchors.fill: parent
                                anchors.margins: 9
                                spacing: 5

                                Text {
                                    text: modelData.job_id || "job"
                                    color: "#dfe5ee"
                                    font.pixelSize: 12
                                    elide: Text.ElideMiddle
                                    width: parent.width
                                }
                                Text {
                                    text: modelData.status + " · " + (modelData.current_phase || "idle")
                                    color: "#8c96a8"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                                Text {
                                    text: modelData.user_query || ""
                                    color: "#687386"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: radAgent.resumeJob(modelData.job_id)
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 520
                color: "#0f1218"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: "Timeline"
                            color: "#e8ebf2"
                            font.pixelSize: 15
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            id: stepButton
                            text: "Step"
                            enabled: !radAgent.busy && radAgent.status.job_id
                            onClicked: radAgent.stepJob()
                        }
                        Button {
                            text: "Continue"
                            enabled: !radAgent.busy && radAgent.status.job_id
                            onClicked: radAgent.continueJob()
                        }
                    }

                    ListView {
                        id: timeline
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 8
                        model: radAgent.events
                        verticalLayoutDirection: ListView.TopToBottom

                        delegate: Rectangle {
                            width: timeline.width
                            implicitHeight: Math.max(58, eventText.implicitHeight + 30)
                            radius: 7
                            color: {
                                if (modelData.status === "error") return "#2b171c"
                                if (modelData.status === "warning") return "#292414"
                                if (modelData.event_type === "user_message" || modelData.event_type === "user_request") return "#172235"
                                return "#171b23"
                            }
                            border.color: "#293140"

                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 5

                                Row {
                                    spacing: 8
                                    Text {
                                        text: modelData.event_type || "event"
                                        color: "#dfe5ee"
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                    Text {
                                        text: modelData.phase ? "· " + modelData.phase : ""
                                        color: "#7c879a"
                                        font.pixelSize: 12
                                    }
                                    Text {
                                        text: modelData.status || ""
                                        color: {
                                            if (modelData.status === "error") return "#ff8f9a"
                                            if (modelData.status === "warning") return "#f0c36a"
                                            if (modelData.status === "success") return "#82d49b"
                                            return "#7c879a"
                                        }
                                        font.pixelSize: 12
                                    }
                                }

                                Text {
                                    id: eventText
                                    text: modelData.summary || ""
                                    color: "#aeb7c7"
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
                                    width: parent.width
                                    maximumLineCount: 6
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        onCountChanged: Qt.callLater(function() {
                            timeline.positionViewAtEnd()
                        })
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 92
                        radius: 8
                        color: "#171b23"
                        border.color: "#2c3545"

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 10

                            TextArea {
                                id: composer
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                placeholderText: "Ask a question or describe a simulation job..."
                                wrapMode: TextEdit.Wrap
                                color: "#eef2f8"
                                placeholderTextColor: "#697386"
                                background: Rectangle { color: "#10141b"; radius: 6 }
                            }

                            ColumnLayout {
                                Layout.preferredWidth: 116
                                Button {
                                    text: "Chat"
                                    Layout.fillWidth: true
                                    enabled: !radAgent.busy
                                    onClicked: {
                                        radAgent.sendMessage(composer.text)
                                        composer.clear()
                                    }
                                }
                                Button {
                                    id: runButton
                                    text: "New Job"
                                    Layout.fillWidth: true
                                    enabled: !radAgent.busy
                                    onClicked: {
                                        radAgent.startJob(composer.text)
                                        composer.clear()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                SplitView.preferredWidth: 360
                SplitView.minimumWidth: 300
                color: "#12161d"
                border.color: "#242a35"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12

                    Label {
                        text: "Inspector"
                        color: "#e8ebf2"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 164
                        radius: 7
                        color: "#181d26"
                        border.color: "#2b3444"

                        Column {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 7

                            Text {
                                text: "Status"
                                color: "#dfe5ee"
                                font.bold: true
                            }
                            Text {
                                text: "Job: " + (radAgent.status.job_id || "none")
                                color: "#98a4b7"
                                width: parent.width
                                elide: Text.ElideMiddle
                            }
                            Text {
                                text: "Phase: " + (radAgent.status.current_phase || "idle")
                                color: "#98a4b7"
                            }
                            Text {
                                text: "Mode: " + (radAgent.status.run_mode || "strict")
                                color: "#98a4b7"
                            }
                            Text {
                                text: radAgent.status.needs_confirmation ? "Needs confirmation" : "No confirmation pending"
                                color: radAgent.status.needs_confirmation ? "#f0c36a" : "#82d49b"
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            text: "Build"
                            Layout.fillWidth: true
                            enabled: !radAgent.busy && radAgent.status.job_id
                            onClicked: radAgent.runBuild()
                        }
                        Button {
                            text: "Sim"
                            Layout.fillWidth: true
                            enabled: !radAgent.busy && radAgent.status.job_id
                            onClicked: radAgent.runSimulation(1000)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: "Artifacts"
                            color: "#e8ebf2"
                            font.pixelSize: 14
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: "Refresh"
                            onClicked: radAgent.refreshArtifacts()
                        }
                    }

                    ListView {
                        id: artifactList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 6
                        model: radAgent.artifacts

                        delegate: Rectangle {
                            width: artifactList.width
                            height: 62
                            radius: 6
                            color: "#181d26"
                            border.color: "#2b3444"

                            Column {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4
                                Text {
                                    text: modelData.kind || modelData.stage || "artifact"
                                    color: "#dfe5ee"
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                                Text {
                                    text: modelData.path || ""
                                    color: "#7d889b"
                                    font.pixelSize: 11
                                    elide: Text.ElideMiddle
                                    width: parent.width
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                onClicked: radAgent.openArtifact(modelData.path)
                            }
                        }
                    }
                }
            }
        }
    }
}
