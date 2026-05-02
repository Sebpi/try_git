import SwiftUI

struct ContentView: View {
    @StateObject private var store = CameraStore()

    var body: some View {
        NavigationStack {
            CameraListView()
                .environmentObject(store)
        }
    }
}
