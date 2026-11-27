#!/usr/bin/env bash
set -euo pipefail
# Called inside apps/client by the emulator runner after the device has booted.
# Flutter's integration-test harness uninstalls the app at the end of *each*
# invocation, which erases Android Keystore keys and all data with backup disabled.
# Use an isolated SDK view whose adb wrapper suppresses only this fixture app's
# uninstall. Actual force-stop and reinstall still go through the real adb.
REAL_ADB="$ANDROID_HOME/platform-tools/adb"
SDK_VIEW="$RUNNER_TEMP/android-sdk-persistence-test"
DIAGNOSTICS="$RUNNER_TEMP/emulator-diagnostics"
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

# Capture before the emulator runner tears down the device, and before uninstall.
# Collection failures must not replace the test's original exit status.
capture_failure() {
  local label="$1" dir="$DIAGNOSTICS/$1"
  mkdir -p "$dir"
  echo "Collecting emulator diagnostics: $label"
  for log in "$RUNNER_TEMP"/smoke-*-attempt-*.txt; do
    if [[ -f "$log" ]]; then cp "$log" "$dir/"; fi
  done
  timeout 20s "$REAL_ADB" -s emulator-5554 logcat -d -v threadtime > "$dir/logcat.txt" 2>&1 || echo 'logcat unavailable' >> "$dir/logcat.txt"
  if ! timeout 20s "$REAL_ADB" -s emulator-5554 exec-out screencap -p > "$dir/screenshot.png" || [[ ! -s "$dir/screenshot.png" ]]; then
    rm -f "$dir/screenshot.png"
    echo 'screenshot unavailable' > "$dir/screenshot-unavailable.txt"
  fi
  echo '--- adb shell dumpsys activity (including crash/process information) ---'
  timeout 20s "$REAL_ADB" -s emulator-5554 shell dumpsys activity > "$dir/dumpsys-activity.txt" 2>&1 || echo 'dumpsys activity unavailable' >> "$dir/dumpsys-activity.txt"
  cat "$dir/dumpsys-activity.txt"
}
cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then capture_failure final || true; fi
  "$REAL_ADB" -s emulator-5554 uninstall com.cabinetsurvey.client.debug >/dev/null 2>&1 || true
  exit "$status"
}
# Ensure every run starts and ends with an empty disposable installation.
"$REAL_ADB" -s emulator-5554 uninstall com.cabinetsurvey.client.debug >/dev/null 2>&1 || true
trap cleanup EXIT
export ANDROID_HOME="$SDK_VIEW" ANDROID_SDK_ROOT="$SDK_VIEW"
flutter doctor -v
flutter test integration_test/local_encryption_test.dart -d emulator-5554 --reporter expanded

# One bounded retry total, only if the harness failed before the named test began.
# A real test failure must never be hidden by a retry, and reopen uses the same DB.
retried=0
run_smoke() {
  local phase="$1" attempt=1 rc log
  shift
  while :; do
    log="$RUNNER_TEMP/smoke-$phase-attempt-$attempt.txt"
    echo "Smoke $phase attempt $attempt (maximum 300 seconds)"
    if timeout --kill-after=10s 300s flutter test integration_test/android_smoke_test.dart -d emulator-5554 --reporter expanded "$@" 2>&1 | tee "$log"; then
      return 0
    else
      local statuses=("${PIPESTATUS[@]}")
      rc=${statuses[0]}
      if (( rc == 0 )); then return "${statuses[1]}"; fi
    fi
    if (( retried == 0 )) &&
       ! grep -Fq 'Android Persian RTL offline capture and process restart' "$log" &&
       grep -Fq 'loading ' "$log" &&
       { (( rc == 124 )) || grep -Fq 'Failed to start Dart Development Service' "$log" || grep -Fq 'Test timed out after 12 minutes' "$log"; }; then
      capture_failure "$phase-attempt-$attempt" || true
      echo 'Harness did not start the smoke test; retrying once after force-stop and adb forward cleanup.'
      "$REAL_ADB" -s emulator-5554 shell am force-stop com.cabinetsurvey.client.debug
      "$REAL_ADB" -s emulator-5554 forward --remove-all
      retried=1
      attempt=$((attempt + 1))
    else
      return "$rc"
    fi
  done
}
run_smoke capture
"$REAL_ADB" -s emulator-5554 shell am force-stop com.cabinetsurvey.client.debug
run_smoke reopen --dart-define=VERIFY_REOPEN=true
