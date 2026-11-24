// Two images crossfading. The server picks the photo; we only fade to it once it
// has fully loaded, so a slow decode never shows a blank frame.
import QtQuick

Item {
    id: root
    property var frame
    readonly property var o: frame.o
    readonly property string photo: frame.wdata && frame.wdata.photo ? frame.app.baseUrl + frame.wdata.photo : ""
    readonly property int fill: o.fit === "contain" ? Image.PreserveAspectFit : Image.PreserveAspectCrop
    property Image front: imgA
    property Image back: imgB

    Rectangle {
        anchors.fill: parent
        visible: root.o.fit === "contain"
        color: root.frame.app.col(root.o.fill, "black")
    }

    Image {
        id: imgA
        anchors.fill: parent
        asynchronous: true
        cache: false
        fillMode: root.fill
        sourceSize: Qt.size(Math.max(1, width), Math.max(1, height))
        onStatusChanged: root.maybeShow(imgA)
    }
    Image {
        id: imgB
        anchors.fill: parent
        asynchronous: true
        cache: false
        opacity: 0
        fillMode: root.fill
        sourceSize: Qt.size(Math.max(1, width), Math.max(1, height))
        onStatusChanged: root.maybeShow(imgB)
    }

    onPhotoChanged: load()
    Component.onCompleted: load()

    function load() {
        if (!photo) return
        if (front.source.toString() === photo && front.status === Image.Ready) return
        back.source = photo
    }
    function maybeShow(img) {
        if (img !== back || img.status !== Image.Ready || img.source.toString() !== photo) return
        fadeIn.target = back
        fadeOut.target = front
        fade.restart()
    }

    ParallelAnimation {
        id: fade
        NumberAnimation { id: fadeIn; property: "opacity"; to: 1; duration: Math.max(1, root.o.fade * 1000) }
        NumberAnimation { id: fadeOut; property: "opacity"; to: 0; duration: Math.max(1, root.o.fade * 1000) }
        onFinished: {
            var old = root.front
            root.front = root.back
            root.back = old
            old.source = ""        // free the texture
        }
    }

    Text {
        anchors.centerIn: parent
        width: parent.width * 0.8
        visible: !root.photo && !!root.frame.wdata.error
        text: root.frame.wdata.error || ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        color: "#99FFFFFF"
        font.family: root.frame.family
        font.pixelSize: 30 * root.frame.app.ui
    }
}
