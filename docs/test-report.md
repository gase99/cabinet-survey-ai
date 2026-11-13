# Verification report — 2026-11-13

## Python (local, clean environment)
Created `/tmp/cabinet-verify` with Python 3.11 and installed
`backend/requirements.txt`. `pip check`: **No broken requirements found**.

- `cd backend && /tmp/cabinet-verify/bin/pytest -q`: **82 passed**, two dependency
  deprecation warnings (Starlette HTTPX test client and Passlib `crypt`).
- `cd services/telegram-bot && PYTHONPATH=. /tmp/cabinet-verify/bin/pytest -q`:
  **4 passed**, one Starlette test-client warning.
- Provider/Telegram transports are isolated test doubles, not live integration evidence.
- Backend suite includes auth/ownership, CRUD, explicit approvals, integer units,
  canonical geometry/rendering hashes, PNG/PDF page verification, migrations,
  stale-version conflicts, operation replay, bounded uploads, encrypted credentials,
  provider candidate validation and password prehash/legacy compatibility.

## Remote client (commit e9f3063)
Run: https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276

- `flutter analyze --no-fatal-infos`: passed; 11 informational deprecations remain.
- `flutter test --reporter expanded --timeout 30s`: **12 passed**.
- Chrome-platform survey/API/form tests: **8 passed**.
- `flutter build web --release`: passed.
- `flutter build apk --debug`: passed.
- `flutter build appbundle --release`: passed; AAB reported 57.6 MB.

Java 21 fixes a lint API/runtime mismatch observed under Java 17. No lint detector
was disabled. App bundle uses generated development signing, not owner signing.
Connected mobile endpoint is intentionally invalid until an authorized host is set.

## Remote server/worker CI
PostgreSQL migration service checks upgrade/check/downgrade/re-upgrade. Backend
and worker CI have passed; current per-commit check status remains visible on draft
PR https://github.com/gase99/cabinet-survey-ai/pull/1 .

## Explicitly unverified
Android device/emulator interaction, full browser end-to-end API/offline persistence,
live AI/Telegram, hosted webhook/TLS, Docker build/runtime, physical print scale,
backup restoration, signing/store publication and complete production security.
