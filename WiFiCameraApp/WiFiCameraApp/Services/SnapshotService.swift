import UIKit
import Photos

class SnapshotService {
    static func fetch(from url: URL, username: String, password: String, completion: @escaping (UIImage?, Error?) -> Void) {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10)
        if !username.isEmpty {
            let credentials = "\(username):\(password)"
            if let data = credentials.data(using: .utf8) {
                request.setValue("Basic \(data.base64EncodedString())", forHTTPHeaderField: "Authorization")
            }
        }
        URLSession.shared.dataTask(with: request) { data, _, error in
            let image = data.flatMap { UIImage(data: $0) }
            DispatchQueue.main.async { completion(image, error) }
        }.resume()
    }

    static func saveToPhotos(_ image: UIImage, completion: @escaping (Bool) -> Void) {
        PHPhotoLibrary.requestAuthorization { status in
            guard status == .authorized else {
                DispatchQueue.main.async { completion(false) }
                return
            }
            PHPhotoLibrary.shared().performChanges({
                PHAssetChangeRequest.creationRequestForAsset(from: image)
            }) { success, _ in
                DispatchQueue.main.async { completion(success) }
            }
        }
    }
}
