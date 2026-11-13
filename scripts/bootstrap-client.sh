#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/client"
# Reproducible platform generation; existing application Dart sources are preserved.
flutter create --project-name cabinet_survey_ai --org com.cabinetsurvey --platforms=android,web .
flutter pub get
dart run sqflite_common_ffi_web:setup
python3 - <<'PY'
from pathlib import Path
p = Path('android/app/src/main/AndroidManifest.xml')
s = p.read_text()
if 'android.permission.INTERNET' not in s:
    s = s.replace('<application', '<uses-permission android:name="android.permission.INTERNET"/>\n    <application', 1)
p.write_text(s)
PY
