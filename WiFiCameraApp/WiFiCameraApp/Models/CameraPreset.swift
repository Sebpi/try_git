import Foundation

struct CameraPreset {
    let brand: String
    let model: String
    let port: Int
    let streamPath: String
    let subStreamPath: String
    let snapshotPath: String
    let defaultUsername: String
    let streamType: Camera.StreamType
    let setupNote: String

    static let all: [CameraPreset] = [
        CameraPreset(
            brand: "Xiaomi",
            model: "BW500 / Outdoor Series",
            port: 554,
            streamPath: "/live",
            subStreamPath: "/live/ch00_1",
            snapshotPath: "/snapshot",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Enable RTSP in Mi Home app: tap the camera → Settings (⚙) → Advanced → RTSP. The password is your Mi Home account password. Find the camera IP in your router's device list or Mi Home settings."
        ),
        CameraPreset(
            brand: "Xiaomi",
            model: "Indoor (Yi / Dafang)",
            port: 554,
            streamPath: "/ch0_0.264",
            subStreamPath: "/ch0_1.264",
            snapshotPath: "/snapshot",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Requires custom firmware (yi-hack or Dafang-Hacks) for RTSP support. Default login: admin / (no password)."
        ),
        CameraPreset(
            brand: "Reolink",
            model: "RLC / E1 Series",
            port: 554,
            streamPath: "/h264Preview_01_main",
            subStreamPath: "/h264Preview_01_sub",
            snapshotPath: "/cgi-bin/api.cgi?cmd=Snap&channel=0",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Default username: admin. Password is set during initial setup in the Reolink app."
        ),
        CameraPreset(
            brand: "Hikvision",
            model: "DS Series",
            port: 554,
            streamPath: "/Streaming/Channels/101",
            subStreamPath: "/Streaming/Channels/102",
            snapshotPath: "/onvif/snapshot/channels/1",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Default username: admin. Default password: 12345. Change after first login."
        ),
        CameraPreset(
            brand: "Dahua",
            model: "IPC Series",
            port: 554,
            streamPath: "/cam/realmonitor?channel=1&subtype=0",
            subStreamPath: "/cam/realmonitor?channel=1&subtype=1",
            snapshotPath: "/cgi-bin/snapshot.cgi",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Default username: admin. Password is set during first-time setup."
        ),
        CameraPreset(
            brand: "TP-Link Tapo",
            model: "C200 / C310 Series",
            port: 554,
            streamPath: "/stream1",
            subStreamPath: "/stream2",
            snapshotPath: "/snapshot",
            defaultUsername: "admin",
            streamType: .rtsp,
            setupNote: "Username and password are set in the Tapo app under camera Settings → Advanced → RTSP."
        ),
        CameraPreset(
            brand: "Generic / Other",
            model: "Custom settings",
            port: 554,
            streamPath: "/stream",
            subStreamPath: "/stream2",
            snapshotPath: "/snapshot",
            defaultUsername: "",
            streamType: .rtsp,
            setupNote: "Enter your camera's IP address, port, and stream path manually."
        ),
    ]

    static var xiaomiBW500: CameraPreset { all[0] }
}
