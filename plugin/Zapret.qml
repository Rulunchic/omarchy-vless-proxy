import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "bobol.zapret"

  property string state: "unknown"
  property string tooltip: "Proxy"

  readonly property bool active: root.state === "active"
  readonly property bool starting: root.state === "starting"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  function toggle() {
    if (root.bar) root.bar.run("ZAPRET_FROM=widget zapret-toggle")
    root.state = "starting"
    refreshTimer.restart()
    root.refresh()
  }

  Timer {
    id: refreshTimer
    interval: 300
    onTriggered: root.refresh()
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  IpcHandler {
    target: "bobol.zapret"

    function toggle(): void {
      root.toggle()
    }

    function status(): string {
      return "state=" + root.state + " active=" + root.active + " starting=" + root.starting
    }
  }

  Process {
    id: statusProc
    command: ["zapret-status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var parsed = JSON.parse(String(text || ""))
          if (parsed && typeof parsed === "object") {
            var s = String(parsed.alt || parsed.class || "unknown")
            if (s === "on") s = "active"
            root.state = s
            root.tooltip = String(parsed.tooltip || "Proxy")
          }
        } catch (e) { /* keep last state */ }
      }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf0e7"
    slotSize: Style.bar.iconSlot
    tooltipText: root.tooltip
    useActiveColor: true
    active: root.active
    activeColor: "#4caf50"
    dimmed: !root.active && !root.starting
    interactive: !root.starting
    onPressed: function(btn) {
      if (btn === Qt.RightButton) {
        if (root.bar) root.bar.run("zapret-settings")
      } else {
        root.toggle()
      }
    }
  }
}
