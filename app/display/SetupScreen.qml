// Shown until a settings-site password has been set.
import QtQuick

Rectangle {
    id: root
    property var app
    color: "#0E1621"

    Column {
        anchors.centerIn: parent
        width: parent.width * 0.8
        spacing: 28 * root.app.ui

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "Welcome to your dashboard"
            color: "white"
            font.family: "Inter"
            font.bold: true
            font.pixelSize: 72 * root.app.ui
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "To set it up, open this address in a browser on a phone or computer on the same network:"
            color: "#CCFFFFFF"
            font.family: "Inter"
            font.pixelSize: 34 * root.app.ui
            wrapMode: Text.WordWrap
        }
        Repeater {
            model: root.app.st ? root.app.st.setup.urls : []
            delegate: Text {
                required property string modelData
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: modelData
                color: "#7CC4FF"
                font.family: "Inter"
                font.bold: true
                font.pixelSize: 56 * root.app.ui
            }
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            visible: root.app.st && root.app.st.setup.urls.length <= 1
            text: "No address yet? Plug in an Ethernet cable and wait a few seconds."
            color: "#99FFFFFF"
            font.family: "Inter"
            font.pixelSize: 28 * root.app.ui
            wrapMode: Text.WordWrap
        }
    }
}
