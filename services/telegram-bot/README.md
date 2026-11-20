# Telegram worker

Independent single-replica application on owner-controlled compute. Telegram provides
the Bot API, not general-purpose code hosting. The current implementation is **webhook
mode**, with durable update deduplication, retry state and delivery receipts.

- Pair only private chats using short-lived, single-use codes.
- Send only explicitly selected, approved PDF/PNG exports.
- Validate Telegram ingress secret and use a different backend-worker credential.
- Never accept bot tokens from Android; never log tokens, pairing codes or document contents.
- At-least-once delivery: a crash after sending but before receipt persistence may duplicate.

Run non-root via the supplied Dockerfile. Persist `/data/worker`, mount `/data/exports`
read-only, and expose only `/webhook` through the HTTPS gateway. `/health` is internal
liveness. Keep one replica. Long polling is not implemented; do not run a second poller.

Configuration and exact setup commands: [Persian guide](../../docs/telegram-setup-fa.md).
Tests: `PYTHONPATH=. python -m pytest -q`. HTTP test doubles are not live Telegram evidence.
