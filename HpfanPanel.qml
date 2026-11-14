import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "vee.hpfan"
  ipcTarget: "vee.hpfan"
  manageIpc: false

  property real cpuTemp: -1
  property int fanRpm: -1
  property string controlMode: "unknown"
  property string verificationStatus: "untested"
  property string logicalProfile: "unknown"
  property var turboBoostAllowed: null
  property bool fanBackendAvailable: false
  property string fanRequestedMode: "auto"
  property string fanEffectiveMode: "auto"
  property int fanTargetPercent: -1
  property bool fanSafetyForced: false
  property string curveDraft: "45:40,60:55,72:75,82:95"
  property bool curveEditing: false
  property bool readingAvailable: false
  property bool refreshPending: false

  readonly property var profileOptions: [
    { id: "auto", labelKey: "profile.auto", icon: "A" },
    { id: "quiet", labelKey: "profile.quiet", icon: "Q" },
    { id: "balanced", labelKey: "profile.balanced", icon: "B" },
    { id: "performance", labelKey: "profile.performance", icon: "P" },
    { id: "turbo", labelKey: "profile.turboCpu", icon: "T" }
  ]
  readonly property string helperPath: decodeURIComponent(
    String(Qt.resolvedUrl("plugin-status.py")).replace(/^file:\/\//, "")
  )
  readonly property string controlPath: decodeURIComponent(
    String(Qt.resolvedUrl("hpfanctl.py")).replace(/^file:\/\//, "")
  )
  readonly property int refreshInterval: Math.max(
    500,
    Math.min(10000, Number(setting("refreshIntervalMs", 2000)) || 2000)
  )
  readonly property string displayMode: String(setting("displayMode", "Compact")) === "Detailed"
    ? "Detailed"
    : "Compact"
  readonly property string temperatureText: readingAvailable
    ? Commons.I18n.formatNumber(cpuTemp, 0) + "°C"
    : strings.t("bar.unavailable")
  readonly property string rpmText: fanRpm >= 0
    ? Commons.I18n.formatNumber(fanRpm) + " RPM"
    : strings.t("bar.rpmUnavailable")
  readonly property string compactRpmText: fanRpm >= 1000
    ? Commons.I18n.formatNumber(fanRpm / 1000, 1) + "k"
    : fanRpm >= 0
      ? Commons.I18n.formatNumber(fanRpm)
      : ""
  readonly property string cpuProfileText: profileLabel(logicalProfile)
  readonly property string fanModeText: fanBackendAvailable
    ? fanSafetyForced
      ? strings.t("fan.fullSafety")
      : fanEffectiveMode === "full"
        ? strings.t("fan.fullSpeed")
        : fanEffectiveMode === "curve"
          ? strings.t("fan.customCurve").arg(Commons.I18n.formatNumber(fanTargetPercent))
        : strings.t("fan.firmwareAuto")
    : controlMode === "automatic"
      ? strings.t("fan.firmwareAuto")
      : strings.t("profile.unknown")
  readonly property string boostText: turboBoostAllowed === true
    ? strings.t("boost.allowed")
    : turboBoostAllowed === false
      ? strings.t("boost.disabled")
      : strings.t("profile.unknown")
  readonly property string statusText: displayMode === "Compact"
    ? temperatureText + (compactRpmText.length > 0 ? " · " + compactRpmText : "")
    : temperatureText + " · " + rpmText + " · " + cpuProfileText
  readonly property string barTooltip: strings.t("bar.tooltip")
    .arg(temperatureText)
    .arg(rpmText)
    .arg(cpuProfileText)
    .arg(fanModeText)

  Commons.Translations {
    id: strings
    directory: Qt.resolvedUrl("i18n")
  }

  function profileLabel(profile) {
    if (profile === "auto") return strings.t("profile.auto")
    if (profile === "quiet") return strings.t("profile.quiet")
    if (profile === "balanced") return strings.t("profile.balanced")
    if (profile === "performance") return strings.t("profile.performance")
    if (profile === "turbo") return strings.t("profile.turboCpu")
    return strings.t("profile.unknown")
  }

  function boundedNumber(value, minimum, maximum, fallback) {
    var parsed = Number(value)
    if (!isFinite(parsed) || parsed < minimum || parsed > maximum) return fallback
    return parsed
  }

  function curveText(points) {
    if (!Array.isArray(points) || points.length < 2 || points.length > 8) return ""
    var output = []
    for (var index = 0; index < points.length; index++) {
      var point = points[index]
      if (!point || typeof point !== "object") return ""
      var temperature = boundedNumber(point.temperature_c, 30, 84, -1)
      var percent = boundedNumber(point.percent, 40, 100, -1)
      if (temperature < 0 || percent < 0) return ""
      output.push(String(temperature) + ":" + String(Math.round(percent)))
    }
    return output.join(",")
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
      verificationStatus = "untested"
      if (Array.isArray(data.controls) && data.controls.length > 0) {
        var control = data.controls[0] || {}
        var candidateMode = String(control.reported_mode || "")
        if (candidateMode === "automatic" || candidateMode === "maximum" || candidateMode === "manual")
          controlMode = candidateMode
        var candidateStatus = String(control.verification_status || "")
        if (candidateStatus === "untested" || candidateStatus === "passed" || candidateStatus === "failed")
          verificationStatus = candidateStatus
      }

      logicalProfile = "unknown"
      turboBoostAllowed = null
      if (data.profile && typeof data.profile === "object") {
        var candidateProfile = String(data.profile.logical || "")
        if (candidateProfile === "auto" || candidateProfile === "quiet"
            || candidateProfile === "balanced" || candidateProfile === "performance"
            || candidateProfile === "turbo")
          logicalProfile = candidateProfile
        if (data.profile.turbo_boost_allowed === true) turboBoostAllowed = true
        else if (data.profile.turbo_boost_allowed === false) turboBoostAllowed = false
      }

      fanBackendAvailable = false
      fanRequestedMode = "auto"
      fanEffectiveMode = "auto"
      fanTargetPercent = -1
      fanSafetyForced = false
      if (data.fan_service && typeof data.fan_service === "object"
          && data.fan_service.available === true) {
        fanBackendAvailable = true
        if (data.fan_service.requested_mode === "auto" || data.fan_service.requested_mode === "full"
            || data.fan_service.requested_mode === "curve")
          fanRequestedMode = String(data.fan_service.requested_mode)
        if (data.fan_service.effective_mode === "auto" || data.fan_service.effective_mode === "full"
            || data.fan_service.effective_mode === "curve")
          fanEffectiveMode = String(data.fan_service.effective_mode)
        fanTargetPercent = Math.round(boundedNumber(data.fan_service.target_percent, 40, 100, -1))
        fanSafetyForced = data.fan_service.safety_forced === true
        var serviceRpm = boundedNumber(data.fan_service.rpm, 0, 100000, -1)
        if (serviceRpm >= 0) fanRpm = Math.round(serviceRpm)
        var nextCurve = curveText(data.fan_service.curve)
        if (!curveEditing && nextCurve.length > 0) curveDraft = nextCurve
      }
    } catch (error) {
      // Preserve the last valid reading. Raw helper output is never displayed.
    }
  }

  function refresh() {
    if (statusProc.running) {
      refreshPending = true
      return
    }
    statusProc.running = true
  }

  function runProfileAction(action, profile) {
    if (profileProc.running) return
    if (action !== "cycle" && action !== "toggle-turbo" && action !== "set") return

    var command = ["python3", root.controlPath, "--json", "--notify", action]
    if (action === "set") {
      if (profile !== "auto" && profile !== "quiet" && profile !== "balanced"
          && profile !== "performance" && profile !== "turbo") return
      command.push(profile)
    }
    profileProc.command = command
    profileProc.running = true
  }

  function runFanAction(mode) {
    if (fanProc.running || !fanBackendAvailable) return
    if (mode !== "auto" && mode !== "full" && mode !== "curve") return
    fanProc.command = ["python3", root.controlPath, "--json", "--notify", "fan", "set", mode]
    fanProc.running = true
  }

  function runCurveAction(spec) {
    if (fanProc.running || !fanBackendAvailable) return
    var value = String(spec || "").trim()
    if (value.length < 7 || value.length > 256) return
    fanProc.command = ["python3", root.controlPath, "--json", "--notify", "fan", "curve", "set", value]
    fanProc.running = true
  }

  function revealCurveEditor(flick, field) {
    runFanAction("curve")
    Qt.callLater(function() {
      if (flick) flick.contentY = Math.max(0, flick.contentHeight - flick.height)
      if (field) field.forceActiveFocus()
    })
  }

  onOpenedChanged: if (opened) refresh()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  ShellIpc {
    target: "vee.hpfan"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function cycle(): void { root.runProfileAction("cycle", "") }
    function toggleTurbo(): void { root.runProfileAction("toggle-turbo", "") }
    function fanAuto(): void { root.runFanAction("auto") }
    function fanFull(): void { root.runFanAction("full") }
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
        statusWatchdog.restart()
        return
      }
      statusWatchdog.stop()
      if (root.refreshPending) {
        root.refreshPending = false
        Qt.callLater(root.refresh)
      }
    }
  }

  Process {
    id: profileProc
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
    onRunningChanged: {
      if (running) {
        profileWatchdog.restart()
        return
      }
      profileWatchdog.stop()
      root.refresh()
    }
  }

  Process {
    id: fanProc
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
    onRunningChanged: {
      if (running) {
        fanWatchdog.restart()
        return
      }
      fanWatchdog.stop()
      root.refresh()
    }
  }

  Timer {
    id: statusWatchdog
    interval: 12000
    onTriggered: if (statusProc.running) statusProc.running = false
  }

  Timer {
    id: profileWatchdog
    interval: 6000
    onTriggered: if (profileProc.running) profileProc.running = false
  }

  Timer {
    id: fanWatchdog
    interval: 15000
    onTriggered: if (fanProc.running) fanProc.running = false
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
    horizontalMargin: 6.5
    verticalPadding: 8.75
    tooltipText: root.barTooltip
    onPressed: function(b) {
      if (b === Qt.RightButton) root.runProfileAction("toggle-turbo", "")
      else if (b === Qt.MiddleButton) root.runProfileAction("cycle", "")
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(560))

    content: PanelKeyCatcher {
      anchors.fill: parent
      implicitHeight: contentColumn.implicitHeight
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: contentColumn
          width: panelFlick.width
          spacing: Style.space(14)

        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroTemp.implicitHeight)

          Text {
            id: heroIcon
            textFormat: Text.PlainText
            text: ""
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroTemp.left
            anchors.rightMargin: Style.space(12)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: strings.t("panel.title")
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
            }

            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: strings.t("panel.subtitle")
              color: Qt.darker(root.bar.foreground, 1.4)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.0
              elide: Text.ElideRight
            }
          }

          Text {
            id: heroTemp
            textFormat: Text.PlainText
            text: root.temperatureText
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.displayLarge
            font.bold: true
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        Row {
          width: parent.width
          spacing: Style.space(20)

          Column {
            width: (parent.width - parent.spacing) / 2
            spacing: Style.space(10)

            Column {
              width: parent.width
              spacing: Style.spacing.labelGap
              Text {
                textFormat: Text.PlainText
                text: strings.t("panel.cpuProfile")
                color: Qt.darker(root.bar.foreground, 1.4)
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                text: root.cpuProfileText
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }

            Column {
              width: parent.width
              spacing: Style.spacing.labelGap
              Text {
                textFormat: Text.PlainText
                text: strings.t("panel.turboBoost")
                color: Qt.darker(root.bar.foreground, 1.4)
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                text: root.boostText
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }
          }

          Column {
            width: (parent.width - parent.spacing) / 2
            spacing: Style.space(10)

            Column {
              width: parent.width
              spacing: Style.spacing.labelGap
              Text {
                textFormat: Text.PlainText
                text: strings.t("panel.fanSpeed")
                color: Qt.darker(root.bar.foreground, 1.4)
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                text: root.rpmText
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }

            Column {
              width: parent.width
              spacing: Style.spacing.labelGap
              Text {
                textFormat: Text.PlainText
                text: strings.t("panel.fanMode")
                color: Qt.darker(root.bar.foreground, 1.4)
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.caption
              }
              Text {
                textFormat: Text.PlainText
                text: root.fanModeText
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
            }
          }
        }

        Button {
          width: parent.width
          visible: root.fanBackendAvailable
          iconText: "C"
          text: strings.t("panel.editCurve")
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          active: root.fanRequestedMode === "curve"
          onClicked: root.revealCurveEditor(panelFlick, curveField)
        }

        PanelSeparator { foreground: root.bar.foreground }

        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: strings.t("panel.cpuProfiles")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Text {
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: strings.t("panel.cpuProfilesHelp")
            color: Qt.darker(root.bar.foreground, 1.35)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Grid {
            id: profileGrid
            width: parent.width
            columns: 2
            columnSpacing: Style.space(6)
            rowSpacing: Style.space(6)

            Repeater {
              model: root.profileOptions

              Button {
                required property var modelData
                width: (profileGrid.width - profileGrid.columnSpacing) / 2
                iconText: String(modelData.icon)
                text: strings.t(String(modelData.labelKey))
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.bodySmall
                horizontalPadding: Style.spacing.controlPaddingX
                verticalPadding: Style.spacing.controlPaddingY + Style.space(2)
                bordered: true
                active: root.logicalProfile === String(modelData.id)
                onClicked: root.runProfileAction("set", String(modelData.id))
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: strings.t("panel.fanControl")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Button {
            width: parent.width
            iconText: "A"
            text: strings.t("panel.firmwareAutoActive")
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            active: root.fanBackendAvailable && root.fanRequestedMode === "auto"
            onClicked: root.fanBackendAvailable ? root.runFanAction("auto") : root.refresh()
          }

          Row {
            width: parent.width
            spacing: Style.space(6)

            Button {
              width: (parent.width - parent.spacing) / 2
              iconText: "F"
              text: strings.t("panel.fullSpeed")
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              enabled: root.fanBackendAvailable
              active: root.fanEffectiveMode === "full"
              opacity: enabled ? 1.0 : 0.5
              onClicked: root.runFanAction("full")
            }

            Button {
              width: (parent.width - parent.spacing) / 2
              iconText: "C"
              text: strings.t("panel.customCurve")
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              bordered: true
              enabled: root.fanBackendAvailable
              active: root.fanRequestedMode === "curve"
              opacity: enabled ? 1.0 : 0.5
              onClicked: root.revealCurveEditor(panelFlick, curveField)
            }
          }

          Column {
            width: parent.width
            visible: root.fanBackendAvailable
            spacing: Style.space(6)

            Text {
              width: parent.width
              textFormat: Text.PlainText
              text: strings.t("panel.curveHelp")
              wrapMode: Text.WordWrap
              color: Qt.darker(root.bar.foreground, 1.35)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.bodySmall
            }

            Row {
              width: parent.width
              spacing: Style.space(6)

              TextField {
                id: curveField
                width: parent.width - applyCurveButton.width - parent.spacing
                text: root.curveDraft
                placeholderText: "45:40,60:55,72:75,82:95"
                foreground: root.bar.foreground
                accent: Commons.Color.accent
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.bodySmall
                onTextEdited: root.curveDraft = text
                onActiveFocusChanged: root.curveEditing = activeFocus
              }

              Button {
                id: applyCurveButton
                text: strings.t("panel.applyCurve")
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                bordered: true
                onClicked: root.runCurveAction(root.curveDraft)
              }
            }
          }

          Text {
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            text: root.fanBackendAvailable
              ? strings.t("panel.fanVerifiedReason")
              : strings.t("panel.fanBackendUnavailable")
            color: Qt.darker(root.bar.foreground, 1.35)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
        }
        }
      }
    }
  }
}
