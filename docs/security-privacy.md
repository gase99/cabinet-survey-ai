# Security and privacy baseline

- TLS for all remote traffic.
- Password hashing with a modern adaptive algorithm; short-lived access tokens and rotating refresh tokens.
- Role-based authorization and project ownership checks.
- AI provider keys, database credentials, JWT secrets and Telegram bot tokens are backend-only secrets.
- Never put secrets in Flutter assets, public web bundles, Git history, logs, screenshots or fixtures.
- Validate file type, size, image dimensions and content; scan uploads where deployment supports it.
- Restrict access to customer names, phone numbers, addresses and site images.
- Define deletion/export/retention policies before production.
- Audit approvals, edits, exports, account linking and deliveries.
- Rate-limit authentication, AI analysis and Telegram pairing.
- Use one-time, short-lived Telegram pairing codes; a Telegram username alone is not identity proof.
- Back up PostgreSQL and test restore procedures.
