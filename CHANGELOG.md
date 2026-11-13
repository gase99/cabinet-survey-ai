# Changelog

## Unreleased
- Implement FastAPI domain APIs, deterministic geometry, export services and backend tests.
- Enforce room ownership on SVG access and authenticated Telegram worker access.
- Fix pairing expiry across SQLite timestamp handling; invalidate replaced and used codes.
- Add security regression tests. Backend checkpoint: 45 tests pass.
- Product remains pre-release; see docs/project-status.md for unverified requirements.
- Harden sync ownership, payload validation, approval separation and idempotent retries.
- Add initial Alembic schema with tested SQLite upgrade/downgrade.
- Replace export placeholders with SVG vector PDF and real raster rendering; verify A3/A4 dimensions.
- Add uncompiled Flutter local-first survey UI, database/outbox, localization, drawings and tests.
- Add Flutter platform bootstrap and independent Android/Web CI build gates (results pending).
- Add independently deployable Telegram webhook/delivery worker with durable retry and receipt state; four isolated worker tests pass.
- Add validated OpenAI-compatible vision adapter (live integration unverified).
- Reject missing measurement units, unknown providers and unavailable audio transcription explicitly.
- Remove heuristic topology invention; add canonical SVG golden fixtures for four room shapes.
- Add source-region sketch review and Telegram controls to Flutter source; remote validation pending.
- Add production startup safeguards, container configuration and PostgreSQL migration CI.
- Remote Flutter analysis, authored tests and production Web compilation passed at ea97a35; Android gates still pending.
- Harden bounded uploads, file signatures and MIME matching; local backend suite now 74 passing tests.
- Make password recovery honestly unavailable until an email service is configured.
- Replace fake masked provider-key storage with Fernet encryption and real server-side loading; enforce provider disable/daily quota.
- Require explicitly measured wall heights and validate project-customer ownership on reassignment.
- Clean-venv verification: 79 backend tests and 4 worker tests pass; dependency check clean.
- Remote Chrome-platform tests and production Web build pass; Android build status remains pending.
- Android debug APK compilation passed. AAB lint exposed a Java 17/21 toolchain mismatch; CI now uses Java 21 without disabling lint. Corrected AAB run pending.
