import SwiftUI

struct SnapshotPreviewView: View {
    @Environment(\.dismiss) private var dismiss
    let image: UIImage
    var onSave: (Bool) -> Void

    var body: some View {
        NavigationStack {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .background(Color.black)
                .ignoresSafeArea()
                .navigationTitle("Snapshot")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { dismiss() }
                    }
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button {
                            SnapshotService.saveToPhotos(image) { success in
                                onSave(success)
                                dismiss()
                            }
                        } label: {
                            Label("Save", systemImage: "square.and.arrow.down")
                        }
                    }
                }
        }
    }
}
