#!/usr/bin/env bash
set -euo pipefail
# Called inside apps/client by the emulator runner after the device has booted.
# Flutter's integration-test harness uninstalls the app at the end of *each*
# invocation, which erases Android Keystore keys and all data with backup disabled.
# Use an isolated SDK view whose adb wrapper suppresses only this fixture app's
# uninstall. Actual force-stop and reinstall still go through the real adb.
REAL_ADB="$ANDROID_HOME/platform-tools/adb"
SDK_VIEW="$RUNNER_TEMP/android-sdk-persistence-test"
mkdir -p "$SDK_VIEW/platform-tools"
for entry in "$ANDROID_HOME"/*; do
  [[ "$(basename "$entry")" == platform-tools ]] || ln -s "$entry" "$SDK_VIEW/$(basename "$entry")"
done
for entry in "$ANDROID_HOME/platform-tools"/*; do
  [[ "$(basename "$entry")" == adb ]] || ln -s "$entry" "$SDK_VIEW/platform-tools/$(basename "$entry")"
done
export CABINET_REAL_ADB="$REAL_ADB"
cat > "$SDK_VIEW/platform-tools/adb" <<'WRAPPER'
#!/usr/bin/env bash
for arg in "$@"; do
  if [[ "$arg" == uninstall ]]; then
    for package in "$@"; do
      if [[ "$package" == com.cabinetsurvey.client || "$package" == com.cabinetsurvey.client.debug ]]; then
        echo 'Success (fixture installation retained for process-restart test)'
        exit 0
      fi
    done
  fi
done
exec "$CABINET_REAL_ADB" "$@"
WRAPPER
chmod +x "$SDK_VIEW/platform-tools/adb"
# Ensure every run starts and ends with an empty disposable installation.
"$REAL_ADB" -s emulator-5554 uninstall com.cabinetsurvey.client.debug >/dev/null 2>&1 || true
trap '"$REAL_ADB" -s emulator-5554 uninstall com.cabinetsurvey.client.debug >/dev/null 2>&1 || true' EXIT
export ANDROID_HOME="$SDK_VIEW" ANDROID_SDK_ROOT="$SDK_VIEW"
flutter doctor -v
flutter test integration_test/local_encryption_test.dart -d emulator-5554 --reporter expanded
flutter test integration_test/android_smoke_test.dart -d emulator-5554 --reporter expanded
"$REAL_ADB" -s emulator-5554 shell am force-stop com.cabinetsurvey.client.debug
flutter test integration_test/android_smoke_test.dart -d emulator-5554 --reporter expanded --dart-define=VERIFY_REOPEN=true
