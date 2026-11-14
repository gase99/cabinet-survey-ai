# Operations

## Services
- API: stateless FastAPI service.
- Database: PostgreSQL with persistent volume and scheduled backups.
- Worker: background jobs for AI, export and Telegram delivery.
- Telegram bot: independently restartable container/process.
- Web client: static build served over HTTPS.

## Production requirements
Health/readiness probes and redacted structured logs; error reporting without customer content or secrets; controlled database migrations; backup retention and restore drills; resource limits, rate limits and upload quotas; monitoring for failed sync/AI/export/Telegram jobs; documented rollback and incident response.

## Pre-release deployment configuration
`deploy/compose.yml` defines PostgreSQL, API, independent Telegram worker and nginx.
It is configuration, not deployment evidence. Build the Web bundle first. Configure
`.env` with private credentials and an internal `DATABASE_URL` referring to `db`,
not localhost. The nginx listener is bound to host loopback intentionally: place an
operator-managed HTTPS reverse proxy in front of it. No TLS certificates are bundled.
Never expose PostgreSQL or the internal worker endpoints directly to the Internet.

Persist PostgreSQL, `/data/assets`, `/data/exports` and `/data/worker`. Container UID
10001 must own writable volumes; do not make them world-writable. Restrict and encrypt
backups because they contain customer data and chat linkage. The worker needs only
read access to exports. Deployment scripts never purchase resources or mutate a
production database in this development session.

## Backup/restore procedure (drill still required)
1. Pause write traffic and worker ingestion or use a documented consistent snapshot.
2. Produce a PostgreSQL custom-format `pg_dump -Fc` using a least-privilege backup
   account; snapshot asset/export/worker volumes consistently with database state.
3. Encrypt backups, record checksums and migration revision, and retain off-host
   copies according to the owner's customer-data retention policy.
4. Restore to an isolated database with `pg_restore --no-owner`, restore volumes and
   permissions, then validate Alembic revision, project counts and sample hashes.
5. Start API and one worker against the restored copy with outbound Telegram disabled
   to avoid replaying customer deliveries. Test auth, geometry and export downloads.
6. Record recovery point/time and evidence before approving production readiness.

This procedure is documented, not a verified recovery drill. Existing databases
created by `create_all` predate migrations; do not automatically stamp or discard them.
