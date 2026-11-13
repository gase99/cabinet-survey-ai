# Telegram bot service

This is a separately deployable integration worker, not a process hosted by Telegram.

Telegram operates the Bot API and transports updates/messages. It does not provide general-purpose hosting for arbitrary bot application code. Run this service on a VPS, container platform, or managed cloud runtime you control. The service calls the official Telegram Bot API over HTTPS.

## Responsibilities
- Secure account linking using short-lived, single-use pairing codes.
- Send user-approved PDF/PNG exports and delivery status.
- Validate webhook requests using a secret token.
- Never accept bot tokens from the mobile/web client.
- Never log tokens, pairing secrets, customer phone numbers or document contents.
- Use webhook mode in production; long polling may be used for local development.

No bot token is committed. Configure `TELEGRAM_BOT_TOKEN` in the deployment secret manager.
