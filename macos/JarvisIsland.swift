import Cocoa
import Speech
import AVFoundation

private func jarvisLog(_ message: String) {
    let formatter = ISO8601DateFormatter()
    let line = "[JARVIS \(formatter.string(from: Date()))] \(message)\n"
    print(line, terminator: "")
    let logURL = URL(fileURLWithPath: "/tmp/jarvis-island.log")
    if let data = line.data(using: .utf8) {
        if FileManager.default.fileExists(atPath: logURL.path), let handle = try? FileHandle(forWritingTo: logURL) {
            try? handle.seekToEnd(); try? handle.write(contentsOf: data); try? handle.close()
        } else { try? data.write(to: logURL) }
    }
}

final class IslandView: NSVisualEffectView {
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        material = .hudWindow; blendingMode = .withinWindow; state = .active
        wantsLayer = true; layer?.cornerRadius = 28; layer?.borderWidth = 1
        layer?.masksToBounds = true
        layer?.borderColor = NSColor(calibratedWhite: 1, alpha: 0.18).cgColor
    }
    required init?(coder: NSCoder) { fatalError("IslandView cannot be decoded") }
}

final class CircleView: NSView {
    var onClick: (() -> Void)?
    var hasNewData = false { didSet { needsDisplay = true } }
    private var downPoint: NSPoint = .zero
    private var moved = false

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedWhite: 0.03, alpha: 0.98).setFill()
        NSBezierPath(ovalIn: bounds.insetBy(dx: 1, dy: 1)).fill()
        let text = NSString(string: "J")
        text.draw(at: NSPoint(x: bounds.midX - 7, y: bounds.midY - 10), withAttributes: [.font: NSFont.systemFont(ofSize: 20, weight: .bold), .foregroundColor: NSColor.white])
        if hasNewData {
            NSColor.systemOrange.setFill()
            NSBezierPath(ovalIn: NSRect(x: bounds.maxX - 13, y: bounds.maxY - 13, width: 8, height: 8)).fill()
        }
    }

    override func mouseDown(with event: NSEvent) { downPoint = event.locationInWindow; moved = false }
    override func mouseDragged(with event: NSEvent) {
        guard let window else { return }
        let point = event.locationInWindow
        let dx = point.x - downPoint.x; let dy = point.y - downPoint.y
        if abs(dx) > 2 || abs(dy) > 2 { moved = true }
        window.setFrameOrigin(NSPoint(x: window.frame.minX + dx, y: window.frame.minY + dy))
        downPoint = point
    }
    override func mouseUp(with event: NSEvent) { if !moved { onClick?() } }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, SFSpeechRecognizerDelegate {
    private var panel: NSPanel!
    private var circlePanel: NSPanel!
    private var statusLabel: NSTextField!
    private var messageLabel: NSTextField!
    private var dot: NSView!
    private var micButton: NSButton!
    private var collapseButton: NSButton!
    private var circleView: CircleView!
    private var plannerLabel: NSTextField!
    private var retryButton: NSButton!
    private var topStack: NSStackView!
    private var separatorView: NSView!
    private var leftStack: NSStackView!
    private var rightStack: NSStackView!
    private var recognizer: SFSpeechRecognizer?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()
    private let synthesizer = NSSpeechSynthesizer()
    private var speechSilenceTimer: Timer?
    private var latestTranscript = ""
    private let apiURL = URL(string: "http://127.0.0.1:8000/api/chat/text")!
    private var listening = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        jarvisLog("Island launched")
        synthesizer.setVoice(NSSpeechSynthesizer.defaultVoice)
        synthesizer.volume = 1.0
        synthesizer.rate = 190
        NSApp.setActivationPolicy(.accessory); buildPanel(); checkHealth(); loadBoldOverview(); installKeyboardShortcuts()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    private func buildPanel() {
        guard let screen = NSScreen.main else { return }
        let frame = screen.frame; let menuBarHeight = frame.maxY - screen.visibleFrame.maxY
        let width: CGFloat = min(420, frame.width - 40); let height: CGFloat = 110
        let rect = NSRect(x: frame.midX - width / 2, y: frame.maxY - menuBarHeight - height, width: width, height: height)
        panel = NSPanel(contentRect: rect, styleMask: [.borderless, .nonactivatingPanel, .resizable], backing: .buffered, defer: false)
        panel.level = .floating; panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = false; panel.hidesOnDeactivate = false
        panel.minSize = NSSize(width: 340, height: 96); panel.maxSize = NSSize(width: min(900, frame.width - 24), height: 360)
        panel.delegate = self; panel.isMovableByWindowBackground = true; panel.contentView = IslandView(frame: NSRect(origin: .zero, size: rect.size))
        panel.contentView?.wantsLayer = true
        panel.contentView?.layer?.backgroundColor = NSColor.clear.cgColor
        panel.contentView?.layer?.cornerRadius = 34
        panel.contentView?.layer?.masksToBounds = true
        let content = panel.contentView!
        let top = NSStackView(frame: NSRect(x: 14, y: height - 27, width: width - 28, height: 19)); top.orientation = .horizontal; top.alignment = .centerY; top.spacing = 5; top.autoresizingMask = [.width, .minYMargin]; topStack = top
        content.addSubview(top)
        let nook = NSButton(title: "◒  Nook", target: nil, action: nil); nook.font = NSFont.systemFont(ofSize: 10, weight: .semibold); nook.bezelStyle = .texturedRounded; nook.isBordered = false; nook.contentTintColor = .white; top.addArrangedSubview(nook)
        let tray = NSButton(title: "▱  Tray", target: nil, action: nil); tray.font = NSFont.systemFont(ofSize: 10, weight: .semibold); tray.bezelStyle = .texturedRounded; tray.isBordered = false; tray.contentTintColor = NSColor(calibratedWhite: 1, alpha: 0.85); top.addArrangedSubview(tray)
        let spacer = NSView(); top.addArrangedSubview(spacer)
        collapseButton = NSButton(title: "⌄", target: self, action: #selector(collapsePanel)); collapseButton.font = NSFont.systemFont(ofSize: 13); collapseButton.isBordered = false; collapseButton.contentTintColor = NSColor(calibratedWhite: 1, alpha: 0.8); top.addArrangedSubview(collapseButton)

        let separator = NSView(frame: NSRect(x: width / 2, y: 13, width: 1, height: height - 40)); separator.wantsLayer = true; separator.layer?.backgroundColor = NSColor(calibratedWhite: 1, alpha: 0.13).cgColor; separator.autoresizingMask = [.height, .minXMargin, .maxXMargin]; separatorView = separator; content.addSubview(separator)
        let left = NSStackView(frame: NSRect(x: 18, y: 16, width: width / 2 - 32, height: 60)); left.orientation = .vertical; left.alignment = .leading; left.spacing = 2; left.autoresizingMask = [.width, .maxYMargin]; leftStack = left; content.addSubview(left)
        let title = NSTextField(labelWithString: "J.A.R.V.I.S"); title.font = NSFont.systemFont(ofSize: 15, weight: .bold); title.textColor = .white; left.addArrangedSubview(title)
        let subtitle = NSTextField(labelWithString: "Local Ollama assistant"); subtitle.font = NSFont.systemFont(ofSize: 8, weight: .medium); subtitle.textColor = NSColor(calibratedWhite: 1, alpha: 0.58); left.addArrangedSubview(subtitle)
        messageLabel = NSTextField(labelWithString: "Tap the mic to speak"); messageLabel.font = NSFont.systemFont(ofSize: 9); messageLabel.textColor = NSColor(calibratedWhite: 1, alpha: 0.78); messageLabel.lineBreakMode = .byWordWrapping; messageLabel.maximumNumberOfLines = 2; messageLabel.usesSingleLineMode = false; messageLabel.cell?.wraps = true; messageLabel.cell?.isScrollable = false; left.addArrangedSubview(messageLabel)
        let controls = NSStackView(); controls.orientation = .horizontal; controls.alignment = .centerY; controls.spacing = 8; left.addArrangedSubview(controls)
        dot = NSView(frame: NSRect(x: 0, y: 0, width: 10, height: 10)); dot.wantsLayer = true; dot.layer?.cornerRadius = 5; dot.layer?.backgroundColor = NSColor.systemGreen.cgColor; controls.addArrangedSubview(dot)
        statusLabel = NSTextField(labelWithString: "READY"); statusLabel.font = NSFont.monospacedSystemFont(ofSize: 9, weight: .medium); statusLabel.textColor = NSColor(calibratedWhite: 1, alpha: 0.65); controls.addArrangedSubview(statusLabel)
        micButton = NSButton(title: " Speak", target: self, action: #selector(toggleListening)); micButton.font = NSFont.systemFont(ofSize: 10); micButton.bezelStyle = .texturedRounded; micButton.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Speak"); micButton.contentTintColor = .white; micButton.toolTip = "Speak to JARVIS"; controls.addArrangedSubview(micButton)

        let right = NSStackView(frame: NSRect(x: width / 2 + 18, y: 17, width: width / 2 - 36, height: 62)); right.orientation = .vertical; right.alignment = .leading; right.spacing = 2; right.autoresizingMask = [.width, .minXMargin, .maxYMargin]; rightStack = right; content.addSubview(right)
        let date = Date(); let month = DateFormatter(); month.dateFormat = "MMM"; let day = DateFormatter(); day.dateFormat = "d"; let weekday = DateFormatter(); weekday.dateFormat = "EEEE"
        let dateLabel = NSTextField(labelWithString: "\(month.string(from: date))  \(day.string(from: date))"); dateLabel.font = NSFont.systemFont(ofSize: 16, weight: .bold); dateLabel.textColor = .white; right.addArrangedSubview(dateLabel)
        let weekdayLabel = NSTextField(labelWithString: weekday.string(from: date)); weekdayLabel.font = NSFont.systemFont(ofSize: 8, weight: .medium); weekdayLabel.textColor = NSColor(calibratedWhite: 1, alpha: 0.58); right.addArrangedSubview(weekdayLabel)
        let calendarLabel = NSTextField(labelWithString: "◫  Local calendar"); calendarLabel.font = NSFont.systemFont(ofSize: 8); calendarLabel.textColor = NSColor(calibratedWhite: 1, alpha: 0.72); right.addArrangedSubview(calendarLabel)
        plannerLabel = NSTextField(labelWithString: "Loading Bold planner…"); plannerLabel.font = NSFont.systemFont(ofSize: 8); plannerLabel.textColor = NSColor(calibratedWhite: 1, alpha: 0.58); right.addArrangedSubview(plannerLabel)
        retryButton = NSButton(title: "Retry", target: self, action: #selector(loadBoldOverview)); retryButton.font = NSFont.systemFont(ofSize: 10); retryButton.isHidden = true; right.addArrangedSubview(retryButton)
        restorePanelState()
        if !UserDefaults.standard.bool(forKey: "jarvisIsland.isCollapsed") { panel.orderFrontRegardless() }
    }

    func windowDidResize(_ notification: Notification) { savePanelFrame(); relayout() }
    func windowDidMove(_ notification: Notification) {
        if let moved = notification.object as? NSPanel, moved == circlePanel { UserDefaults.standard.set(NSStringFromRect(moved.frame), forKey: "jarvisIsland.circleFrame") } else { savePanelFrame() }
    }

    private func relayout() {
        guard let content = panel.contentView else { return }
        let width = content.bounds.width; let height = content.bounds.height
        topStack.frame = NSRect(x: 14, y: height - 27, width: width - 28, height: 19)
        separatorView.frame = NSRect(x: width / 2, y: 13, width: 1, height: height - 40)
        leftStack.frame = NSRect(x: 18, y: 16, width: width / 2 - 32, height: height - 40)
        rightStack.frame = NSRect(x: width / 2 + 18, y: 17, width: width / 2 - 36, height: height - 43)
    }

    private func savePanelFrame() {
        guard panel != nil else { return }
        UserDefaults.standard.set(NSStringFromRect(panel.frame), forKey: "jarvisIsland.panelFrame")
    }

    private func restorePanelState() {
        if let saved = UserDefaults.standard.string(forKey: "jarvisIsland.panelFrame") {
            let old = NSRectFromString(saved)
            let compact = old.width > 500 || old.height > 130
            panel.setFrame(compact ? NSRect(x: old.midX - 210, y: old.midY - 55, width: 420, height: 110) : old, display: false)
        }
        if UserDefaults.standard.bool(forKey: "jarvisIsland.isCollapsed") { collapsePanel() }
    }

    private func buildCircle() {
        guard circlePanel == nil, let screen = NSScreen.main else { return }
        let size: CGFloat = 54; let frame = screen.frame
        let saved = UserDefaults.standard.string(forKey: "jarvisIsland.circleFrame").map(NSRectFromString) ?? NSRect(x: frame.midX - size / 2, y: frame.maxY - 90, width: size, height: size)
        circlePanel = NSPanel(contentRect: saved, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        circlePanel.level = .floating; circlePanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]; circlePanel.isOpaque = false; circlePanel.backgroundColor = .clear; circlePanel.hasShadow = false; circlePanel.isMovableByWindowBackground = false; circlePanel.delegate = self
        circleView = CircleView(frame: NSRect(origin: .zero, size: saved.size)); circlePanel.contentView = circleView; circleView.onClick = { [weak self] in self?.expandPanel() }
    }

    @objc private func collapsePanel() {
        buildCircle(); UserDefaults.standard.set(true, forKey: "jarvisIsland.isCollapsed")
        NSAnimationContext.runAnimationGroup { context in context.duration = 0.2; panel.animator().alphaValue = 0.0 } completionHandler: { self.panel.orderOut(nil); self.panel.alphaValue = 1; self.circlePanel?.orderFrontRegardless() }
    }

    @objc private func expandPanel() {
        guard circlePanel != nil else { return }
        UserDefaults.standard.set(false, forKey: "jarvisIsland.isCollapsed"); panel.setFrameOrigin(NSPoint(x: circlePanel.frame.midX - panel.frame.width / 2, y: circlePanel.frame.minY - panel.frame.height - 8)); panel.alphaValue = 0; panel.orderFrontRegardless(); circlePanel.orderOut(nil)
        NSAnimationContext.runAnimationGroup { context in context.duration = 0.2; panel.animator().alphaValue = 1 }
    }

    @objc private func loadBoldOverview() {
        plannerLabel?.stringValue = "Loading Bold planner…"; retryButton?.isHidden = true
        URLSession.shared.dataTask(with: URL(string: "http://127.0.0.1:8000/api/schedule/bold/overview")!) { [weak self] data, response, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                guard let data, let http = response as? HTTPURLResponse, http.statusCode == 200, let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let tasks = payload["tasks"] as? [[String: Any]], let events = payload["events"] as? [[String: Any]] else { self.plannerLabel.stringValue = "Bold planner unavailable"; self.retryButton.isHidden = false; return }
                self.plannerLabel.stringValue = "\(events.count) events · \(tasks.count) tasks from Bold"; self.retryButton.isHidden = true
                self.circleView?.hasNewData = !events.isEmpty
            }
        }.resume()
    }

    private func installKeyboardShortcuts() {
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            if event.keyCode == 53 { self.collapsePanel(); return nil }
            if event.keyCode == 36, self.circlePanel != nil { self.expandPanel(); return nil }
            if event.modifierFlags.contains([.command, .shift]) && event.charactersIgnoringModifiers?.lowercased() == "m" { self.toggleListening(); return nil }
            return event
        }
    }

    private func requestSpeechPermission() {
        SFSpeechRecognizer.requestAuthorization { _ in DispatchQueue.main.async { self.recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_GB")); self.recognizer?.delegate = self } }
    }
    @objc private func toggleListening() {
        if recognizer == nil {
            jarvisLog("Requesting speech recognition permission")
            requestSpeechPermission()
            setStatus("ALLOW SPEECH", color: .systemOrange)
            messageLabel?.stringValue = "Allow Speech Recognition, then tap mic again"
            return
        }
        listening ? stopListening() : startListening()
    }

    private func startListening() {
        guard let recognizer, recognizer.isAvailable else { setStatus("SPEECH UNAVAILABLE", color: .systemOrange); return }
        recognitionTask?.cancel(); recognitionTask = nil
        let request = SFSpeechAudioBufferRecognitionRequest(); recognitionRequest = request
        let input = audioEngine.inputNode; let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
        audioEngine.prepare()
        do {
            try audioEngine.start(); listening = true; micButton.image = NSImage(systemSymbolName: "stop.fill", accessibilityDescription: "Stop"); setStatus("LISTENING", color: .systemRed); jarvisLog("Microphone listening")
            recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
                guard let self else { return }
                if let result {
                    let transcript = result.bestTranscription.formattedString
                    self.latestTranscript = transcript
                    self.messageLabel.stringValue = transcript.isEmpty ? "Listening…" : transcript
                    if !transcript.isEmpty { jarvisLog("Speech partial: \(transcript)") }
                    if !transcript.isEmpty {
                        DispatchQueue.main.async {
                            self.speechSilenceTimer?.invalidate()
                            self.speechSilenceTimer = Timer.scheduledTimer(withTimeInterval: 1.4, repeats: false) { [weak self] _ in
                                guard let self, !self.latestTranscript.isEmpty, self.listening else { return }
                                jarvisLog("Silence detected; finalizing speech")
                                self.finishListening(text: self.latestTranscript)
                            }
                        }
                    }
                    if result.isFinal { jarvisLog("Speech recognized: \(transcript)"); self.finishListening(text: transcript) }
                }
                if let error { jarvisLog("Speech error: \(error.localizedDescription)"); self.stopListening() }
            }
        } catch { setStatus("MIC UNAVAILABLE", color: .systemOrange); stopListening() }
    }

    private func finishListening(text: String) {
        stopListening(); guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { jarvisLog("Empty speech result"); return }; setStatus("THINKING", color: .systemBlue); jarvisLog("Sending API request: \(text)")
        var request = URLRequest(url: apiURL); request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.setValue(UUID().uuidString, forHTTPHeaderField: "Idempotency-Key"); request.httpBody = try? JSONSerialization.data(withJSONObject: ["message": text, "session_id": "mac-island"])
        URLSession.shared.dataTask(with: request) { [weak self] data, responseObject, error in DispatchQueue.main.async { guard let self else { return }; if let error { jarvisLog("API error: \(error.localizedDescription)"); self.setStatus("OFFLINE", color: .systemOrange); self.messageLabel.stringValue = error.localizedDescription; return }; let status = (responseObject as? HTTPURLResponse)?.statusCode ?? 0; guard let data, let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let response = payload["response"] as? String else { jarvisLog("Invalid API response (HTTP \(status)): \(String(data: data ?? Data(), encoding: .utf8) ?? "<empty>")"); self.setStatus("ERROR", color: .systemOrange); return }; jarvisLog("API response received: \(response)"); self.messageLabel.stringValue = response; self.setStatus("READY", color: .systemGreen); if self.synthesizer.isSpeaking { self.synthesizer.stopSpeaking() }; let started = self.synthesizer.startSpeaking(response); jarvisLog("Speech playback started=\(started)") } }.resume()
    }
    private func stopListening() { speechSilenceTimer?.invalidate(); speechSilenceTimer = nil; if audioEngine.isRunning { audioEngine.stop() }; audioEngine.inputNode.removeTap(onBus: 0); recognitionRequest?.endAudio(); recognitionTask?.cancel(); recognitionRequest = nil; recognitionTask = nil; listening = false; micButton?.image = NSImage(systemSymbolName: "mic.fill", accessibilityDescription: "Speak") }
    private func checkHealth() { URLSession.shared.dataTask(with: URL(string: "http://127.0.0.1:8000/api/health")!) { [weak self] data, _, _ in DispatchQueue.main.async { self?.setStatus(data != nil ? "READY" : "OFFLINE", color: data != nil ? .systemGreen : .systemOrange) } }.resume() }
    private func setStatus(_ text: String, color: NSColor) { statusLabel?.stringValue = text; dot?.layer?.backgroundColor = color.cgColor; dot?.layer?.shadowColor = color.cgColor; dot?.layer?.shadowRadius = 5; dot?.layer?.shadowOpacity = 0.8 }
}

let app = NSApplication.shared; let delegate = AppDelegate(); app.delegate = delegate; app.run()
