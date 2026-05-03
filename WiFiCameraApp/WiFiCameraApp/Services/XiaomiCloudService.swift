import Foundation
import CryptoKit

enum XiaomiError: LocalizedError {
    case authFailed(String)
    case deviceFetchFailed(String)
    case noServiceToken

    var errorDescription: String? {
        switch self {
        case .authFailed(let msg): return "Login failed: \(msg)"
        case .deviceFetchFailed(let msg): return "Could not fetch devices: \(msg)"
        case .noServiceToken: return "Could not get session token from Xiaomi"
        }
    }
}

struct XiaomiDevice: Identifiable {
    let id = UUID()
    let did: String
    let name: String
    let localIP: String
    let token: String
    let model: String
    let isOnline: Bool

    var isCamera: Bool {
        let m = model.lowercased()
        return m.contains("camera") || m.contains("cam") ||
               m.contains("cw") || m.contains("bw") ||
               m.contains("rcam") || m.contains("mjsxj") ||
               m.contains("isa.")
    }
}

class XiaomiCloudService: ObservableObject {

    enum Region: String, CaseIterable {
        case china = "cn"
        case europe = "de"
        case us = "us"
        case russia = "ru"
        case taiwan = "tw"
        case singapore = "sg"
        case india = "in"

        var displayName: String {
            switch self {
            case .china:     return "China"
            case .europe:    return "Europe"
            case .us:        return "United States"
            case .russia:    return "Russia"
            case .taiwan:    return "Taiwan"
            case .singapore: return "Singapore"
            case .india:     return "India"
            }
        }

        var apiBase: String {
            self == .china ? "https://api.io.mi.com/app" : "https://\(rawValue).api.io.mi.com/app"
        }
    }

    @Published var isAuthenticated = false
    @Published var cameras: [XiaomiDevice] = []
    @Published var isLoading = false
    @Published var error: String?

    private var userId = ""
    private var serviceToken = ""
    private var ssecurity = ""
    private var region: Region = .europe

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.httpCookieStorage = .shared
        config.httpShouldSetCookies = true
        config.httpCookieAcceptPolicy = .always
        return URLSession(configuration: config)
    }()

    // MARK: - Public API

    func login(username: String, password: String, region: Region) async throws {
        self.region = region

        // 1. GET login page → extract _sign, qs, callback
        let pageURL = URL(string: "https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true")!
        var pageReq = URLRequest(url: pageURL)
        pageReq.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", forHTTPHeaderField: "User-Agent")
        let (pageData, _) = try await session.data(for: pageReq)
        let pageJSON = try parseResponse(pageData)

        guard let sign = pageJSON["_sign"] as? String else {
            throw XiaomiError.authFailed("Unexpected login page response")
        }
        let qs       = pageJSON["qs"]       as? String ?? ""
        let callback = pageJSON["callback"] as? String ?? ""

        // 2. POST credentials
        let passwordHash = md5(password).uppercased()
        var bodyItems: [URLQueryItem] = [
            .init(name: "sid",    value: "xiaomiio"),
            .init(name: "hash",   value: passwordHash),
            .init(name: "callback", value: callback),
            .init(name: "qs",     value: qs),
            .init(name: "user",   value: username),
            .init(name: "_sign",  value: sign),
            .init(name: "_json",  value: "true"),
        ]
        var bodyComps = URLComponents()
        bodyComps.queryItems = bodyItems
        let bodyString = bodyComps.query ?? ""

        let authURL = URL(string: "https://account.xiaomi.com/pass/serviceLoginAuth2")!
        var authReq = URLRequest(url: authURL)
        authReq.httpMethod = "POST"
        authReq.httpBody = bodyString.data(using: .utf8)
        authReq.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        authReq.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", forHTTPHeaderField: "User-Agent")

        let (authData, _) = try await session.data(for: authReq)
        let authJSON = try parseResponse(authData)

        let code = authJSON["code"] as? Int ?? -1
        if code != 0 {
            let desc = authJSON["desc"] as? String ?? "Invalid credentials (code \(code))"
            throw XiaomiError.authFailed(desc)
        }

        guard let location = authJSON["location"] as? String,
              let ss       = authJSON["ssecurity"] as? String else {
            throw XiaomiError.authFailed("Missing auth fields in response")
        }

        if let uid = authJSON["userId"] as? Int        { userId = "\(uid)" }
        else if let uid = authJSON["userId"] as? String { userId = uid }
        ssecurity = ss

        // 3. Follow location URL to pick up serviceToken cookie
        guard let locURL = URL(string: location) else { throw XiaomiError.noServiceToken }
        _ = try await session.data(from: locURL)

        let cookies = HTTPCookieStorage.shared.cookies(for: locURL) ?? []
        serviceToken = cookies.first(where: { $0.name == "serviceToken" })?.value ?? ""

        if serviceToken.isEmpty { throw XiaomiError.noServiceToken }

        await MainActor.run { isAuthenticated = true }
    }

    func fetchCameras() async throws {
        let path = "/home/device_list"
        let dataDict: [String: Any] = [
            "getVirtualModel": false,
            "getHuamiDevices": 1,
            "get_split_device": false,
            "support_smart_home": true,
        ]
        let dataJSON = String(data: try JSONSerialization.data(withJSONObject: dataDict), encoding: .utf8) ?? "{}"

        let nonce    = makeNonce()
        let sNonce   = signedNonce(nonce: nonce)
        let sig      = signature(path: path, data: dataJSON, signedNonce: sNonce)

        var bodyComps = URLComponents()
        bodyComps.queryItems = [
            .init(name: "data",      value: dataJSON),
            .init(name: "_nonce",    value: nonce),
            .init(name: "signature", value: sig),
        ]
        let body = bodyComps.query ?? ""

        var req = URLRequest(url: URL(string: region.apiBase + path)!)
        req.httpMethod = "POST"
        req.httpBody = body.data(using: .utf8)
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        req.setValue("PROTOCAL-HTTP2", forHTTPHeaderField: "x-xiaomi-protocal-flag-cli")
        req.setValue("userId=\(userId); serviceToken=\(serviceToken); locale=en_GB",
                     forHTTPHeaderField: "Cookie")
        req.setValue("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", forHTTPHeaderField: "User-Agent")

        let (data, _) = try await session.data(for: req)

        guard let json    = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let result  = json["result"] as? [String: Any],
              let list    = result["list"] as? [[String: Any]] else {
            let raw = String(data: data, encoding: .utf8) ?? ""
            throw XiaomiError.deviceFetchFailed("Unexpected response: \(raw.prefix(300))")
        }

        let found: [XiaomiDevice] = list.compactMap { d in
            guard let did   = d["did"]   as? String,
                  let name  = d["name"]  as? String,
                  let model = d["model"] as? String,
                  let token = d["token"] as? String else { return nil }
            return XiaomiDevice(
                did: did, name: name,
                localIP: d["localip"] as? String ?? "",
                token: token, model: model,
                isOnline: d["isOnline"] as? Bool ?? false
            )
        }

        await MainActor.run { cameras = found }
    }

    func toCamera(_ device: XiaomiDevice) -> Camera {
        Camera(
            name: device.name,
            ipAddress: device.localIP,
            port: 554,
            streamPath: "/live",
            snapshotPath: "/snapshot",
            username: "admin",
            password: device.token,
            streamType: .rtsp
        )
    }

    // MARK: - Crypto helpers

    private func makeNonce() -> String {
        var bytes = [UInt8](repeating: 0, count: 8)
        _ = SecRandomCopyBytes(kSecRandomDefault, 8, &bytes)
        let minutes = UInt32(Date().timeIntervalSince1970 / 60).bigEndian
        var all = bytes
        withUnsafeBytes(of: minutes) { all.append(contentsOf: $0) }
        return Data(all).base64EncodedString()
    }

    private func signedNonce(nonce: String) -> String {
        guard let ssData = Data(base64Encoded: ssecurity),
              let nData  = Data(base64Encoded: nonce) else { return "" }
        return Data(SHA256.hash(data: ssData + nData)).base64EncodedString()
    }

    private func signature(path: String, data: String, signedNonce: String) -> String {
        let msg = "POST\n\(path)\ndata=\(data)\n\(signedNonce)"
        guard let keyData = Data(base64Encoded: signedNonce),
              let msgData = msg.data(using: .utf8) else { return "" }
        let mac = HMAC<SHA256>.authenticationCode(for: msgData, using: SymmetricKey(data: keyData))
        return Data(mac).base64EncodedString()
    }

    private func md5(_ string: String) -> String {
        let hash = Insecure.MD5.hash(data: Data(string.utf8))
        return hash.map { String(format: "%02x", $0) }.joined()
    }

    private func parseResponse(_ data: Data) throws -> [String: Any] {
        var str = String(data: data, encoding: .utf8) ?? ""
        if str.hasPrefix("&&&START&&&") { str = String(str.dropFirst(11)) }
        guard let jsonData = str.data(using: .utf8),
              let json = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any] else {
            throw XiaomiError.authFailed("Could not parse server response")
        }
        return json
    }
}
