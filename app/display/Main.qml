// The dashboard screen. Draws whatever the local server's /api/display/state says;
// all decisions (which photo, which headline, prayer times) are made server-side
// so this screen and the settings-site preview always agree.
import QtQuick
import QtQuick.Window

Window {
    id: win
    visible: true
    width: 1920
    height: 1080
    visibility: Qt.platform.pluginName === "eglfs" ? Window.FullScreen : Window.Windowed
    color: "black"
    title: "Dashboard"

    readonly property string baseUrl: {
        if (typeof dashboardUrl !== "undefined" && dashboardUrl)
            return dashboardUrl
        var a = Qt.application.arguments
        for (var i = a.length - 1; i >= 0; i--)
            if (/^https?:\/\//.test(a[i])) return a[i]
        return "http://127.0.0.1"
    }

    property var st: null          // last good display state
    property int rev: -1
    property bool online: false
    property int reqId: 0
    property var order: []         // widget ids sorted by z; reassigned only when it changes
    readonly property var cfg: st ? st.config : null
    readonly property real ui: Math.min(stage.width, stage.height) / 1080 * (cfg ? cfg.display.scale : 1)

    // config colours are CSS #RRGGBB[AA]; Qt wants #AARRGGBB
    function col(c, fallback) {
        if (!c) return fallback
        return c.length === 9 ? "#" + c.substr(7, 2) + c.substr(1, 6) : c
    }
    function fam(f) { return f || (cfg && cfg.theme.font) || "Inter" }
    function findWidget(id) {
        var ws = st ? st.config.widgets : []
        for (var i = 0; i < ws.length; i++)
            if (ws[i].id === id) return ws[i]
        return null
    }

    onStChanged: {
        var ws = st ? st.config.widgets.slice() : []
        ws.sort(function (a, b) { return a.z - b.z })
        var ids = ws.map(function (w) { return w.id })
        if (ids.join("|") !== order.join("|"))
            order = ids
    }

    function poll() {
        var my = ++reqId
        var xhr = new XMLHttpRequest()
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== XMLHttpRequest.DONE || my !== reqId) return
            watchdog.stop()
            if (xhr.status === 200) {
                try {
                    var s = JSON.parse(xhr.responseText)
                    st = s
                    rev = s.rev
                    online = true
                    Qt.callLater(poll)
                    return
                } catch (e) {
                    console.warn("bad state:", e)
                }
            }
            online = false
            retry.start()     // keep showing the last state
        }
        xhr.open("GET", baseUrl + "/api/display/state?since=" + rev)
        xhr.send()
        watchdog.restart()
    }
    Timer { id: retry; interval: 2000; onTriggered: win.poll() }
    Timer {
        id: watchdog
        interval: 25000      // the server answers within ~10 s; anything longer is a hung request
        onTriggered: { win.reqId++; win.online = false; retry.start() }
    }
    Component.onCompleted: poll()

    FontLoader { source: "fonts/Inter-Regular.ttf" }
    FontLoader { source: "fonts/Inter-Bold.ttf" }
    FontLoader { source: "fonts/RobotoSlab-Regular.ttf" }
    FontLoader { source: "fonts/RobotoSlab-Bold.ttf" }
    FontLoader { source: "fonts/NotoNaskhArabic-Regular.ttf" }
    FontLoader { source: "fonts/NotoNaskhArabic-Bold.ttf" }

    // The logical stage: screen dimensions swapped for 90/270, rotated about its centre.
    Item {
        id: stage
        readonly property int rot: win.cfg ? win.cfg.display.rotation : 0
        readonly property bool sideways: rot === 90 || rot === 270
        width: sideways ? win.height : win.width
        height: sideways ? win.width : win.height
        anchors.centerIn: parent
        rotation: rot

        Rectangle {
            anchors.fill: parent
            color: win.col(win.cfg ? win.cfg.theme.background : "", "black")
        }

        Item {
            id: content
            readonly property var pad: win.cfg ? win.cfg.display.padding : { "top": 0, "right": 0, "bottom": 0, "left": 0 }
            x: stage.width * pad.left / 100
            y: stage.height * pad.top / 100
            width: stage.width * (100 - pad.left - pad.right) / 100
            height: stage.height * (100 - pad.top - pad.bottom) / 100
            visible: !!win.st && !win.st.setup.needed

            Repeater {
                model: win.order
                delegate: WidgetFrame {
                    required property string modelData
                    app: win
                    w: { win.st; return win.findWidget(modelData) }
                    wdata: win.st && win.st.widgets[modelData] ? win.st.widgets[modelData] : ({})
                }
            }
        }

        SetupScreen {
            anchors.fill: parent
            visible: !!win.st && win.st.setup.needed
            app: win
        }

        Text {
            anchors.centerIn: parent
            visible: !win.st
            text: startTimer.slow ? "Waiting for the dashboard service…" : "Starting…"
            color: "#99FFFFFF"
            font.family: "Inter"
            font.pixelSize: 40 * win.ui
            Timer { id: startTimer; property bool slow: false; interval: 15000; running: true; onTriggered: slow = true }
        }

        Text {
            anchors { top: parent.top; right: parent.right; margins: 12 * win.ui }
            visible: !!win.st && !win.st.clockSynced
            text: "Clock not set yet — waiting for internet"
            color: "#B3FFFFFF"
            style: Text.Raised
            styleColor: "#80000000"
            font.family: "Inter"
            font.pixelSize: 18 * win.ui
        }
    }

    // While someone has the settings-site preview open, save a half-size screenshot every second.
    Timer {
        interval: 1000
        repeat: true
        triggeredOnStart: true
        running: !!(win.st && win.st.screenshot.wanted)
        onTriggered: {
            var path = win.st.screenshot.path
            stage.grabToImage(function (r) { r.saveToFile(path) }, Qt.size(stage.width / 2, stage.height / 2))
        }
    }
}
