import QtQuick

Item {
    id: root
    property var frame
    readonly property var o: frame.o
    readonly property var hijri: frame.wdata ? frame.wdata.hijri : null
    property date now: new Date()

    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = new Date() }

    function arabicDigits(n) {
        return String(n).replace(/[0-9]/g, function (d) { return String.fromCharCode(0x0660 + Number(d)) })
    }
    readonly property string hijriText: {
        if (!hijri) return ""
        if (o.hijriScript === "arabic")
            return arabicDigits(hijri.day) + " " + hijri.monthNameAr + " " + arabicDigits(hijri.year) + " هـ"
        return hijri.day + " " + hijri.monthName + " " + hijri.year + " AH"
    }

    Column {
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        spacing: root.frame.fs * 0.1

        Text {
            width: parent.width
            text: Qt.formatTime(root.now, root.o.hour24 ? (root.o.seconds ? "HH:mm:ss" : "HH:mm")
                                                        : (root.o.seconds ? "h:mm:ss AP" : "h:mm AP"))
            color: root.frame.textColor
            style: root.frame.textStyle
            styleColor: root.frame.shadowColor
            font.family: root.frame.family
            font.bold: true
            font.pixelSize: root.frame.fs
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 10
            horizontalAlignment: root.frame.halign
        }
        Text {
            width: parent.width
            visible: root.o.showDate
            text: Qt.formatDate(root.now, root.o.dateFormat)
            color: root.frame.textColor
            style: root.frame.textStyle
            styleColor: root.frame.shadowColor
            font.family: root.frame.family
            font.pixelSize: root.frame.fs * 0.3
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 8
            horizontalAlignment: root.frame.halign
        }
        Text {
            width: parent.width
            visible: root.o.hijri && root.hijriText !== ""
            text: root.hijriText
            textFormat: Text.PlainText
            color: root.frame.textColor
            opacity: 0.85
            style: root.frame.textStyle
            styleColor: root.frame.shadowColor
            font.family: root.o.hijriScript === "arabic" ? "Noto Naskh Arabic" : root.frame.family
            font.pixelSize: root.frame.fs * 0.27
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 8
            horizontalAlignment: root.frame.halign
        }
    }
}
