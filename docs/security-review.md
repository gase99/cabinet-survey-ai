> **Historical PR #1 record:** the Android-only decision and current verification are in [android-delivery-fa.md](android-delivery-fa.md). Results below refer to the old Android/Web branch, not this revision.

# Release security review — in progress, NOT release approval

Baseline: `ca5bc6aedb652b268a03dd34438fe995f22b6d13`, PR #1. Review is of
actual code. Initial exact-head CI is captured in `evidence/initial-head-checks.json`.
This report distinguishes confirmed defects, fixes with tests, and unverified controls.

## Confirmed findings addressed in this acceptance work

| ID | Severity | Finding / change | Regression evidence |
| --- | --- | --- | --- |
| AUTH-01 | High | Logout did not invalidate access/refresh credentials; now database-backed per-device revocable sessions | `test_session_security.py::test_logout_revokes_access_and_refresh` |
| AUTH-02 | High | Refresh replay usable indefinitely; now hashed one-time refresh rotation, row lock, family revocation on replay | `test_refresh_rotation_and_replay_revoke_session_but_not_other_device` |
| AUTH-03 | High | Password changes left stolen device credentials usable; now all user sessions revoked | `test_password_change_revokes_all_devices` |
| AUTH-04 | High | Authentication endpoints lacked throttling; now atomic PostgreSQL/SQLite quota shared across workers, no trust of spoofed forwarded headers | `test_shared_database_auth_throttle_ignores_spoofed_forwarded_headers` |
| INPUT-01 | Medium | Multipart/JSON parser could allocate before endpoint size checks; bounded ASGI ingress added | `test_request_ingress_rejects_oversized_json_before_parsing` plus existing upload tests |
| DATA-01 | High | Backend accepted self-crossing/degenerate polygons, disconnected corners within tolerance and invalid vertical element spans | `test_geometry_acceptance.py` |
| DATA-02 | Medium | Raw sync values could differ from Pydantic-coerced checks; dimensions now strict, coordinates bounded; wall resize validates child elements | `test_measurement_integrity.py` |
| SYNC-01 | High | Dirty snapshot check before network response could silently overwrite a newer queued edit; database import now rechecks transactionally | Flutter `snapshot import never overwrites a newly queued local edit` |
| TG-01 | High | Queued documents remained deliverable after unlink; backend cancels pending jobs, worker rechecks eligibility before cached retry | Backend unlink/callback test; worker cancelled-cache test |
| TG-02 | Medium | Terminal delivery callback could overwrite cancelled/sent state; only identical terminal acknowledgments are idempotent | `test_unlink_cancels_queued_deliveries_and_callback_replay_cannot_resurrect` |
| TG-03 | Medium | Unbounded worker request buffering and invalid update IDs; streaming request cap and signed-int-range IDs | worker webhook tests; additional malformed-ID coverage required |

## Controls inspected
- Ownership traversal is checked for nested rooms/walls/elements and sync parents;
  SVG room access and export/asset owner checks have regression tests.
- Uploaded MIME/signature/decoder checks reject SVG; filenames do not select storage
  paths. File modes are private. PDF signature validation is **not malware scanning**.
- Renderer consumes canonical, XML-escaped engine SVG, not uploaded SVG. Unknown heights
  and sill references are not inferred from pixels. A3/A4 printing calibration is open.
- Provider credentials are Fernet encrypted with external master key, never returned
  to clients. Invalid config fails closed. Provider output remains unapproved.
- Webhook ingress and worker API require server-side secrets. Update IDs persist across
  restarts. A crash after Telegram accepts a send but before receipt persistence may
  duplicate delivery; no exactly-once guarantee. Unlink cannot retract an in-flight send.
- Auth session migration invalidates legacy stateless tokens deliberately; users must
  sign in again. Customer/project/measurement records are not deleted or rewritten.

## Remaining release failures / limits
- Local SQLite/photos are unencrypted; shared-device cache access requires product/
  platform security work. Do not call this owner-approved device security.
- Fixed-window auth quotas can allow bursts across a minute boundary. Proxy deployment
  must configure trusted proxy addresses; otherwise a reverse proxy shares one quota.
  Infrastructure flood protection and quota load/concurrency testing remain required.
- Offline client logout can only clear local credentials; server-side revocation needs
  connectivity. No claim of remote revocation during an outage.
- Full production TLS/container/storage permissions, key rotation, retention/erasure,
  malware scanning, privacy review and independent penetration testing are unverified.
- Live AI, Telegram and owner-operated recovery drills require authorized credentials/
  infrastructure. Missing credentials were checked as booleans; no secrets were printed.

## Commands
`cd backend && /tmp/acceptance-venv/bin/pytest -q`: latest local **101 passed**.
`cd services/telegram-bot && PYTHONPATH=. /tmp/acceptance-venv/bin/pytest -q`:
**5 passed**, HTTP test transports, not a live Telegram test.
Remote acceptance gates remain pending until exact-head evidence is collected.
