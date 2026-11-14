import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "vee.hpfan"

  property real cpuTemp: -1
  property int fanRpm: -1
  property string controlMode: "unknown"
  property bool manualDutyAvailable: false
  property bool maxAutoCandidate: false
  property bool writeVerified: false
  property bool readingAvailable: false
  property bool refreshPending: false

  readonly property string helperPath: decodeURIComponent(
    String(Qt.resolvedUrl("plugin-status.py")).replace(/^file:\/\//, "")
  )
  readonly property int refreshInterval: Math.max(
    500,
    Math.min(10000, Number(setting("refreshIntervalMs", 2000)) || 2000)
  )
  readonly property string temperatureText: readingAvailable
    ? Commons.I18n.formatNumber(cpuTemp, 0) + "°C"
    : strings.t("bar.unavailable")
  readonly property string rpmText: fanRpm >= 0
    ? Commons.I18n.formatNumber(fanRpm) + " RPM"
    : strings.t("bar.rpmUnavailable")
  readonly property string profileText: {
    if (controlMode === "automatic") return strings.t("profile.auto")
    if (controlMode === "maximum") return strings.t("profile.turbo")
    if (controlMode === "manual") return strings.t("profile.custom")
    return strings.t("profile.unknown")
  }
  readonly property string statusText: temperatureText + " · " + rpmText
  readonly property string controlText: {
    if (manualDutyAvailable) return strings.t("control.manualAvailable")
    if (maxAutoCandidate && !writeVerified) return strings.t("control.awaitingVerification")
    return strings.t("control.monitorOnly")
  }
  readonly property string tooltip: strings.t("bar.tooltip")
    .arg(temperatureText)
    .arg(rpmText)
    .arg(profileText)
    .arg(controlText)

  Commons.Translations {
    id: strings
    directory: Qt.resolvedUrl("i18n")
  }

  function boundedNumber(value, minimum, maximum, fallback) {
    var parsed = Number(value)
    if (!isFinite(parsed) || parsed < minimum || parsed > maximum) return fallback
    return parsed
  }

  function consume(rawText) {
    var raw = String(rawText || "")
    if (raw.length === 0 || raw.length > 65536) return

    try {
      var data = JSON.parse(raw)
      var hottest = boundedNumber(data.cpu_max_c, 0.1, 150, -1)
      var packageTemp = boundedNumber(data.cpu_package_c, 0.1, 150, -1)
      var nextTemp = hottest >= 0 ? hottest : packageTemp
      if (nextTemp >= 0) {
        cpuTemp = nextTemp
        readingAvailable = true
      }

      fanRpm = -1
      if (Array.isArray(data.fans) && data.fans.length > 0)
        fanRpm = Math.round(boundedNumber(data.fans[0].rpm, 0, 100000, -1))

      controlMode = "unknown"
      manualDutyAvailable = false
      maxAutoCandidate = false
      writeVerified = false
      if (Array.isArray(data.controls) && data.controls.length > 0) {
        var control = data.controls[0] || {}
        var candidateMode = String(control.reported_mode || "")
        if (candidateMode === "automatic" || candidateMode === "maximum" || candidateMode === "manual")
          controlMode = candidateMode
        manualDutyAvailable = control.manual_duty_available === true
        maxAutoCandidate = control.max_auto_candidate === true
        writeVerified = control.write_verified === true
      }
    } catch (error) {
      // Keep the last valid reading. No command output is displayed verbatim.
    }
  }

  function refresh() {
    if (statusProc.running) {
      refreshPending = true
      return
    }
    statusProc.running = true
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  ShellIpc {
    target: "vee.hpfan"
    function refresh(): void { root.refresh() }
  }

  Process {
    id: statusProc
    command: ["python3", root.helperPath]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.consume(text)
    }
    onRunningChanged: {
      if (running) {
        processWatchdog.restart()
        return
      }
      processWatchdog.stop()
      if (root.refreshPending) {
        root.refreshPending = false
        Qt.callLater(root.refresh)
      }
    }
  }

  Timer {
    id: processWatchdog
    interval: 3000
    onTriggered: if (statusProc.running) statusProc.running = false
  }

  Timer {
    interval: root.refreshInterval
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.statusText
    labelVisible: true
    horizontalMargin: 8.75
    verticalPadding: 8.75
    tooltipText: root.tooltip
    onPressed: root.refresh()
  }
}
