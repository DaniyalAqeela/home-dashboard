import QtQuick

Item {
    id: root
    property var frame
    readonly property var o: frame.o
    readonly property var d: frame.wdata || ({})
    readonly property var cur: d.current || null
    readonly property var days: d.daily ? d.daily.slice(0, o.days) : []
    readonly property real fs: frame.fs

    function temp(c) { return Math.round(o.units === "f" ? c * 9 / 5 + 32 : c) + "°" }
    function alignX(w) {
        return frame.halign === Text.AlignHCenter ? (width - w) / 2 : frame.halign === Text.AlignRight ? width - w : 0
    }

    Text {
        anchors.centerIn: parent
        width: parent.width
        visible: !root.cur
        text: root.d.error || "Loading weather…"
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        color: root.frame.textColor
        opacity: 0.6
        font.family: root.frame.family
        font.pixelSize: root.fs * 0.6
    }

    Row {
        id: now
        visible: !!root.cur
        x: root.alignX(width)
        spacing: root.fs * 0.35
        Image {
            width: root.fs * 2.2
            height: width
            sourceSize: Qt.size(width, height)
            source: root.cur ? "../icons/" + root.cur.icon + ".svg" : ""
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            Text {
                text: root.cur ? root.temp(root.cur.temp) : ""
                color: root.frame.textColor
                style: root.frame.textStyle
                styleColor: root.frame.shadowColor
                font.family: root.frame.family
                font.bold: true
                font.pixelSize: root.fs * 1.5
            }
            Text {
                text: root.cur ? root.cur.label + (root.d.place ? " · " + root.d.place : "") : ""
                textFormat: Text.PlainText
                color: root.frame.textColor
                opacity: 0.85
                style: root.frame.textStyle
                styleColor: root.frame.shadowColor
                font.family: root.frame.family
                font.pixelSize: root.fs * 0.5
            }
            Text {
                visible: root.o.showDetails && !!root.cur
                text: root.cur ? "Humidity " + root.cur.humidity + "%  ·  Wind "
                                 + (root.o.units === "f" ? Math.round(root.cur.wind * 0.621) + " mph"
                                                         : Math.round(root.cur.wind) + " km/h") : ""
                color: root.frame.textColor
                opacity: 0.7
                font.family: root.frame.family
                font.pixelSize: root.fs * 0.42
            }
        }
    }

    Row {
        visible: !!root.cur && root.days.length > 0
        anchors.bottom: parent.bottom
        x: root.alignX(width)
        spacing: root.fs * 0.6
        Repeater {
            model: root.days
            delegate: Column {
                required property var modelData
                required property int index
                spacing: 2
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: index === 0 ? "Today" : Qt.formatDate(new Date(modelData.date + "T12:00:00"), "ddd")
                    color: root.frame.textColor
                    opacity: 0.8
                    font.family: root.frame.family
                    font.pixelSize: root.fs * 0.48
                }
                Image {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: root.fs * 1.1
                    height: width
                    sourceSize: Qt.size(width, height)
                    source: "../icons/" + modelData.icon + ".svg"
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.temp(modelData.max) + " " + root.temp(modelData.min)
                    color: root.frame.textColor
                    font.family: root.frame.family
                    font.pixelSize: root.fs * 0.48
                }
            }
        }
    }
}
