# Operations

## Services
- API: stateless FastAPI service.
- Database: PostgreSQL with persistent volume and scheduled backups.
- Worker: background jobs for AI, export and Telegram delivery.
- Telegram bot: independently restartable container/process.
- Web client: static build served over HTTPS.

## Production requirements
Health/readiness probes and redacted structured logs; error reporting without customer content or secrets; controlled database migrations; backup retention and restore drills; resource limits, rate limits and upload quotas; monitoring for failed sync/AI/export/Telegram jobs; documented rollback and incident response.
