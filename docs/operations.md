# Operations — Android API and Telegram worker

## Services
- FastAPI API and PostgreSQL; SQLite is local to the Android app or disposable tests.
- Independent Telegram webhook/delivery worker, one replica and persistent retry state.
- nginx **API/webhook gateway**, not a static web-client host. Android is installed as APK/AAB.
- AI requests and PDF/PNG generation currently run in the API process, not a separate AI/export worker.

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
