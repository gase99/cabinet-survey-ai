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

## Implemented safeguards and remaining review
Provider API credentials submitted by administrators are encrypted using Fernet with
`SECRET_ENCRYPTION_KEY` supplied by the operator. Without a valid master key the API
returns HTTP 503 and stores nothing. Generate a key with
`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`
on a secure operator machine, never in shared logs. Back up the key in a separate
secret manager; losing it makes stored credentials unreadable. Provider reads honor
disable flags and daily request limits. PostgreSQL serializes requests against the
selected provider configuration row while applying the quota. Live concurrency and
provider token accounting still need production load testing.

Local files use controlled suffixes and private permissions. Decoded image signatures
must match MIME types; SVG uploads are rejected. PDF signature checks are not malware
scanning. Uploads remain untrusted customer documents. Configure a scanner/isolation
policy before production. Encryption of Flutter SQLite/photos, distributed auth
rate limits, refresh-token revocation, recovery email and full privacy retention
remain release blockers; do not describe the system as production-secure yet.
