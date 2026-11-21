# Security review — Phase 5 final pass (2026-11-21)

Scope: this repository at branch `arena/f8492bec-cabinet-survey-ai` after Phase 5 items 1–5,
covering the backend API, Telegram worker, Android client, CI workflows and deployment
files. This is a code and configuration review by the implementing agent. It is **not**
an independent penetration test and **not** release approval. It assumes a personal-use
deployment run by one owner, with no paid infrastructure.

The PR #1 report this file used to contain is replaced; its fixed findings (AUTH-01…04,
INPUT-01, DATA-01/02, SYNC-01, TG-01…03) have regression tests and are not repeated.

Severity guide:
- **High:** realistic compromise of secrets, signing or customer data.
- **Medium:** needs a specific condition or misconfiguration, or causes notable data
  exposure or loss.
- **Low:** limited impact or defence in depth.

## Open risks

| ID | Severity | Risk | Recommended action |
| --- | --- | --- | --- |
| REL-01 | **High** | **Release signing secrets on tag pushes.** `client-ci.yml` passes `ANDROID_KEYSTORE_*`, `ANDROID_KEY_*` and `RELEASE_API_BASE_URL` to the build only on `push` to a branch with `github.ref_protected == true`, **or on any tag push**. The repository is public. `main` is **not protected** (`gh api …/branches/main` → `protected:false`), and there are no rulesets and no environments. Result: branch pushes never get the secrets (they fail safe to a disposable keystore), but any collaborator who can push a tag gets the real signing key in a job they control through the workflow file at that tag. | Protect `main` (rulesets: PR + passing checks, no force push). Add a tag ruleset limiting `v*` tag creation to the owner. Move the secrets into a GitHub **Environment** (`release`) with required reviewer and deployment-branch/tag rules, and reference it only from the release build job. Keep the `ref_protected` condition. Do not add release secrets until this is done. |
| TG-04 | Medium | **Telegram worker is single-replica only.** `GET /api/v1/telegram/internal/pending-deliveries` selects `status == "pending"` with `LIMIT 20` and no claim, lease or `FOR UPDATE SKIP LOCKED`. Worker dedup and retry state is local SQLite (`/data/worker/worker.sqlite`). Two workers, or a second poller, can send the same document twice. Compose pins `replicas: 1` and the docs say so, but nothing enforces it at runtime. | Keep `replicas: 1`. Before any scale-out, add a claim step (`UPDATE … SET status='sending', lease_until=… WHERE id IN (SELECT … FOR UPDATE SKIP LOCKED)`) with lease expiry, and move dedup state into PostgreSQL. Optionally add a PostgreSQL advisory lock held by the worker at startup so a second instance refuses to run. |
| DEV-01 | Medium | **Plaintext copies outside the encrypted store.** Phase 5 item 1 encrypts the local DB and app-private photos. Not covered: (a) PDF/PNG exports the user saves or shares outside the app (Downloads, share targets, Telegram); (b) the copy the camera or gallery app keeps of a photo taken through the system picker. Both are plaintext on the device and outside the app's control (documented in `apps/client/README.md` and `docs/offline-sync.md`). | Tell users in the UI when saving or sharing an export. Prefer sharing via `content://` URIs with temporary grants over writing to shared storage. Optionally offer in-app capture (CameraX into app-private storage) so no gallery copy is created. Rely on Android device encryption and screen lock as the baseline. |
| SRV-01 | Medium | **No server-side retention for exports and uploads.** Rendered exports (`EXPORT_STORAGE_DIR`) and re-encoded uploads stay on disk forever. Deleting a project is a soft delete and does not remove its files. The files contain customer names, project titles and room drawings. | Add a retention job: delete export files after N days (they can be re-rendered), and remove the files of soft-deleted projects after a grace period. Document backup retention in `docs/operations.md`. Encrypt the data volume (LUKS or provider disk encryption). |
| CI-01 | Medium | **`app/geometry` is excluded from ruff and mypy** (`backend/pyproject.toml`: ruff `extend-exclude`, mypy `exclude` plus `follow_imports = "silent"` for `app.geometry.*`). The deterministic geometry engine decides every exported dimension but gets no lint or type checks. It is covered only by behaviour and golden tests (`test_geometry*.py`, `test_fixtures/geometry`). Phase 5 was not allowed to change it. | In a separate, approved phase, enable ruff and mypy for `app/geometry` with the golden fixtures as a safety net, and fix findings without changing output (goldens must stay byte-identical). Until then, any geometry change needs a golden-diff review. |
| CI-02 | Low | **Supply chain.** Python locks pin versions but **not hashes**. GitHub Actions are pinned to major tags (`actions/checkout@v5`, `subosito/flutter-action@v2`, `reactivecircus/android-emulator-runner@v2` …), not commit SHAs. Item 5 added `arabic-reshaper==3.1.0` and `python-bidi==0.6.12` (both pure Python, used only for text layout). A compromised tag or package release would run in CI, including the job that could receive signing secrets (REL-01). | Generate locks with `pip-compile --generate-hashes` and install with `--require-hashes`. Pin third-party actions to full commit SHAs (Dependabot can update them). Enable Dependabot or `pip-audit` for Python and Gradle. |
| UP-01 | Low | **Image decoder exposure.** Item 2 limits uploads to JPEG, PNG and WebP by magic bytes, enforces size and pixel limits, and decodes and re-encodes them (stripping EXIF/GPS). Decoding still runs Pillow and libwebp/libjpeg/libpng on untrusted bytes in the API process, so a decoder CVE could be reachable by an authenticated user. There is no malware scanning; this was a deliberate decision for personal use. | Keep Pillow and the base image patched (rebuild regularly). Optionally run decoding in a subprocess with resource limits (`ulimit -v`, timeout). |
| OPS-01 | Low | **Rate limiting behind the gateway.** Auth throttling keys on the client address. If `FORWARDED_ALLOW_IPS` and the gateway are misconfigured, every request appears to come from the proxy and shares one quota. The production validator rejects `*`, but it cannot prove the right proxy IP is set. Fixed windows allow bursts at window edges. | Follow `docs/operations.md` (set `FORWARDED_ALLOW_IPS` to the gateway address only). Check the logs once after deployment to confirm real client IPs appear. Optionally add nginx `limit_req` on `/api/v1/auth/`. |
| OPS-02 | Low | **`.env.example` is incomplete** for Phase 5 settings: `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_DIMENSION`, `UPLOAD_MAX_PIXELS`, `EXPORT_MAX_CONCURRENT_JOBS` and `EXPORT_JOB_STALE_SECONDS` are missing. Their defaults are safe, but operators cannot see them. | Add them, with their defaults and comments, to `.env.example`. |
| EXP-01 | Low | **In-process export jobs.** Rendering runs in a FastAPI background task, bounded by a semaphore (`EXPORT_MAX_CONCURRENT_JOBS=2`). The queue itself is unbounded and holds render specs in memory. A restart loses queued work, which is reported `failed` after `EXPORT_JOB_STALE_SECONDS`. An authenticated user can queue many jobs (memory/CPU) because there is no per-user export rate limit. Each replica renders only its own jobs. | For personal use, accept the risk. If usage grows, cap queued jobs per user (e.g. 409 above 3 active) or move rendering to a worker with a DB-backed queue. |
| EXP-02 | Low | **Export integrity depends on a bundled font and shaping libraries.** Item 5 pins Vazirmatn by SHA-256; a missing or changed font fails startup and exports, and nothing falls back to system fonts. A wrong shaping result would show text incorrectly but cannot change dimensions (geometry numbers come from the engine). Page scale is exact in the PDF, but a print made with "fit to page" is not to scale. | Keep the digest check. Review the visual sample in `docs/export-output.md` when updating the font or the shaping libraries. Users must print at 100% and check against the printed scale bar. |
| AUTH-05 | Low | **Offline logout cannot revoke server sessions** until the device is online (unchanged from PR #1). Access tokens last 30 min; refresh tokens last 7 days, rotate on every use and are revoked on replay. | Accept. After a device is lost, change the password from another device; this revokes all sessions (`POST /api/v1/auth/change-password`, AUTH-03). |
| API-01 | Low | **OpenAPI and docs are enabled in the app** (`/docs`, `/redoc`, `/openapi.json`). The production gateway returns 404 for everything outside `/api/`, `/health`, `/ready` and `/telegram/webhook`, so they are not public in the documented deployment. They would be exposed if the API port were published directly. | Disable them when `APP_ENV=production` (`docs_url=None` etc.), or keep the gateway as the only published port (`deploy/compose.yml` already binds the gateway to `127.0.0.1:8080`). |

## Controls confirmed in this pass (with tests)

- **Local data (item 1 + follow-ups):**
  - SQLCipher DB, with the key wrapped by Android Keystore.
  - A generic `open_failed` first offers "try again". Only "not a database", "file is
    encrypted" or a missing wrapped key offers the destructive reset immediately.
  - Tests: `local_open_failure_test.dart`, `local_reset_test.dart`, and the emulator
    `local_encryption_test.dart` in CI.
- **Uploads (item 2):**
  - Magic-byte allowlist, size and pixel limits, decompression-bomb rejection (413),
    re-encoding with EXIF/GPS removed, and random server file names with no traversal.
  - Tests: `backend/tests/test_upload_security.py`.
- **Production config (item 3):**
  - The app refuses to start with default or weak secrets, wildcard or insecure CORS,
    `DEBUG=true`, a non-PostgreSQL or insecure DB URL, `FORWARDED_ALLOW_IPS=*`, or an
    unknown `APP_ENV`.
  - Tests: `backend/tests/test_production_config.py`. TLS and trusted-proxy setup is in
    `docs/operations.md`.
- **Exports (item 4):**
  - Every room is included, and the approval rules are unchanged (409 unless an explicit
    exclude/flag option is set).
  - Owner checks on status and download.
  - Idempotency-Key replay; a failed render releases the key; the generic error does not
    leak internals.
  - Audit actions: `export.create`, `export.complete`, `export.fail`.
  - Tests: `backend/tests/test_export.py`, `test_phase3_audit_ai_controls.py`, and
    PostgreSQL `test_postgres_concurrency.py`.
- **Export output (item 5):**
  - Only the embedded, pinned font is used; shaping and RTL are applied; the PDF scale is
    measured exactly.
  - Tests: `backend/tests/test_export_text_scale.py`. See `docs/export-output.md`.
- **Renderer input:**
  - The renderer consumes only engine SVG with XML-escaped labels (`html.escape` in the
    engine) and never uploaded SVG.
  - svglib parses with `resolve_entities=False`.
  - Label lengths are capped at 200 characters by the schemas.
- **AI and STT:**
  - Endpoints come only from server configuration, must use `https://`, and keys are
    Fernet-encrypted.
  - AI output stays unapproved, and confidence never approves anything.

## Not verified

- No physical Android device was used. Emulator results come from CI only.
- No live Telegram, AI or STT credentials were used. Workers were tested with HTTP test
  transports.
- No production TLS certificate, container hardening, volume encryption or backup restore
  was checked on real infrastructure. The restore drill runs in CI against disposable
  PostgreSQL.
- No independent penetration test was done.
- No paper print scale was measured (see `docs/export-output.md`).
- GitHub repository secrets could not be listed with the available token, so it is
  unknown whether release secrets are configured yet. REL-01 applies as soon as they are.
