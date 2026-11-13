# Telegram integration and deployment

## Important hosting distinction
Telegram provides the Bot API, not general-purpose compute hosting for arbitrary user bot code. The bot application must run on infrastructure controlled by the project owner (VPS, Docker host, or managed cloud/container service). It communicates with Telegram over HTTPS.

Running a self-hosted Telegram Bot API server is a different optional advanced setup; it does not host the bot application's logic and is not required for normal bot operation.

## Production topology
1. Authenticated user requests linking; FastAPI issues a short-lived, single-use pairing code.
2. Bot worker receives a Telegram update and exchanges the code with FastAPI.
3. Backend stores the Telegram chat/user association after verification.
4. Export service creates a PDF/PNG.
5. Delivery worker sends the file through Telegram Bot API and records message ID/status.

## Deployment
Recommended initial option: Docker container on a small VPS with restart policy, HTTPS webhook endpoint, health checks and managed environment secrets. Polling may be used for local development.

## Required secrets
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- Backend service credentials with least privilege

Never commit secrets. Do not ask customers to paste bot tokens into the app. Telegram delivery is optional and must not block in-app downloads.

## Current backend contract (pre-release)
`TELEGRAM_WEBHOOK_SECRET` is mandatory for worker access. Missing configuration
returns HTTP 503; missing/incorrect credentials return HTTP 401. Pairing verification
and internal delivery endpoints accept `X-Webhook-Secret`; webhook authentication
uses `X-Telegram-Bot-Api-Secret-Token`. Query-string credentials are not accepted.
New pairing codes replace prior unused codes and expire after ten minutes.
The webhook currently acknowledges updates only: update processing and external
worker delivery are still release blockers, not completed functionality.

## Independent worker implementation
`services/telegram-bot/worker.py` exposes `/webhook` and `/health` and is packaged in
its own non-root container. `deploy/compose.yml` mounts generated exports read-only
and a separate persistent worker SQLite volume. Run **one worker replica**. Its
update IDs, retry attempts and sent message receipts survive restarts. After a send
succeeds but a status callback fails, it retries the callback without resending.
A crash between Telegram acceptance and receipt persistence can still duplicate a
message; the external delivery guarantee is at-least-once, not exactly-once.

Use distinct secrets:
- Backend `TELEGRAM_WEBHOOK_SECRET`: authenticates the worker-to-backend channel.
- Worker `BACKEND_WORKER_SECRET`: same value as backend secret.
- Worker `TELEGRAM_WEBHOOK_SECRET`: ingress secret (compose uses `TELEGRAM_INGRESS_SECRET`).

Both worker secrets and the bot token must be at least 20 characters; generate
high-entropy random values, not memorable passwords. Configure the official Bot API
`setWebhook` on operator-controlled infrastructure with the HTTPS URL ending in
`/telegram/webhook` and the worker ingress `secret_token`. Never paste bot tokens
into the client, command history or public support logs. Do not point Telegram at
FastAPI's old webhook path: it now returns HTTP 501 after authentication.

User flow: create code in app -> private bot chat `/pair CODE` -> app checks link
status -> generate approved export -> select existing export in Telegram control.
PNG files are sent as documents to avoid lossy photo resizing. Delivery status is
available at `/api/v1/telegram/deliveries`; retries end in a reported failure after
five unsuccessful send attempts. Operators can inspect aggregate state in the
worker database without publishing chat IDs or payloads. Failed update payloads
may contain pairing codes; protect the worker volume and define a retention policy.

Four tests use HTTP test transports; no live bot credentials or VPS are available
in this session. Container builds, webhook TLS and live delivery remain unverified.
