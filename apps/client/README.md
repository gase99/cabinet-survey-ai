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
- `sqflite` uses native Android storage; the browser FFI/WASM dependency is removed.
- Refresh tokens use Android secure storage. Survey SQLite/photos are **not encrypted**.
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
