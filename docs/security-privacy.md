# Security and privacy baseline

- TLS for all remote traffic.
- Password hashing with a modern adaptive algorithm; short-lived access tokens and rotating refresh tokens.
- Role-based authorization and project ownership checks.
- AI provider keys, database credentials, JWT secrets and Telegram bot tokens are backend-only secrets.
- Never put secrets in Flutter assets, Android bundles, Git history, logs, screenshots or fixtures.
- Validate file type (magic bytes), size and image dimensions; re-encode images server-side (see below).
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

### Upload safety (personal-use deployment; no malware scanner by decision)
`POST /api/v1/assets` and `POST /api/v1/ai/sketch-analysis` accept **only JPEG, PNG and
WebP** (`backend/app/services/uploads.py`). PDFs, SVG, GIF and everything else get `415`.
- The type is decided by **magic bytes**; the declared Content-Type and any filename
  extension must agree with it, otherwise `422` (no extension/MIME-only trust).
- Size limit `UPLOAD_MAX_BYTES` (default 15 MiB, bounded single read) → `413` with the
  limit in the message. Dimension limits `UPLOAD_MAX_DIMENSION` (8192 px per side) and
  `UPLOAD_MAX_PIXELS` (40 MP) are checked from the header before decoding → `413`;
  Pillow's own decompression-bomb guard is also mapped to `413`.
- The image is decoded, EXIF orientation is applied to the pixels, then it is
  **re-encoded** without EXIF (incl. GPS), XMP, ICC, text chunks or trailing bytes.
  Only the re-encoded copy is stored, hashed for provenance, or sent to an AI provider.
  Animated/multi-frame images are rejected.
- Storage names are random server-generated `uuid4().hex` + canonical extension in
  `ASSET_STORAGE_DIR` (mode `0600`, dir `0700`, `O_EXCL`). The client filename is
  reduced to a display-only label (no separators, `..`, control characters or leading
  dots) and never used as a path; downloads only serve files directly inside the asset
  directory.
- This is input hardening, **not malware scanning**; re-encoding reduces but does not
  eliminate risk from image-decoder vulnerabilities, so keep Pillow patched.

Encryption of Flutter SQLite/photos, distributed auth rate limits, refresh-token
revocation, recovery email and full privacy retention were earlier release blockers; see
`security-review.md` for the current status. Do not describe the system as
production-secure yet.

New passwords use bcrypt-SHA256 prehashing so long/Persian UTF-8 passwords are not
silently truncated by raw bcrypt's 72-byte limit. Legacy bcrypt hashes still verify
for compatibility; plan explicit credential rotation/reset before production,
particularly for any previously overlong passwords. No stored hash is discarded.

## Android-only update
Browser storage/CORS is no longer applicable. Release network policy rejects HTTP;
Android cloud backup is disabled. Local survey SQLite/photos use SQLCipher (see
apps/client/README.md); exported files and external camera/gallery copies remain plaintext.
System document picker avoids broad storage permissions. See android-delivery-fa.md.
