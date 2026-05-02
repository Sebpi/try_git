import SwiftUI

struct CameraDiscoveryView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var discovery = CameraDiscoveryService()
    var onAdd: (DiscoveredCamera) -> Void

    var body: some View {
        NavigationStack {
            Group {
                if discovery.discoveredCameras.isEmpty && !discovery.isScanning {
                    emptyState
                } else {
                    List(discovery.discoveredCameras) { cam in
                        Button {
                            onAdd(cam)
                            dismiss()
                        } label: {
                            HStack {
                                Image(systemName: "camera.fill")
                                    .foregroundColor(.accentColor)
                                VStack(alignment: .leading) {
                                    Text(cam.name).font(.headline)
                                    Text("\(cam.host):\(cam.port)").font(.caption).foregroundColor(.secondary)
                                    Text(cam.type).font(.caption2).foregroundColor(.accentColor)
                                }
                            }
                        }
                        .foregroundColor(.primary)
                    }
                }
            }
            .navigationTitle("Discover Cameras")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if discovery.isScanning {
                        ProgressView()
                    } else {
                        Button("Scan") { discovery.startDiscovery() }
                    }
                }
            }
            .onAppear { discovery.startDiscovery() }
            .onDisappear { discovery.stopDiscovery() }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "antenna.radiowaves.left.and.right")
                .font(.system(size: 50))
                .foregroundColor(.secondary)
            Text("No Cameras Found")
                .font(.title3)
                .fontWeight(.semibold)
            Text("Make sure your camera is powered on and connected to the same WiFi network.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .padding(.horizontal)
            Button("Scan Again") {
                discovery.startDiscovery()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}
