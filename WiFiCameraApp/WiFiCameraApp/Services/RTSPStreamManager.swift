import AVFoundation
import UIKit
import Combine

class RTSPStreamManager: NSObject, ObservableObject {
    @Published var playerLayer: AVPlayerLayer?
    @Published var isPlaying = false
    @Published var isLoading = false
    @Published var errorMessage: String?

    private var player: AVPlayer?
    private var playerItem: AVPlayerItem?
    private var statusObserver: NSKeyValueObservation?
    private var bufferObserver: NSKeyValueObservation?

    func connect(to url: URL) {
        disconnect()
        isLoading = true
        errorMessage = nil

        let asset = AVURLAsset(url: url, options: [
            "AVURLAssetHTTPHeaderFieldsKey": authHeaders(for: url)
        ])
        playerItem = AVPlayerItem(asset: asset)
        player = AVPlayer(playerItem: playerItem)

        let layer = AVPlayerLayer(player: player)
        layer.videoGravity = .resizeAspect
        playerLayer = layer

        statusObserver = playerItem?.observe(\.status, options: [.new]) { [weak self] item, _ in
            DispatchQueue.main.async {
                switch item.status {
                case .readyToPlay:
                    self?.isLoading = false
                    self?.isPlaying = true
                    self?.player?.play()
                case .failed:
                    self?.isLoading = false
                    self?.errorMessage = item.error?.localizedDescription ?? "Stream failed"
                default:
                    break
                }
            }
        }

        bufferObserver = playerItem?.observe(\.isPlaybackBufferEmpty, options: [.new]) { [weak self] item, _ in
            DispatchQueue.main.async {
                if item.isPlaybackBufferEmpty && self?.isPlaying == true {
                    self?.isLoading = true
                }
            }
        }
    }

    func disconnect() {
        player?.pause()
        statusObserver?.invalidate()
        bufferObserver?.invalidate()
        player = nil
        playerItem = nil
        playerLayer = nil
        isPlaying = false
        isLoading = false
        errorMessage = nil
    }

    func snapshot(completion: @escaping (UIImage?) -> Void) {
        guard let playerItem = playerItem else { completion(nil); return }
        let generator = AVAssetImageGenerator(asset: playerItem.asset)
        generator.appliesPreferredTrackTransform = true
        let time = playerItem.currentTime()
        generator.generateCGImagesAsynchronously(forTimes: [NSValue(time: time)]) { _, image, _, _, _ in
            let uiImage = image.map { UIImage(cgImage: $0) }
            DispatchQueue.main.async { completion(uiImage) }
        }
    }

    private func authHeaders(for url: URL) -> [String: String] {
        guard let user = url.user, let pass = url.password,
              !user.isEmpty else { return [:] }
        let credentials = "\(user):\(pass)"
        guard let data = credentials.data(using: .utf8) else { return [:] }
        return ["Authorization": "Basic \(data.base64EncodedString())"]
    }
}
