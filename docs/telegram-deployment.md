# Telegram deployment contract

Telegram supplies the Bot API, **not hosting for this application's code**. Run API,
database and `services/telegram-bot` on infrastructure controlled by the owner.
The implemented worker uses an HTTPS **webhook**; long polling is not implemented.

## Flow and trust boundaries
1. Authenticated Android user requests a single-use ten-minute pairing code.
2. User sends `/pair CODE` in a private chat with the owner's bot.
3. Worker validates the ingress secret, durably queues the update and calls FastAPI's
   pairing endpoint using a separate API/worker credential.
4. User creates an approved export and explicitly selects it for Telegram delivery.
5. Worker reads the shared export volume and sends PDF/PNG as a document, persisting
   receipts/retries. Delivery is at-least-once, not exactly-once.

## Distinct environment names
- `TELEGRAM_BOT_TOKEN`: worker only; official Bot API credential.
- `TELEGRAM_WEBHOOK_SECRET`: worker ingress; sent by Telegram in
  `X-Telegram-Bot-Api-Secret-Token`, registered through `setWebhook.secret_token`.
- `TELEGRAM_WORKER_SECRET`: backend setting; mapped to worker `BACKEND_WORKER_SECRET`
  and sent as `X-Webhook-Secret` on internal API requests. It is **not** the Telegram header secret.
- `TELEGRAM_WEBHOOK_URL`: public HTTPS endpoint ending `/telegram/webhook`, no token in URL.

`deploy/compose.yml` maps these explicitly. Never put the bot token in Android, Git,
screenshots, logs or a pairing message. Telegram-facing URL is routed to worker port
8081, not FastAPI's inactive legacy webhook path. Internal backend delivery/pairing
routes are denied at the public gateway and authenticated on the internal network.

Use [the operator setup guide](telegram-setup-fa.md) and `scripts/configure-telegram.py`.
Keep exactly one worker replica. Unlink cancels pending jobs, but cannot retract an
already accepted/in-flight Telegram send. Protect persistent volumes and define retention.
No live token, public host or cloud deployment was supplied; live delivery is not claimed.
