# Operations — Android API and Telegram worker

## Services
- FastAPI API and PostgreSQL; SQLite is local to the Android app or disposable tests.
- Independent Telegram webhook/delivery worker (`services/telegram-bot`), strictly **single replica (`1`)** with persistent SQLite retry/dedup state (`/data/worker/worker.sqlite`). Webhook ingress (`POST /telegram/webhook` -> worker `:8081/webhook`) is implemented; `getUpdates` long polling is not implemented, FastAPI's `/api/v1/telegram/webhook` stub is disabled (`501` / gateway `404`), and running >1 worker replica is unsupported because `pending-deliveries` polling is unleased.
- nginx **API/webhook gateway**, not a static web-client host. Android is installed as APK/AAB.
- AI requests and PDF/PNG generation currently run in the API process, not a separate AI/export worker.
- API exposes cheap liveness at `GET /health` and database readiness (`SELECT 1`, `503` on failure) at `GET /ready`.

## Deployment
Use `deploy/compose.yml`; no web build is required. Generate a private `.env` with
`scripts/init-environment.py`, then fill the bot token and actual HTTPS webhook domain.
Compose constructs the internal PostgreSQL URL using service host `db`. The gateway
binds to host `127.0.0.1:8080`; an owner-managed TLS reverse proxy must forward to it.
Do not expose PostgreSQL, API container ports or worker ports directly to the Internet.
Gateway denies backend internal Telegram routes; the worker reaches them on the Docker network.

See [Persian setup guide](telegram-setup-fa.md) for exact commands, distinct credentials,
webhook registration, pairing, verification, logs, backups and troubleshooting.
Health endpoints are liveness checks, not a full production readiness/observability suite.

## Known static-analysis debt

`backend/app/geometry` is currently excluded from Ruff and mypy analysis, and its
code contains `type: ignore` comments. Passing those checks does not establish that
geometry is lint- or type-clean; addressing this debt requires a separate, reviewed
geometry change with appropriate golden tests.

## Persistence and recovery
Persist PostgreSQL, `/data/assets`, `/data/exports` and `/data/worker`. API/worker run
as UID 10001; writable volumes need appropriate ownership, not world-wide write access.
Worker mounts exports read-only. Protect and encrypt backups: they contain customer
records, photos, documents and chat linkage. Keep the provider encryption master key
separate from the encrypted database, with an owner-controlled recovery procedure.

1. Pause writes/worker ingestion or take a documented consistent snapshot.
2. `pg_dump -Fc` plus a consistent snapshot of assets, exports and worker state; record
   Alembic revision and checksums. Encrypt and retain an off-host copy.
3. Restore with `pg_restore --no-owner` into an isolated environment; restore permissions.
4. Verify counts, sample hashes, migrations and downloads before switching traffic.
   Prevent external Telegram replay while testing a restored pending-delivery queue.
5. Record recovery point/time and actual results. Owner production recovery is not yet verified.

Never blindly stamp or discard a legacy `create_all` database. Schema changes require a
reviewed Alembic migration. Do not automatically downgrade a production database as a
rollback; compatibility and data loss must be assessed first. Retention/cleanup for
exports, photos, pairing codes and worker retry payloads remains an open release task.
