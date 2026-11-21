# Telegram deployment contract

Telegram supplies the Bot API, **not hosting for this application's code**. Run API,
database and `services/telegram-bot` on infrastructure controlled by the owner.

## Webhook implementation status (vs. live verification)
- **Implemented in code (`services/telegram-bot`):** `POST /webhook` on worker port `8081`
  (exposed publicly via `deploy/gateway.conf` at `POST /telegram/webhook`) validates
  `X-Telegram-Bot-Api-Secret-Token` in constant time, enforces a 1 MiB streaming body cap,
  deduplicates `update_id` in `/data/worker/worker.sqlite`, pairs `/pair CODE` via internal
  `POST /api/v1/telegram/verify-pairing`, and sends approved PDF/PNG exports via `sendDocument`.
- **Not implemented / intentionally disabled:** Telegram `getUpdates` long polling is **not**
  implemented (never run a second poller alongside the webhook). FastAPI's legacy
  `POST /api/v1/telegram/webhook` route returns `501` and is blocked with `404` at the nginx gateway.
- **Verification boundary:** Worker webhook auth, deduplication, retry persistence and unlink
  cancellation are verified in CI via isolated HTTP transports (`services/telegram-bot/tests`).
  Live end-to-end delivery against `api.telegram.org` requires an owner-supplied
  `TELEGRAM_BOT_TOKEN` and public HTTPS domain and is therefore not claimed until operator acceptance.

## Single-replica requirement
Run **exactly one replica (`1`)** of `services/telegram-bot`:
1. The worker persists update deduplication and delivery retry state in a single-node SQLite
   database (`/data/worker/worker.sqlite`).
2. `GET /api/v1/telegram/internal/pending-deliveries` returns `status = "pending"` rows without
   multi-worker row leases; running multiple worker replicas concurrently would fetch the same
   pending deliveries and send duplicate files to Telegram chats.
3. Delivery is **at-least-once** (a crash after `sendDocument` succeeds at Telegram but before
   receipt persistence can resend once on recovery). Unlink (`DELETE /api/v1/telegram/unlink`)
   cancels pending deliveries, and the worker re-verifies delivery status before cached retries,
   but cannot retract a document already accepted by Telegram.
4. Scaling beyond one worker replica in the future requires replacing local SQLite queue state
   and unleased polling with PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` delivery leases.

## Flow and trust boundaries
1. Authenticated Android user requests a single-use ten-minute pairing code (`POST /api/v1/telegram/pairing-code`).
2. User sends `/pair CODE` in a private chat with the owner's bot.
3. Worker validates `X-Telegram-Bot-Api-Secret-Token`, durably queues the update and calls
   FastAPI's internal pairing endpoint using the separate `BACKEND_WORKER_SECRET`.
4. User creates an approved export and explicitly queues delivery (`POST /api/v1/telegram/send`,
   supporting `Idempotency-Key`).
5. Worker reads the read-only shared export volume (`/data/exports`) and sends PDF/PNG as a
   document, persisting receipts/retries.

## Distinct environment names
- `TELEGRAM_BOT_TOKEN`: worker only; official Bot API credential. Never place in Android, Git, logs or pairing replies.
- `TELEGRAM_WEBHOOK_SECRET`: worker ingress; sent by Telegram in
  `X-Telegram-Bot-Api-Secret-Token`, registered through `setWebhook.secret_token`.
- `TELEGRAM_WORKER_SECRET`: backend setting; mapped to worker `BACKEND_WORKER_SECRET`
  and sent as `X-Webhook-Secret` on internal API requests. It is **not** the Telegram header secret.
- `TELEGRAM_WEBHOOK_URL`: public HTTPS endpoint ending `/telegram/webhook`, no token in URL.

`deploy/compose.yml` maps these explicitly, and `deploy/gateway.conf` blocks `/api/v1/telegram/internal/*`,
`/api/v1/telegram/verify-pairing`, and `/api/v1/telegram/webhook` from public ingress.
Use [the operator setup guide](telegram-setup-fa.md) and `scripts/configure-telegram.py`.
