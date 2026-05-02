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

    init(camera: Camera? = nil, onSave: @escaping (Camera) -> Void) {
        self.camera = camera
        self.onSave = onSave
        let c = camera ?? Camera(name: "", ipAddress: "", port: 554, streamPath: "/stream",
                                 snapshotPath: "/snapshot", username: "", password: "", streamType: .rtsp)
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
                    TextField("Stream Path (e.g. /stream)", text: $streamPath)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    TextField("Snapshot Path (e.g. /snapshot)", text: $snapshotPath)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section("Authentication (optional)") {
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
                        var updated = camera ?? Camera(name: "", ipAddress: "", port: 554, streamPath: "",
                                                       snapshotPath: "", username: "", password: "", streamType: .rtsp)
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
        }
    }

    private var urlPreview: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Stream URL Preview")
                .font(.caption)
                .foregroundColor(.secondary)
            let previewCam = Camera(name: name, ipAddress: ipAddress.isEmpty ? "x.x.x.x" : ipAddress,
                                    port: Int(port) ?? 554, streamPath: streamPath,
                                    snapshotPath: snapshotPath, username: username,
                                    password: password, streamType: streamType)
            Text(previewCam.rtspURL?.absoluteString ?? "rtsp://...")
                .font(.caption)
                .foregroundColor(.accentColor)
                .lineLimit(2)
        }
        .padding(.vertical, 4)
    }
}
