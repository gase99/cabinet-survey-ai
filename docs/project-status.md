> **Historical PR #1 record:** the Android-only decision and current verification are in [android-delivery-fa.md](android-delivery-fa.md). Results below refer to the old Android/Web branch, not this revision.

# Engineering status — 2026-11-13

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


**Pre-release implementation, not a release candidate.** No production deployment,
store publication or live provider/bot verification is claimed.

## Verified evidence

| Gate | Evidence | Result |
| --- | --- | --- |
| Clean Python dependency install | Fresh `/tmp/cabinet-verify` venv; `pip install -r backend/requirements.txt`; `pip check` | No broken requirements |
| Backend regression | `cd backend && /tmp/cabinet-verify/bin/pytest -q` | **82 passed**, 2 deprecation warnings |
| Independent worker tests | `cd services/telegram-bot && PYTHONPATH=. /tmp/cabinet-verify/bin/pytest -q` | **4 passed**, isolated HTTP transports |
| SQLite migrations | Initial upgrade, schema comparison, downgrade | Passed in backend tests |
| PostgreSQL migrations | GitHub backend CI run 43435156620 | Upgrade/check/downgrade/re-upgrade passed |
| Flutter analysis | GitHub client run 43436483276, commit e9f3063 | Passed |
| Flutter tests | Same run | **12 passed** |
| Chrome-platform tests | Same run: geometry, API transport and form lifecycle | **8 passed** |
| Production Web compilation | Same run | Passed |
| Android debug APK | Same run | Build passed |
| Android release AAB | Same run | Build passed on Java 21 (57.6 MB AAB) |
| Docker/runtime deployment | Toolchain unavailable locally | Not executed |

Run links: https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276
and https://github.com/gase99/cabinet-survey-ai/actions/runs/43435156620 .

## Implemented areas
- FastAPI auth/profile, ownership-scoped customers/projects, rooms/walls/elements,
  approvals, history, assets, drawings, export jobs, sync, Telegram and administration.
- Sync validates parents and allowlists, locks versioned updates, persists idempotent
  receipts and rejects stale writes. Failed savepoints do not poison a batch.
- SVG labels are escaped; unknown element heights/sills remain explicitly unpositioned, never default-size boxes. Plan markers follow wall direction.
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
- Android artifacts are built; browser/device interactive workflows and owner signing are not accepted.
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
1. Independently install/test Android and Web artifacts against an authorized API host.
2. Test complete Web/Android workflows, camera, secure storage and SQLite persistence.
3. Complete offline lifecycle, scanner/editor and multilingual export limitations.
4. Complete auth/security hardening, live integrations and recovery drill before RC.

## Android build artifacts and toolchain correction
AAB initially failed in lint with `NoSuchMethodError: java.util.List.removeLast()`.
Switching the generated modern toolchain from Java 17 to Java 21 fixed it without
disabling lint. **All client gates passed** in run 43436483276.

Download Web bundle, debug APK and release-mode AAB:
https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276/artifacts/14044115931

Artifact: `client-development-builds`, ZIP size 155,701,620 bytes.
ZIP SHA-256: `de2f12d623465d53deeb00e504a9ac37e26017095ec862d746168841bbc9f590`.
GitHub reports expiration **2027-02-11**; download/archive it before then.
The artifact is stored externally, not committed as large generated binaries.
Mobile API host is intentionally `.invalid`; offline capture can be tested, while
connected acceptance requires rebuilding with the authorized API host. Android
signing is the generated development signing, not an owner release keystore.
Flutter source is unchanged between this build and the subsequent backend-only fixes.

New password hashes use bcrypt-SHA256 to avoid truncating long/multibyte passwords;
legacy bcrypt verification is preserved without silently rewriting credentials.
Review/rotate legacy credentials before production. Refresh revocation/rate limits
remain open. Clean-venv backend rerun after this fix: **82 passed**.
Analysis gate used `--no-fatal-infos`: 11 informational framework deprecations remain.
