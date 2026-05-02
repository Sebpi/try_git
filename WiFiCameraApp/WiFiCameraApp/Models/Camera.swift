import Foundation

struct Camera: Identifiable, Codable, Equatable {
    var id: UUID = UUID()
    var name: String
    var ipAddress: String
    var port: Int
    var streamPath: String
    var snapshotPath: String
    var username: String
    var password: String
    var streamType: StreamType

    enum StreamType: String, Codable, CaseIterable {
        case rtsp = "RTSP"
        case http = "HTTP MJPEG"
    }

    var rtspURL: URL? {
        var components = URLComponents()
        components.scheme = "rtsp"
        if !username.isEmpty {
            components.user = username
            components.password = password
        }
        components.host = ipAddress
        components.port = port
        components.path = streamPath.hasPrefix("/") ? streamPath : "/" + streamPath
        return components.url
    }

    var snapshotURL: URL? {
        var components = URLComponents()
        components.scheme = "http"
        components.host = ipAddress
        components.port = port
        components.path = snapshotPath.hasPrefix("/") ? snapshotPath : "/" + snapshotPath
        return components.url
    }

    static let example = Camera(
        name: "Front Door",
        ipAddress: "192.168.1.100",
        port: 554,
        streamPath: "/stream",
        snapshotPath: "/snapshot",
        username: "",
        password: "",
        streamType: .rtsp
    )
}
