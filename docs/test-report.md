# Verification report — 2026-11-13

## Release acceptance verification update — 2026-11-13

**NOT READY; PR #1 remains draft and must not be merged.** See
[release-acceptance](release-acceptance.md) and [security-review](security-review.md).

- Initial head `ca5bc6aedb652b268a03dd34438fe995f22b6d13`: all configured checks
  successful; evidence saved in `evidence/initial-head-checks.json`.
- Intermediate head `6e9bab8b4f70ef2a136ecd49c1c6a22a2bcf5cf5`: backend,
  PostgreSQL migration and worker checks passed; Flutter failed because its test
  binding blocked real HTTP. A real-network override is committed in
  `6fb2d68`; its remote result has **not** been verified. Older green artifacts
  are not proof of the new head.
- Latest local backend command: `cd backend && /tmp/acceptance-venv/bin/pytest -q`
  → **101 passed, 3 skipped, 2 warnings**. The skipped tests intentionally require
  isolated PostgreSQL for concurrent sync, pairing and shared auth quota tests.
- Latest local worker command: `cd services/telegram-bot && PYTHONPATH=. /tmp/acceptance-venv/bin/pytest -q`
  → **6 passed, 1 warning**; tests use HTTP transports, not live Telegram.
- Added revocable/rotating device sessions, authentication throttling, bounded
  request ingress, strict integer/topology/vertical validation, transactional dirty
  cache protection, Telegram unlink cancellation and cached retry authorization.
  Unknown elevation height/sill remain unpositioned rather than fabricated.
- New acceptance gates: physical SQLite close/reopen + real FastAPI conflict/export
  workflow (English/Persian); production Web Chrome capture/reopen; PostgreSQL
  transaction concurrency and isolated database/asset restoration drill. These are
  **NOT TESTED** until exact-head CI confirms execution, not just compilation.
- Authorized live AI/Telegram, physical Android, production signing/host and owner
  production recovery remain **BLOCKED**. No credentials/device were available.
- GitHub API subsequently returned **403 Resource not accessible by integration**;
  exact latest-head check collection is blocked pending GitHub reconnection in Arena.

Reproduce evidence collection after reconnecting:
`python scripts/check-head-ci.py /tmp/head-ci.json`.
No production deployment, publishing, live paid request or merge was performed.


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
