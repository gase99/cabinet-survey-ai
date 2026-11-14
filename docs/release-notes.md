> **Historical PR #1 record:** the Android-only decision and current verification are in [android-delivery-fa.md](android-delivery-fa.md). Results below refer to the old Android/Web branch, not this revision.

# Development candidate notes — 0.1.0 (not release accepted)

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


## Implemented and verified independently
- Clean-venv backend suite: 82 passing tests.
- Independent worker suite: 4 passing isolated tests; GitHub worker CI passed.
- Initial migration tested locally on SQLite and in CI on PostgreSQL, including
  metadata comparison and downgrade/re-upgrade. Existing create_all databases must
  not be stamped blindly: back up, inspect and migrate their actual schema first.
- Engine SVG goldens cover rectangle, L, U and irregular rooms with opening/utility
  elements. Missing endpoints produce validation errors rather than guessed topology.
- Exports render engine SVG, with tested PDF A3/A4 media boxes and 300-DPI PNG sizes.

## Client verification
Remote Flutter analysis, **12 Flutter tests**, **8 Chrome-platform tests**, production
Web compilation, Android debug APK and release-mode AAB all passed in run
[43436483276](https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276).
[Download build artifacts](https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276/artifacts/14044115931)
before 2027-02-11. These mobile binaries use development signing and an intentionally
invalid API host, not owner production credentials. Rebuild with the authorized
HTTPS host for connected testing. Device acceptance and live integrations remain
open; successful builds alone do not establish release readiness.

## Required before release acceptance
Independent device/browser acceptance; complete localization; sketch preprocessing;
voice; full geometry editor; synchronization deletion/photo/merge behavior; security
review and rate limits; session revocation and recovery email; local encryption;
provider token accounting/load verification; multi-room export and Persian font shaping;
physical print calibration; backup restore drill; live vision and Telegram tests;
owner signing configuration and authorized production HTTPS deployment.

No production deployment, app-store publication or live external API test is claimed.
