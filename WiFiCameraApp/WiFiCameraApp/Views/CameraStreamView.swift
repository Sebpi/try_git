import SwiftUI
import AVFoundation

struct CameraStreamView: View {
    let camera: Camera
    @StateObject private var streamManager = RTSPStreamManager()
    @State private var snapshotImage: UIImage?
    @State private var showingSnapshot = false
    @State private var showingSettings = false
    @State private var savedToast = false
    @EnvironmentObject var store: CameraStore

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if let layer = streamManager.playerLayer {
                VideoLayerView(playerLayer: layer)
                    .ignoresSafeArea()
            } else {
                placeholderView
            }

            if streamManager.isLoading {
                ProgressView()
                    .progressViewStyle(.circular)
                    .tint(.white)
                    .scaleEffect(1.5)
            }

            if let error = streamManager.errorMessage {
                errorBanner(error)
            }

            if savedToast {
                toastView("Saved to Photos")
            }

            VStack {
                Spacer()
                controlBar
            }
        }
        .navigationTitle(camera.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    showingSettings = true
                } label: {
                    Image(systemName: "gearshape")
                }
                .tint(.white)
            }
        }
        .sheet(isPresented: $showingSettings) {
            AddCameraView(camera: camera) { updated in
                store.update(updated)
            }
        }
        .sheet(isPresented: $showingSnapshot) {
            if let image = snapshotImage {
                SnapshotPreviewView(image: image) { saved in
                    if saved { showSavedToast() }
                }
            }
        }
        .onAppear { connectStream() }
        .onDisappear { streamManager.disconnect() }
    }

    private func connectStream() {
        switch camera.streamType {
        case .rtsp:
            guard let url = camera.rtspURL else { return }
            streamManager.connect(to: url)
        case .http:
            guard let url = camera.snapshotURL else { return }
            streamManager.connect(to: url)
        }
    }

    private var controlBar: some View {
        HStack(spacing: 40) {
            Button {
                takeSnapshot()
            } label: {
                VStack(spacing: 4) {
                    Image(systemName: "camera")
                        .font(.title2)
                    Text("Snapshot").font(.caption2)
                }
            }
            .tint(.white)

            Button {
                if streamManager.isPlaying {
                    streamManager.disconnect()
                } else {
                    connectStream()
                }
            } label: {
                Image(systemName: streamManager.isPlaying ? "stop.circle.fill" : "play.circle.fill")
                    .font(.system(size: 50))
            }
            .tint(.white)

            Button {
                streamManager.disconnect()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    connectStream()
                }
            } label: {
                VStack(spacing: 4) {
                    Image(systemName: "arrow.clockwise")
                        .font(.title2)
                    Text("Refresh").font(.caption2)
                }
            }
            .tint(.white)
        }
        .padding(.vertical, 20)
        .padding(.horizontal, 40)
        .background(.ultraThinMaterial)
        .clipShape(Capsule())
        .padding(.bottom, 30)
    }

    private var placeholderView: some View {
        VStack(spacing: 16) {
            Image(systemName: "camera.on.rectangle")
                .font(.system(size: 60))
                .foregroundColor(.gray)
            Text("Connecting...")
                .foregroundColor(.gray)
        }
    }

    private func errorBanner(_ message: String) -> some View {
        VStack {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.yellow)
                Text(message)
                    .font(.footnote)
                    .foregroundColor(.white)
            }
            .padding(12)
            .background(Color.red.opacity(0.85))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .padding()
            Spacer()
        }
    }

    private func toastView(_ message: String) -> some View {
        VStack {
            Spacer()
            Text(message)
                .font(.subheadline)
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(Color.black.opacity(0.7))
                .clipShape(Capsule())
                .padding(.bottom, 120)
        }
    }

    private func takeSnapshot() {
        if camera.streamType == .rtsp {
            streamManager.snapshot { image in
                snapshotImage = image
                if image != nil { showingSnapshot = true }
            }
        } else if let url = camera.snapshotURL {
            SnapshotService.fetch(from: url, username: camera.username, password: camera.password) { image, _ in
                snapshotImage = image
                if image != nil { showingSnapshot = true }
            }
        }
    }

    private func showSavedToast() {
        savedToast = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            savedToast = false
        }
    }
}

struct VideoLayerView: UIViewRepresentable {
    let playerLayer: AVPlayerLayer

    func makeUIView(context: Context) -> UIView {
        let view = PlayerView()
        view.backgroundColor = .black
        view.layer.addSublayer(playerLayer)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        playerLayer.frame = uiView.bounds
    }

    class PlayerView: UIView {
        override func layoutSubviews() {
            super.layoutSubviews()
            layer.sublayers?.first?.frame = bounds
        }
    }
}
