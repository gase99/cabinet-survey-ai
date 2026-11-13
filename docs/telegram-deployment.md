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
