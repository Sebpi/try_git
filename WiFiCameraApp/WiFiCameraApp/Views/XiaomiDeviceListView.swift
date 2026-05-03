import SwiftUI

struct XiaomiDeviceListView: View {
    @Environment(\.dismiss) private var dismiss
    let devices: [XiaomiDevice]
    var onAdd: (XiaomiDevice) -> Void

    var body: some View {
        NavigationStack {
            List(devices) { device in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "camera.fill")
                            .foregroundColor(.accentColor)
                        Text(device.name)
                            .font(.headline)
                        Spacer()
                        statusBadge(device.isOnline)
                    }

                    Text(device.model)
                        .font(.caption)
                        .foregroundColor(.secondary)

                    if !device.localIP.isEmpty {
                        Label(device.localIP, systemImage: "network")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Label("IP not found — enter manually after adding", systemImage: "exclamationmark.triangle")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }

                    tokenRow(device.token)

                    Button {
                        onAdd(device)
                        dismiss()
                    } label: {
                        Label("Add to Camera List", systemImage: "plus.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .padding(.top, 2)
                }
                .padding(.vertical, 6)
            }
            .navigationTitle("Found Cameras (\(devices.count))")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .overlay {
                if devices.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "camera.on.rectangle")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("No Cameras Found")
                            .font(.headline)
                        Text("No camera devices were found on your account.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                }
            }
        }
    }

    private func statusBadge(_ online: Bool) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(online ? Color.green : Color.gray)
                .frame(width: 7, height: 7)
            Text(online ? "Online" : "Offline")
                .font(.caption2)
                .foregroundColor(online ? .green : .secondary)
        }
    }

    private func tokenRow(_ token: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Device Token")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                Text(token)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundColor(.accentColor)
                    .lineLimit(1)
            }
            Spacer()
            Button {
                UIPasteboard.general.string = token
            } label: {
                Image(systemName: "doc.on.doc")
                    .font(.caption)
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
        }
    }
}
