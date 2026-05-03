import SwiftUI

struct CameraListView: View {
    @EnvironmentObject var store: CameraStore
    @State private var showingAddCamera = false
    @State private var showingDiscovery = false
    @State private var showingXiaomiLogin = false

    var body: some View {
        Group {
            if store.cameras.isEmpty {
                emptyState
            } else {
                List {
                    ForEach(store.cameras) { camera in
                        NavigationLink(destination: CameraStreamView(camera: camera)) {
                            CameraRowView(camera: camera)
                        }
                    }
                    .onDelete(perform: store.delete)
                }
            }
        }
        .navigationTitle("WiFi Cameras")
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button {
                    showingDiscovery = true
                } label: {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    Button {
                        showingAddCamera = true
                    } label: {
                        Label("Add Manually", systemImage: "pencil")
                    }
                    Button {
                        showingXiaomiLogin = true
                    } label: {
                        Label("Xiaomi Cloud Login", systemImage: "cloud")
                    }
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showingAddCamera) {
            AddCameraView { camera in
                store.add(camera)
            }
        }
        .sheet(isPresented: $showingXiaomiLogin) {
            XiaomiLoginView { camera in
                store.add(camera)
            }
        }
        .sheet(isPresented: $showingDiscovery) {
            CameraDiscoveryView { discovered in
                let camera = Camera(
                    name: discovered.name,
                    ipAddress: discovered.host,
                    port: discovered.type.contains("rtsp") ? discovered.port : 80,
                    streamPath: "/stream",
                    snapshotPath: "/snapshot",
                    username: "",
                    password: "",
                    streamType: discovered.type.contains("rtsp") ? .rtsp : .http
                )
                store.add(camera)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 20) {
            Image(systemName: "camera.on.rectangle")
                .font(.system(size: 60))
                .foregroundColor(.secondary)
            Text("No Cameras")
                .font(.title2)
                .fontWeight(.semibold)
            Text("Tap + to add a camera manually,\nor use scan to discover cameras on your network.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            VStack(spacing: 12) {
                Button {
                    showingXiaomiLogin = true
                } label: {
                    Label("Xiaomi Cloud Login", systemImage: "cloud")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                HStack(spacing: 12) {
                    Button {
                        showingDiscovery = true
                    } label: {
                        Label("Scan Network", systemImage: "antenna.radiowaves.left.and.right")
                    }
                    .buttonStyle(.bordered)

                    Button {
                        showingAddCamera = true
                    } label: {
                        Label("Add Manually", systemImage: "pencil")
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
        .padding()
    }
}

struct CameraRowView: View {
    let camera: Camera

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "camera.fill")
                .foregroundColor(.accentColor)
                .font(.title2)
                .frame(width: 40, height: 40)
                .background(Color.accentColor.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(camera.name)
                    .font(.headline)
                Text("\(camera.ipAddress):\(camera.port)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text(camera.streamType.rawValue)
                    .font(.caption2)
                    .foregroundColor(.accentColor)
            }
        }
        .padding(.vertical, 4)
    }
}
