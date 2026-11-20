#!/usr/bin/env bash
set -euo pipefail
# Called inside apps/client by the emulator runner after the device has booted.
flutter doctor -v
flutter test integration_test/android_smoke_test.dart -d emulator-5554 --reporter expanded
adb -s emulator-5554 shell am force-stop com.cabinetsurvey.client.debug
flutter test integration_test/android_smoke_test.dart -d emulator-5554 --reporter expanded --dart-define=VERIFY_REOPEN=true
