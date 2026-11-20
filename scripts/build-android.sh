#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KIND="${1:-debug}"
CONFIG="${2:-$ROOT/apps/client/config/api.json}"
case "$KIND" in debug|release) ;; *) echo 'Usage: build-android.sh [debug|release] [api-json]' >&2; exit 2;; esac
[[ -f "$CONFIG" ]] || { echo 'Copy apps/client/config/api.example.json to api.json and set your API host.' >&2; exit 2; }
python3 - "$CONFIG" "$KIND" <<'PY'
import json,sys,urllib.parse
p=urllib.parse.urlsplit(json.load(open(sys.argv[1]))['API_BASE_URL'])
if not p.hostname or p.scheme not in {'http','https'} or (sys.argv[2]=='release' and p.scheme!='https') or not p.path.endswith('/api/v1/') or p.username or p.query or p.fragment:
 raise SystemExit('Invalid API URL. Release requires HTTPS and /api/v1/; debug may use emulator HTTP.')
if sys.argv[2]=='release' and (p.hostname.endswith('.example') or p.hostname.endswith('.invalid')):
 raise SystemExit('Replace the example API host before a connected release build.')
PY
cd "$ROOT/apps/client"
flutter pub get
if [[ "$KIND" == debug ]]; then
  flutter build apk --debug --dart-define-from-file="$CONFIG"
  echo 'APK: build/app/outputs/flutter-apk/app-debug.apk'
else
  python3 - "$ROOT" <<'CHECK'
import os,sys
from pathlib import Path
root=Path(sys.argv[1])/'apps/client/android'
values={}
if (root/'key.properties').is_file():
 for line in (root/'key.properties').read_text().splitlines():
  if '=' in line and not line.lstrip().startswith('#'):
   key,value=line.split('=',1);values[key.strip()]=value.strip()
for key,env in [('storeFile','ANDROID_KEYSTORE_PATH'),('storePassword','ANDROID_KEYSTORE_PASSWORD'),('keyAlias','ANDROID_KEY_ALIAS'),('keyPassword','ANDROID_KEY_PASSWORD')]:
 if not os.environ.get(env) and not values.get(key):raise SystemExit('Owner signing is required. Configure private key.properties or ANDROID_KEYSTORE_* environment variables.')
store=os.environ.get('ANDROID_KEYSTORE_PATH') or values['storeFile']
if not (Path(store) if Path(store).is_absolute() else root/store).is_file():raise SystemExit('Signing keystore file does not exist.')
CHECK
  flutter build appbundle --release --dart-define-from-file="$CONFIG"
  echo 'AAB: build/app/outputs/bundle/release/app-release.aab (signing must be configured)'
fi
