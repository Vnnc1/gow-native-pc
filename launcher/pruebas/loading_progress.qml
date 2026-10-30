import QtQuick
import "ui" as Ui

// Run against copies of the production QML through tools/test/loading-progress.py (no pipeline or game).
Item {
    width: 1280
    height: 720
    QtObject {
        id: installer
        property bool running: false
        property string stages: ""
        signal stepChanged(string step)
        signal progress(int done, int total)
        signal statusText(string text)
        signal logLine(string text)
        signal finished(bool ok, int code)
        function loadingArt() { return [] }
        function cancel() {}
    }
    QtObject { id: lanzador; function urlDesdeRuta(path) { return path } }
    Ui.LoadingScreen { id: screen; anchors.fill: parent }
    property real previous: 0
    property bool watching: false
    property bool regressed: false

    function require(ok, message) { if (!ok) throw new Error(message) }
    function near(actual, expected, message) { require(Math.abs(actual - expected) < 0.000001, message + ": " + actual) }
    function start(stages) {
        watching = false
        installer.running = false
        installer.stages = stages
        installer.running = true
        near(screen.fraccion, 0, "New operation starts at zero")
        previous = 0
        watching = true
    }
    function finish(ok) {
        installer.running = false
        installer.finished(ok, ok ? 0 : 1)
    }
    Component.onCompleted: {
        try {
            screen.fraccionChanged.connect(function() {
                if (watching && screen.fraccion < previous) regressed = true
                previous = screen.fraccion
            })
            start("tools,fetch,discs,configure,recomp,sync,build,optimize")
            var steps = ["build tools", "runtime", "discs", "configure", "recompile the executable", "generated code", "build the game"]
            for (var i = 0; i < steps.length; ++i) {
                installer.stepChanged(steps[i])
                if (i < steps.length - 1) installer.progress(1, 1)
            }
            near(screen.fraccion, 11 / 29.5, "Build starts at its weighted boundary")
            installer.progress(1, 558)
            near(screen.fraccion, (11 + 12 / 558) / 29.5, "Real first object stays near 37%, not 78%")
            installer.progress(400, 558)
            var reached = screen.fraccion
            installer.progress(400, 1000)
            near(screen.fraccion, reached, "Revised total cannot rewind the bar")
            require(screen.total === 1000, "ETA retains the actual revised counter")
            installer.progress(-1, 10)
            installer.progress(10, 0)
            installer.progress(11, 10)
            near(screen.fraccion, reached, "Malformed counters cannot advance/reset progress")
            installer.stepChanged("build the game")
            near(screen.fraccion, reached, "Repeated step does not reset")
            installer.stepChanged("record: the game plays itself")
            installer.progress(1, 240)
            installer.progress(240, 240)
            installer.stepChanged("native VU1 and IOP code")
            installer.stepChanged("rebuild (Release)")
            installer.progress(1, 10)
            installer.progress(10, 10)
            near(screen.fraccion, 0.99, "Last counter is not a successful process exit")
            finish(false)
            near(screen.fraccion, 0.99, "Failure retains progress without claiming completion")

            start("build")
            installer.stepChanged("build the game")
            installer.progress(1, 1) // no-op builds also emit completion
            near(screen.fraccion, 0.99, "No-op waits for success")
            finish(true)
            near(screen.fraccion, 1, "Success reaches 100%")

            start("pgo,optimize,native")
            require(screen.plan.length === 6, "Optimize and native share their last two steps")
            var pgo = ["profile-guided optimisation: instrumented build", "profile-guided optimisation: the game plays itself",
                       "rebuild with the profile", "record", "native VU1 and IOP code", "rebuild"]
            for (var j = 0; j < pgo.length; ++j) {
                installer.stepChanged(pgo[j])
                installer.progress(1, 100)
                installer.progress(100, 100)
            }
            finish(true)
            near(screen.fraccion, 1, "PGO and optimization complete monotonically")
            require(!regressed, "Overall progress moved backwards during an intermediate property update")
            console.log("PASS: actual LoadingScreen transitions, revised counters, failure, retry, no-op, PGO and success")
            Qt.exit(0)
        } catch (e) {
            console.error(e.stack || e)
            Qt.exit(1)
        }
    }
}
