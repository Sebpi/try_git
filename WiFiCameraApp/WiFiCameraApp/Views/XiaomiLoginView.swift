import SwiftUI

struct XiaomiLoginView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var cloud = XiaomiCloudService()

    var onCameraAdded: (Camera) -> Void

    @State private var username = ""
    @State private var password = ""
    @State private var region = XiaomiCloudService.Region.europe
    @State private var showingDevices = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 10) {
                        Image(systemName: "cloud.fill")
                            .font(.system(size: 44))
                            .foregroundColor(.accentColor)
                        Text("Xiaomi Cloud")
                            .font(.title2).fontWeight(.semibold)
                        Text("Sign in with your Mi Home / Xiaomi account. The app will fetch your BW500's device token and try a direct local connection.")
                            .font(.caption)
                            .multilineTextAlignment(.center)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 8)
                    .listRowBackground(Color.clear)
                }

                Section("Account") {
                    TextField("Email or phone", text: $username)
                        .keyboardType(.emailAddress)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    SecureField("Password", text: $password)
                }

                Section {
                    Picker("Server Region", selection: $region) {
                        ForEach(XiaomiCloudService.Region.allCases, id: \.self) { r in
                            Text(r.displayName).tag(r)
                        }
                    }
                    Text("Select the region your Mi Home account was registered in. If outside China, try Europe first.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } header: {
                    Text("Region")
                }

                if let err = cloud.error {
                    Section {
                        Label(err, systemImage: "exclamationmark.triangle")
                            .foregroundColor(.red)
                            .font(.caption)
                    }
                }

                Section {
                    Button {
                        Task { await signIn() }
                    } label: {
                        HStack {
                            Spacer()
                            if cloud.isLoading {
                                ProgressView().padding(.trailing, 6)
                                Text("Signing in…")
                            } else {
                                Text("Sign In & Find Camera")
                                    .fontWeight(.semibold)
                            }
                            Spacer()
                        }
                    }
                    .disabled(username.isEmpty || password.isEmpty || cloud.isLoading)
                }

                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Label("Your password is sent directly to Xiaomi's servers, not stored by this app.", systemImage: "lock.shield")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        Label("If RTSP is not supported by your BW500, the app will show the device token so you can try manually.", systemImage: "info.circle")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    .listRowBackground(Color.clear)
                }
            }
            .navigationTitle("Xiaomi Cloud Login")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .sheet(isPresented: $showingDevices) {
                XiaomiDeviceListView(devices: cloud.cameras) { device in
                    let camera = cloud.toCamera(device)
                    onCameraAdded(camera)
                    dismiss()
                }
            }
        }
    }

    private func signIn() async {
        await MainActor.run {
            cloud.isLoading = true
            cloud.error = nil
        }
        do {
            try await cloud.login(username: username, password: password, region: region)
            try await cloud.fetchCameras()
            await MainActor.run {
                cloud.isLoading = false
                if cloud.cameras.isEmpty {
                    cloud.error = "No cameras found on your account. Make sure your BW500 is added to Mi Home and powered on."
                } else {
                    showingDevices = true
                }
            }
        } catch {
            await MainActor.run {
                cloud.isLoading = false
                cloud.error = error.localizedDescription
            }
        }
    }
}
