# Engineering status — 2026-11-13

## Verified checkpoint
- Backend suite: `cd backend && /tmp/venv/bin/pytest -q` — **45 passed**.
- Tests exercise auth, ownership, CRUD, measurements, deterministic geometry,
  AI text candidates, approval reset, export downloads, sync conflicts and pairing.
- Fixed SQLite pairing expiry comparisons (naive stored timestamps interpreted as UTC).
- New pairing codes invalidate older unused codes; successful codes cannot be reused.
- Worker and webhook routes now fail closed without configuration. Internal worker
  authentication uses `X-Webhook-Secret`, not query parameters.
- SVG requests validate room-to-project ownership; drawing creation returns HTTP 201.
- Installed the repository-pinned bcrypt 4.0.1 in the test environment; bcrypt 5 is
  incompatible with the current Passlib backend. Password security modernization
  remains part of the production review.

## Changed areas
Backend APIs, schemas, models, geometry, services and tests are working-tree changes
on the Arena branch. This checkpoint additionally updates pairing, drawings,
regression tests, runtime-data ignore rules, roadmap and agent execution guidance.

## Remaining release gates
- Flutter remains scaffold-level. Flutter SDK is not on PATH. Android/Web builds,
  responsive UI, Persian RTL, local SQLite and offline geometry are not verified.
- PostgreSQL migration upgrade/downgrade and backup restoration are not verified.
- Live multimodal AI, voice, scanner processing and OCR are not verified.
- Drawing editor, undo/redo and full revision restoration are incomplete.
- Physical print-scale, A3/A4 golden rendering and complete reports are not verified.
- External Telegram worker, real update handling, retries, deployment and live file
  delivery are not verified. Backend webhook currently only acknowledges updates;
  it must not be described as a working bot.
- Full security review remains open: password recovery, session rotation/revocation,
  rate limiting, approval enforcement across all drawing/export paths, upload
  hardening, provider secret storage, production configuration and log redaction.
- Backend tests are SQLite/TestClient tests, not evidence of live provider or
  production readiness. Deprecation warnings remain in framework/password code.

## Progress accounting
Release acceptance: **0 of 7 acceptance groups fully verified (0%)**. Groups are
Application, Measurements/AI, Engineering drawings, Export, Offline, Telegram and
Production. This strict metric tracks completed acceptance groups, not source-code
volume; backend test progress is separately reported above. No APK, AAB or
production Web artifact has been generated. No deployment is claimed.

## Next execution order
1. Audit remaining backend authorization/approval and session weaknesses.
2. Establish tested migrations and production startup configuration.
3. Implement Flutter workflows and local persistence; establish a usable build toolchain.
4. Complete scanner/providers, editor, offline sync and external Telegram worker.
5. Execute independent platform builds, golden fixtures, security and release gates.

## Continued implementation checkpoint
- Re-audited client: original runner was a single placeholder; no platform runners or tests.
- Backend re-verification: original 45 tests passed. Current local suite: **58 passed**.
- Added transactional sync receipts, field allowlists, parent ownership, explicit
  approval-only operations, customer sync, bounded elements and safe operation retries.
- Added initial explicit Alembic revision; SQLite upgrade/schema comparison/downgrade passes.
  PostgreSQL migration and existing development database conversion remain unverified.
- Replaced simulated PDF/PNG exports with actual engine SVG rendering. A3/A4 page
  sizes, vector path presence, 300-DPI PNG sizing and approval/error gates are tested.
- Implemented Flutter source for Riverpod bootstrap, fa/en shell, authentication,
  account-isolated SQLite, durable outbox/revisions, projects/customers/rooms/walls/
  elements, local vector plan/elevations, measurement editing, undo/redo, local camera/
  gallery photo storage, explicit approval controls, export downloads and server-choice
  conflict resolution. This is **uncompiled implementation**, not verified functionality.
- Added Flutter geometry/API/SQLite/widget tests; not yet executed. Local environment
  has no Flutter, Dart, Java or Android SDK. Added reproducible platform-generation
  script and CI to analyze/test/build on a suitable runner; results pending.
- Sketch preprocessing/provider review overlays, voice, full editor, photo upload sync,
  local guest-to-account transfer, automatic token refresh, full localization of all
  diagnostics, local encryption and independent platform acceptance remain incomplete.
- Sync pull is explicitly only a receipt feed. Client imports REST snapshots after
  pushing; deletion propagation and full incremental change cursors remain incomplete.
- No release-candidate claim. The 0/7 fully verified acceptance-group metric remains.
