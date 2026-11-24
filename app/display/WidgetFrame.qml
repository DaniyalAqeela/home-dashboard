// One widget: positioned in % of the stage, with the common style (background,
// radius, padding, font, colour, alignment, shadow). The type-specific content is
// loaded from widgets/<Type>.qml and reads everything through `frame`.
import QtQuick

Item {
    id: frame
    property var app
    property var w: null
    property var wdata: ({})

    readonly property var s: w ? w.style : ({})
    readonly property var o: w ? w.options : ({})
    readonly property string family: app.fam(s.font)
    readonly property color textColor: app.col(s.color, app.col(app.cfg ? app.cfg.theme.color : "", "white"))
    readonly property real fs: (s.fontSize || 32) * app.ui
    readonly property int halign: s.align === "center" ? Text.AlignHCenter : s.align === "right" ? Text.AlignRight : Text.AlignLeft
    readonly property int textStyle: s.shadow ? Text.Raised : Text.Normal
    readonly property color shadowColor: "#B0000000"

    visible: !!w
    x: w ? parent.width * w.x / 100 : 0
    y: w ? parent.height * w.y / 100 : 0
    width: w ? parent.width * w.w / 100 : 0
    height: w ? parent.height * w.h / 100 : 0
    z: w ? w.z : 0

    Rectangle {
        anchors.fill: parent
        color: frame.app.col(frame.s.background, "transparent")
        radius: (frame.s.radius || 0) * frame.app.ui
    }

    Loader {
        id: body
        anchors.fill: parent
        anchors.margins: (frame.s.padding || 0) * frame.app.ui
        clip: true
        Component.onCompleted: {
            var t = frame.w ? frame.w.type : ""
            if (t)
                setSource("widgets/" + t.charAt(0).toUpperCase() + t.slice(1) + ".qml", { "frame": frame })
        }
    }
}
