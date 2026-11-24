// Headlines. Feed text is untrusted, so every Text is PlainText.
import QtQuick

Item {
    id: root
    property var frame
    readonly property var o: frame.o
    readonly property var d: frame.wdata || ({})
    readonly property var items: d.items || []
    readonly property real fs: frame.fs

    // line heights, used to fit the rotate layout into whatever box it has
    readonly property real h1: fs * 1.25
    readonly property real h2: fs * 0.62 * 1.3
    readonly property real h3: o.showSource ? fs * 0.45 * 1.4 : 0

    Text {
        anchors.centerIn: parent
        visible: root.items.length === 0
        text: root.d.error || "Loading news…"
        textFormat: Text.PlainText
        color: root.frame.textColor
        opacity: 0.6
        font.family: root.frame.family
        font.pixelSize: root.fs * 0.6
    }

    // --- one headline at a time ------------------------------------------------
    Item {
        id: rotate
        anchors.fill: parent
        visible: root.o.layout === "rotate" && root.items.length > 0
        readonly property int wanted: root.items.length ? (root.d.index || 0) % root.items.length : 0
        property int shown: 0
        readonly property var cur: root.items.length ? root.items[Math.min(shown, root.items.length - 1)] : ({})
        readonly property int titleLines: height >= root.h1 * 2 + root.h2 + root.h3 ? 2 : 1
        readonly property int descLines: Math.max(0, Math.floor((height - titleLines * root.h1 - root.h3) / root.h2))

        onWantedChanged: swap.restart()
        SequentialAnimation {
            id: swap
            NumberAnimation { target: rotCol; property: "opacity"; to: 0; duration: 350 }
            ScriptAction { script: rotate.shown = rotate.wanted }
            NumberAnimation { target: rotCol; property: "opacity"; to: 1; duration: 350 }
        }

        Column {
            id: rotCol
            width: parent.width
            anchors.verticalCenter: parent.verticalCenter
            Text {
                width: parent.width
                text: rotate.cur.title || ""
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                maximumLineCount: rotate.titleLines
                elide: Text.ElideRight
                color: root.frame.textColor
                style: root.frame.textStyle
                styleColor: root.frame.shadowColor
                font.family: root.frame.family
                font.bold: true
                font.pixelSize: root.fs
                horizontalAlignment: root.frame.halign
            }
            Text {
                width: parent.width
                visible: rotate.descLines > 0 && !!rotate.cur.summary
                text: rotate.cur.summary || ""
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                maximumLineCount: Math.max(1, rotate.descLines)
                elide: Text.ElideRight
                color: root.frame.textColor
                opacity: 0.85
                style: root.frame.textStyle
                styleColor: root.frame.shadowColor
                font.family: root.frame.family
                font.pixelSize: root.fs * 0.62
                horizontalAlignment: root.frame.halign
            }
            Text {
                width: parent.width
                visible: root.o.showSource
                text: rotate.cur.source || ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: root.frame.textColor
                opacity: 0.6
                font.family: root.frame.family
                font.pixelSize: root.fs * 0.45
                horizontalAlignment: root.frame.halign
            }
        }
    }

    // --- list --------------------------------------------------------------------
    Column {
        anchors.fill: parent
        visible: root.o.layout === "list" && root.items.length > 0
        spacing: root.fs * 0.4
        Repeater {
            model: root.items.slice(0, root.o.count)
            delegate: Column {
                required property var modelData
                width: parent.width
                Text {
                    width: parent.width
                    text: modelData.title
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: root.frame.textColor
                    style: root.frame.textStyle
                    styleColor: root.frame.shadowColor
                    font.family: root.frame.family
                    font.bold: true
                    font.pixelSize: root.fs
                    horizontalAlignment: root.frame.halign
                }
                Text {
                    width: parent.width
                    visible: !!modelData.summary
                    text: modelData.summary
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    color: root.frame.textColor
                    opacity: 0.8
                    font.family: root.frame.family
                    font.pixelSize: root.fs * 0.62
                    horizontalAlignment: root.frame.halign
                }
            }
        }
    }

    // --- ticker --------------------------------------------------------------------
    Item {
        id: tickerBox
        anchors.fill: parent
        visible: root.o.layout === "ticker" && root.items.length > 0
        Text {
            id: ticker
            anchors.verticalCenter: parent.verticalCenter
            text: root.items.map(function (i) { return (root.o.showSource ? i.source + ": " : "") + i.title }).join("     •     ")
            textFormat: Text.PlainText
            color: root.frame.textColor
            style: root.frame.textStyle
            styleColor: root.frame.shadowColor
            font.family: root.frame.family
            font.pixelSize: root.fs
            onTextChanged: scroll.restart()
        }
        NumberAnimation {
            id: scroll
            target: ticker
            property: "x"
            from: tickerBox.width
            to: -ticker.width
            duration: Math.max(1000, (tickerBox.width + ticker.width) / Math.max(1, root.o.tickerSpeed * root.frame.app.ui) * 1000)
            loops: Animation.Infinite
            running: tickerBox.visible
        }
    }
}
