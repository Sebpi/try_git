import Foundation
import Combine

class CameraStore: ObservableObject {
    @Published var cameras: [Camera] = []

    private let saveKey = "saved_cameras"

    init() {
        load()
    }

    func add(_ camera: Camera) {
        cameras.append(camera)
        save()
    }

    func update(_ camera: Camera) {
        guard let index = cameras.firstIndex(where: { $0.id == camera.id }) else { return }
        cameras[index] = camera
        save()
    }

    func delete(at offsets: IndexSet) {
        cameras.remove(atOffsets: offsets)
        save()
    }

    private func save() {
        if let data = try? JSONEncoder().encode(cameras) {
            UserDefaults.standard.set(data, forKey: saveKey)
        }
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: saveKey),
              let decoded = try? JSONDecoder().decode([Camera].self, from: data) else { return }
        cameras = decoded
    }
}
