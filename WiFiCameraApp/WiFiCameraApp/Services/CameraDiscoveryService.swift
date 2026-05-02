import Foundation
import Network
import Combine

struct DiscoveredCamera: Identifiable {
    let id = UUID()
    let name: String
    let host: String
    let port: Int
    let type: String
}

class CameraDiscoveryService: NSObject, ObservableObject {
    @Published var discoveredCameras: [DiscoveredCamera] = []
    @Published var isScanning = false

    private var browser: NWBrowser?
    private var browsers: [NWBrowser] = []

    func startDiscovery() {
        discoveredCameras = []
        isScanning = true
        browsers.forEach { $0.cancel() }
        browsers = []

        let serviceTypes = ["_rtsp._tcp", "_http._tcp", "_onvif._tcp", "_camera._tcp"]
        for serviceType in serviceTypes {
            let params = NWParameters()
            let browser = NWBrowser(for: .bonjourWithTXTRecord(type: serviceType, domain: "local."), using: params)
            browser.stateUpdateHandler = { [weak self] state in
                if case .failed = state {
                    DispatchQueue.main.async { self?.isScanning = false }
                }
            }
            browser.browseResultsChangedHandler = { [weak self] results, _ in
                for result in results {
                    if case let .service(name, type, domain, _) = result.endpoint {
                        self?.resolve(name: name, type: type, domain: domain)
                    }
                }
            }
            browser.start(queue: .global(qos: .userInitiated))
            browsers.append(browser)
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 10) { [weak self] in
            self?.stopDiscovery()
        }
    }

    private func resolve(name: String, type: String, domain: String) {
        let connection = NWConnection(
            to: .service(name: name, type: type, domain: domain, interface: nil),
            using: .tcp
        )
        connection.stateUpdateHandler = { [weak self] state in
            if case .ready = state {
                if let endpoint = connection.currentPath?.remoteEndpoint,
                   case let .hostPort(host, port) = endpoint {
                    let hostStr = "\(host)"
                    let portInt = Int(port.rawValue)
                    let discovered = DiscoveredCamera(
                        name: name,
                        host: hostStr,
                        port: portInt,
                        type: type
                    )
                    DispatchQueue.main.async {
                        if let self = self,
                           !self.discoveredCameras.contains(where: { $0.host == hostStr && $0.port == portInt }) {
                            self.discoveredCameras.append(discovered)
                        }
                    }
                }
                connection.cancel()
            }
        }
        connection.start(queue: .global(qos: .userInitiated))
    }

    func stopDiscovery() {
        browsers.forEach { $0.cancel() }
        browsers = []
        DispatchQueue.main.async { self.isScanning = false }
    }
}
