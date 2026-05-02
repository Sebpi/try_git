import SwiftUI

struct AddCameraView: View {
    @Environment(\.dismiss) private var dismiss

    var camera: Camera?
    var onSave: (Camera) -> Void

    @State private var name: String
    @State private var ipAddress: String
    @State private var port: String
    @State private var streamPath: String
    @State private var snapshotPath: String
    @State private var username: String
    @State private var password: String
    @State private var streamType: Camera.StreamType
    @State private var selectedPreset: CameraPreset?
    @State private var showingPresetPicker = false
    @State private var showingSetupNote = false

    init(camera: Camera? = nil, onSave: @escaping (Camera) -> Void) {
        self.camera = camera
        self.onSave = onSave
        let c = camera ?? Camera(
            name: "", ipAddress: "", port: 554, streamPath: "/live",
            snapshotPath: "/snapshot", username: "admin", password: "", streamType: .rtsp
        )
        _name = State(initialValue: c.name)
        _ipAddress = State(initialValue: c.ipAddress)
        _port = State(initialValue: "\(c.port)")
        _streamPath = State(initialValue: c.streamPath)
        _snapshotPath = State(initialValue: c.snapshotPath)
        _username = State(initialValue: c.username)
        _password = State(initialValue: c.password)
        _streamType = State(initialValue: c.streamType)
    }

    var isValid: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty &&
        !ipAddress.trimmingCharacters(in: .whitespaces).isEmpty &&
        Int(port) != nil
    }

    var body: some View {
        NavigationStack {
            Form {
                // Brand preset picker
                Section {
                    Button {
                        showingPresetPicker = true
                    } label: {
                        HStack {
                            Image(systemName: "list.bullet.rectangle")
                                .foregroundColor(.accentColor)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Camera Brand Preset")
                                    .foregroundColor(.primary)
                                Text(selectedPreset.map { "\($0.brand) – \($0.model)" } ?? "Select to auto-fill settings")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    if let preset = selectedPreset, !preset.setupNote.isEmpty {
                        Button {
                            showingSetupNote = true
                        } label: {
                            Label("Setup Guide for \(preset.brand)", systemImage: "info.circle")
                                .font(.subheadline)
                        }
                    }
                } header: {
                    Text("Quick Setup")
                }

                Section("Camera Info") {
                    TextField("Name (e.g. Front Door)", text: $name)
                    TextField("IP Address (e.g. 192.168.1.100)", text: $ipAddress)
                        .keyboardType(.decimalPad)
                    TextField("Port", text: $port)
                        .keyboardType(.numberPad)
                    Picker("Stream Type", selection: $streamType) {
                        ForEach(Camera.StreamType.allCases, id: \.self) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }
                }

                Section("Paths") {
                    TextField("Stream Path", text: $streamPath)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    TextField("Snapshot Path", text: $snapshotPath)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section("Authentication") {
                    TextField("Username", text: $username)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    SecureField("Password", text: $password)
                }

                Section {
                    urlPreview
                }
            }
            .navigationTitle(camera == nil ? "Add Camera" : "Edit Camera")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        var updated = camera ?? Camera(
                            name: "", ipAddress: "", port: 554, streamPath: "",
                            snapshotPath: "", username: "", password: "", streamType: .rtsp
                        )
                        updated.name = name
                        updated.ipAddress = ipAddress
                        updated.port = Int(port) ?? 554
                        updated.streamPath = streamPath
                        updated.snapshotPath = snapshotPath
                        updated.username = username
                        updated.password = password
                        updated.streamType = streamType
                        onSave(updated)
                        dismiss()
                    }
                    .disabled(!isValid)
                }
            }
            .sheet(isPresented: $showingPresetPicker) {
                PresetPickerView { preset in
                    applyPreset(preset)
                }
            }
            .alert(selectedPreset?.brand ?? "Setup Guide", isPresented: $showingSetupNote) {
                Button("OK") {}
            } message: {
                Text(selectedPreset?.setupNote ?? "")
            }
        }
    }

    private func applyPreset(_ preset: CameraPreset) {
        selectedPreset = preset
        port = "\(preset.port)"
        streamPath = preset.streamPath
        snapshotPath = preset.snapshotPath
        username = preset.defaultUsername
        streamType = preset.streamType
        if name.isEmpty {
            name = preset.brand == "Generic / Other" ? "" : preset.brand
        }
    }

    private var urlPreview: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Stream URL Preview")
                .font(.caption)
                .foregroundColor(.secondary)
            let previewCam = Camera(
                name: name,
                ipAddress: ipAddress.isEmpty ? "x.x.x.x" : ipAddress,
                port: Int(port) ?? 554,
                streamPath: streamPath,
                snapshotPath: snapshotPath,
                username: username,
                password: password.isEmpty ? "" : "••••",
                streamType: streamType
            )
            Text(previewCam.rtspURL?.absoluteString ?? "rtsp://...")
                .font(.caption)
                .foregroundColor(.accentColor)
                .lineLimit(3)
        }
        .padding(.vertical, 4)
    }
}

struct PresetPickerView: View {
    @Environment(\.dismiss) private var dismiss
    var onSelect: (CameraPreset) -> Void

    private var grouped: [(String, [CameraPreset])] {
        Dictionary(grouping: CameraPreset.all, by: \.brand)
            .sorted { a, b in
                // Xiaomi first
                if a.key == "Xiaomi" { return true }
                if b.key == "Xiaomi" { return false }
                if a.key == "Generic / Other" { return false }
                if b.key == "Generic / Other" { return true }
                return a.key < b.key
            }
    }

    var body: some View {
        NavigationStack {
            List {
                ForEach(grouped, id: \.0) { brand, presets in
                    Section(brand) {
                        ForEach(presets, id: \.model) { preset in
                            Button {
                                onSelect(preset)
                                dismiss()
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(preset.model)
                                        .foregroundColor(.primary)
                                    Text("rtsp://\(preset.defaultUsername.isEmpty ? "" : "\(preset.defaultUsername):••••@")<ip>:\(preset.port)\(preset.streamPath)")
                                        .font(.caption)
                                        .foregroundColor(.accentColor)
                                        .lineLimit(1)
                                }
                                .padding(.vertical, 2)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Select Brand")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
