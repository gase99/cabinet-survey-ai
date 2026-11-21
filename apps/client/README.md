# Android Flutter client — pre-release

Android only. Native Gradle/Kotlin sources, manifest, icons and wrapper are committed.
Do **not** run `flutter create --platforms=android,web` or a web bootstrap.

## Toolchain and local run
Use Flutter **3.35.7**, Java **21**, Android SDK Platform 36, Build Tools, Platform Tools
and NDK **27.0.12077973** (Flutter's pinned NDK). Gradle 8.12 / AGP 8.9.1 / Kotlin 2.1.0.
Minimum Android API 24 (7.0); target/compile API 36. Run `flutter doctor -v`.

```sh
cd apps/client
cp config/api.example.json config/api.json
# Edit API_BASE_URL. Emulator development: http://10.0.2.2:8000/api/v1/
# Physical device/release: your actual HTTPS host, https://HOST/api/v1/
flutter pub get
flutter analyze --no-fatal-infos
flutter test
flutter run -d ANDROID_DEVICE_ID --dart-define-from-file=config/api.json
```
The configured URL is compile-time public routing information, **not a secret**.
Release code rejects HTTP, relative URLs and credentials/query in the API URL.
Debug network policy permits HTTP only for emulator/ADB-local development hosts.
The default debug URL is `http://10.0.2.2:8000/api/v1/`; this is not a phone loopback URL.

## Build and signing
From repository root:
```sh
bash scripts/build-android.sh debug
# Configure owner signing first; see docs/android-delivery-fa.md.
bash scripts/build-android.sh release
```
Debug application ID is `com.cabinetsurvey.client.debug`, so it can coexist with release.
Release is `com.cabinetsurvey.client`. Copy `android/key.properties.example` to private
`android/key.properties`, or set `ANDROID_KEYSTORE_PATH`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. Never commit the keystore or passwords.
No owner key means no distributable release signing; release never silently falls back
to debug signing. CI uses a disposable key solely to test AAB compilation, with an
invalid API host; its artifact is **not for publication or connected production use**.

## Android integration
- Survey data and photo BLOBs use SQLCipher via `sqflite_sqlcipher`; VM-only tests use
  `sqflite_common_ffi` and do not verify encryption. The database password is random.
  Android Keystore holds a non-exportable AES-GCM wrapping key; only the wrapped password
  and IV are written to app-private `noBackupFilesDir`, never SharedPreferences. Refresh
  tokens continue to use their separate Android secure-storage implementation.
- On the first upgrade from plaintext SQLite, the app shows counts of pending/conflicted
  operations, device-local records and stored photos. With explicit confirmation it deletes
  the old database and `-wal`, `-shm`, and `-journal`, creates an encrypted database and
  attempts a server re-sync after sign-in. Unreadable counts are shown as unknown. **All
  unsynced changes, device-local data and photos are permanently lost**: photo sync is not
  implemented. Cancel leaves the old data untouched. Failed sync remains marked for retry.
- If SQLCipher reports "not a database" / "file is encrypted", or the wrapped key (or its
  Keystore wrapping key) is missing (`WRAPPED_KEY_MISSING`), the app immediately offers the
  confirmed reset: wipe the encrypted cache, create a new key/database, re-sync server
  data after sign-in. A generic failure (SQLCipher `open_failed`, other Keystore errors)
  first shows only **Try again**; the destructive reset is offered only after a retry has
  also failed. No data is deleted without explicit confirmation in any case.
- Backup and device-transfer rules exclude app data. Uninstall, device replacement, loss
  of the Keystore key, and unsupported restores make device-only data unrecoverable. Keep
  server sync current; photos are local-only and require a separate owner-managed copy.
- Picker temporary files in the app cache are cleared after success, failure or cancellation
  and on startup. Files created by external camera/gallery apps and user originals are outside
  this app's control. File deletion is not guaranteed physical secure erasure on flash storage.
- **Not covered by local encryption (plaintext on the device):** PDF/PNG exports saved
  through the document picker (the user-chosen destination, e.g. Downloads or a cloud
  folder) and any copies kept by external camera/gallery apps (e.g. the original photo in
  the device gallery). These files are outside the app's SQLCipher database and are not
  deleted by the app's reset; protect or delete them with the device's own tools.
- Camera/gallery use the system picker; no broad storage or CAMERA manifest permission.
- PDF/PNG saving uses `ACTION_CREATE_DOCUMENT`, so the user chooses the destination.
  Cancellation is not reported as a successful save. No legacy external-storage permission.
- Release blocks cleartext HTTP and Android cloud backup of the local survey database.
- Persian RTL/English; explicit integer-mm entry and human approval remain mandatory.

## Tests
```sh
flutter test
cd android && ./gradlew :app:testDebugUnitTest :app:lintDebug
cd ..
python ../../scripts/run-client-acceptance.py --native  # disposable real FastAPI
flutter test integration_test/android_smoke_test.dart -d ANDROID_DEVICE_ID
```
VM tests are not Android-device tests. CI additionally runs the integration test on an
API-35 emulator, force-stops the process, and reopens it to verify real local persistence.
Physical camera, document-picker interaction and print/device acceptance still need a device.

## Existing product limitations
Guest-to-account migration, background/photo sync, deletion tombstones, full sketch
correction/OCR/voice, persistent undo and drag/snapping editor remain incomplete.
Server export currently selects the first room; Persian PDF shaping and physical print
scale are not accepted. AI candidates are not automatically imported as measurements.
See the Persian delivery report; source compilation does not erase these limitations.
