import QtQuick

Item {
    id: root
    property var frame
    readonly property var o: frame.o
    readonly property var d: frame.wdata || ({})
    readonly property var times: d.times || []
    readonly property var next: d.next || null
    property real nowMs: Date.now()
    readonly property real countH: o.countdown && next ? frame.fs * 1.4 : 0
    readonly property real rowH: times.length ? Math.min(frame.fs * 1.55, (height - countH) / times.length) : 0
    readonly property real rowFs: Math.min(frame.fs, rowH / 1.45, width / 9)  // bold "Maghrib  19:03" must fit

    Timer { interval: 1000; running: root.o.countdown; repeat: true; onTriggered: root.nowMs = Date.now() }

    function countdown() {
        if (!next) return ""
        var m = Math.max(0, Math.ceil((next.ts - nowMs) / 60000))
        var h = Math.floor(m / 60)
        return next.name + " in " + (h > 0 ? h + "h " + (m % 60 < 10 ? "0" : "") + (m % 60) + "m" : m + " min")
    }

    Text {
        anchors.centerIn: parent
        width: parent.width
        visible: root.times.length === 0
        text: root.d.error || ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        color: root.frame.textColor
        opacity: 0.6
        font.family: root.frame.family
        font.pixelSize: root.frame.fs * 0.6
    }

    Column {
        width: parent.width
        anchors.verticalCenter: parent.verticalCenter
        Repeater {
            model: root.times
            delegate: Item {
                required property var modelData
                readonly property bool isNext: root.o.highlightNext && root.next && root.next.key === modelData.key
                width: parent.width
                height: root.rowH
                Rectangle {
                    anchors.fill: parent
                    visible: parent.isNext
                    radius: height * 0.25
                    color: "#33FFFFFF"
                }
                Text {
                    anchors { left: parent.left; leftMargin: root.rowFs * 0.4; verticalCenter: parent.verticalCenter }
                    text: modelData.name
                    color: root.frame.textColor
                    style: root.frame.textStyle
                    styleColor: root.frame.shadowColor
                    font.family: root.frame.family
                    font.bold: parent.isNext
                    font.pixelSize: root.rowFs
                }
                Text {
                    anchors { right: parent.right; rightMargin: root.rowFs * 0.4; verticalCenter: parent.verticalCenter }
                    text: root.o.hour24 ? modelData.time24 : modelData.time12
                    color: root.frame.textColor
                    style: root.frame.textStyle
                    styleColor: root.frame.shadowColor
                    font.family: root.frame.family
                    font.bold: parent.isNext
                    font.pixelSize: root.rowFs
                }
            }
        }
        Text {
            width: parent.width
            height: root.countH
            visible: root.countH > 0
            verticalAlignment: Text.AlignBottom
            horizontalAlignment: Text.AlignHCenter
            text: root.countdown()
            color: root.frame.textColor
            opacity: 0.85
            font.family: root.frame.family
            font.pixelSize: root.frame.fs * 0.65
        }
    }
}
