# Engineering status — 2026-11-13

**Pre-release implementation, not a release candidate.** No production deployment,
store publication or live provider/bot verification is claimed.

## Verified evidence

| Gate | Evidence | Result |
| --- | --- | --- |
| Clean Python dependency install | Fresh `/tmp/cabinet-verify` venv; `pip install -r backend/requirements.txt`; `pip check` | No broken requirements |
| Backend regression | `cd backend && /tmp/cabinet-verify/bin/pytest -q` | **79 passed**, 2 deprecation warnings |
| Independent worker tests | `cd services/telegram-bot && PYTHONPATH=. /tmp/cabinet-verify/bin/pytest -q` | **4 passed**, isolated HTTP transports |
| SQLite migrations | Initial upgrade, schema comparison, downgrade | Passed in backend tests |
| PostgreSQL migrations | GitHub backend CI run 43435156620 | Upgrade/check/downgrade/re-upgrade passed |
| Flutter analysis | GitHub client run 43435156646, commit c5cdc96 | Passed |
| Flutter tests | Same run | **12 passed** |
| Chrome-platform tests | Same run: geometry, API transport and form lifecycle | **8 passed** |
| Production Web compilation | Same run | Passed |
| Android debug APK | Same run | Build passed |
| Android release AAB | Same run | Failed: lint uses Java 21 API on Java 17; CI runtime corrected to Java 21, rerun pending |
| Docker/runtime deployment | Toolchain unavailable locally | Not executed |

Run links: https://github.com/gase99/cabinet-survey-ai/actions/runs/43435156646
and https://github.com/gase99/cabinet-survey-ai/actions/runs/43435156620 .

## Implemented areas
- FastAPI auth/profile, ownership-scoped customers/projects, rooms/walls/elements,
  approvals, history, assets, drawings, export jobs, sync, Telegram and administration.
- Sync validates parents and allowlists, locks versioned updates, persists idempotent
  receipts and rejects stale writes. Failed savepoints do not poison a batch.
- Engine requires explicit endpoints rather than guessing topology. Canonical SVG hash
  fixtures cover rectangle/L/U/irregular rooms with windows, doors, columns and pipes.
- Actual SVG vector PDF and raster PNG rendering replaced simulated export rectangles.
  Tests verify A3/A4 media boxes, vector paths, 300-DPI PNG size and approval/error gates.
- Bounded uploads validate MIME/signatures/decoded images, use private files/controlled
  suffixes, reject SVG and do not reveal filesystem paths in asset metadata.
- Online vision adapter validates source-linked JSON, source regions and exact values/
  units, rejects approval/geometry fields and never auto-applies candidates. Unknown
  providers and unavailable audio return errors, not successful mock results.
- Admin provider credentials use Fernet with an external master key. Missing encryption
  configuration fails closed. Enable flags, model selection and daily request quota
  are enforced. No key/ciphertext is returned to clients.
- Independent non-root Telegram worker persists webhook updates/deduplication, private
  pairing, retry state, send receipts and callback retries. A post-send crash before
  receipt persistence can duplicate delivery: at-least-once, not exactly-once.
- Flutter Riverpod shell, Persian RTL/English, themes, auth/secure refresh restoration,
  account-isolated SQLite, transactional outbox/revisions, project/customer/room/wall/
  element capture, integer-mm validation, local vector plan/elevations, editing,
  session undo/redo, camera/gallery photos, sketch candidate/source-region review,
  approval controls, authenticated export download and Telegram controls.
- Conflicts preserve snapshots and require explicit keep-server or keep-local rebase.
  No local edit is silently converted to an approved measurement.
- API/worker Dockerfiles, PostgreSQL/API/worker/nginx compose and deployment/backup docs.

## Decisions and defects corrected in this milestone
- Removed unsafe generic sync ORM assignment and missing nested parent authorization.
- Removed topology heuristics, implicit wall-height/unit assumptions, fake masked-key
  storage, successful empty transcription and falsely successful recovery-email status.
- Restricted SVG room access and customer reassignment to authorized ownership.
- Added explicit initial Alembic revision. Existing create_all databases must be backed
  up and reviewed before conversion, not blindly stamped or discarded.
- Flutter form controllers now belong to dialog lifecycle, including exit animations;
  the regression test passes. FFI widget tests run without background isolates.
- Generated test exports are ignored and isolated in temporary test directories.

## Remaining acceptance blockers
- Android AAB rerun/artifacts pending; browser/device interactive workflows not accepted.
- Crop/rotate/perspective correction, OCR preprocessing, voice recording/transcription,
  full sketch correction/import workflow and some diagnostic translations incomplete.
- Full drawing drag/snapping editor, persistent undo stacks and server version restore
  incomplete. Local previews are not certified fabrication drawings.
- Sync is manual, with REST snapshot import; `/sync/pull` is only a receipt feed.
  Deletion/tombstones, photo upload sync, background reconnect, full merge/retry UI and
  device-local guest-to-account migration are incomplete.
- SQLite/photos are not encrypted. Refresh revocation, distributed rate limits,
  recovery email, comprehensive audit/privacy retention and security review remain open.
- Multi-room drawing packages, Persian export font shaping, physical print calibration
  and complete reports need work. Export currently selects the first project room.
- Live vision, Telegram linking/delivery/failure tests, hosted TLS/webhook acceptance,
  Docker deployment, backup recovery drill and performance testing are unverified.
- Owner API host, provider credentials, bot token, production signing and deployment
  authorization are required for connected release validation. CI mobile builds use
  an intentionally invalid API host and default development signing, not owner signing.

## Progress accounting
**0 of 7 complete acceptance groups (0%)**: Application, Measurements/AI, Engineering
Drawings, Export, Offline, Telegram, Production. This conservative metric counts only
fully verified acceptance groups, not source volume or test count. Substantial tested
subsystems exist, but no group satisfies every production acceptance criterion yet.

## Next execution priorities
1. Finish Android build gates and expose artifacts with precise signing/host limitations.
2. Test complete Web/Android workflows, camera, secure storage and SQLite persistence.
3. Complete offline lifecycle, scanner/editor and multilingual export limitations.
4. Complete auth/security hardening, live integrations and recovery drill before RC.

## Android toolchain correction
AAB failure was `image_picker_android:lintVitalAnalyzeRelease` with
`NoSuchMethodError: java.util.List.removeLast()`. The generated current Android
lint toolchain requires Java 21. CI now uses Java 21; lint is not disabled.
Artifact upload is now `always()` so successful Web/APK outputs survive a later
failed gate. Previous runs skipped artifact upload after AAB failure. AAB success
must be verified from the corrected run, not inferred from the Java change.
