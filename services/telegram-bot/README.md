# Telegram worker

Independent **single-replica** application on owner-controlled compute. Telegram provides
the Bot API, not general-purpose code hosting.

## Implementation status & replica rule
- **Webhook mode implemented:** `POST /webhook` (proxied publicly at `POST /telegram/webhook`
  by `deploy/gateway.conf`) verifies `X-Telegram-Bot-Api-Secret-Token`, caps request bodies
  at 1 MiB, deduplicates `update_id` in `/data/worker/worker.sqlite`, and processes pairing
  and document deliveries. Long polling (`getUpdates`) is **not** implemented; FastAPI's
  legacy `/api/v1/telegram/webhook` returns `501` and is blocked (`404`) at the gateway.
- **Strictly one replica (`1`):** Do **not** run multiple worker replicas or a second poller.
  `/api/v1/telegram/internal/pending-deliveries` returns pending rows without multi-worker
  leases and retry state lives in `/data/worker/worker.sqlite`; >1 replica would cause
  duplicate Telegram document sends.
- **At-least-once delivery:** A crash after Telegram accepts `sendDocument` but before receipt
  persistence may resend once on recovery. Unlink cancels pending jobs and rechecks status
  before retries, but cannot retract an already sent document.
- **Security boundaries:** Pair only private chats using 10-minute single-use codes; send only
  explicitly selected, approved PDF/PNG exports; use distinct secrets for Telegram ingress
  (`TELEGRAM_WEBHOOK_SECRET`) vs. internal backend auth (`BACKEND_WORKER_SECRET`); never put
  bot tokens in Android, Git or logs.

Run non-root via the supplied Dockerfile, persist `/data/worker`, mount `/data/exports`
read-only, and expose only `/webhook` through the HTTPS gateway (`/health` is internal liveness).

Configuration and exact setup commands: [Telegram deployment contract](../../docs/telegram-deployment.md)
and [Persian guide](../../docs/telegram-setup-fa.md).
Tests: `PYTHONPATH=. python -m pytest -q`. HTTP test doubles are not live Telegram evidence.
