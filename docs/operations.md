# Operations — Android API and Telegram worker

## Services
- FastAPI API and PostgreSQL; SQLite is local to the Android app or disposable tests.
- Independent Telegram webhook/delivery worker (`services/telegram-bot`), strictly **single replica (`1`)** with persistent SQLite retry/dedup state (`/data/worker/worker.sqlite`). Webhook ingress (`POST /telegram/webhook` -> worker `:8081/webhook`) is implemented; `getUpdates` long polling is not implemented, FastAPI's `/api/v1/telegram/webhook` stub is disabled (`501` / gateway `404`), and running >1 worker replica is unsupported because `pending-deliveries` polling is unleased.
- nginx **API/webhook gateway**, not a static web-client host. Android is installed as APK/AAB.
- AI requests and PDF/PNG generation currently run in the API process, not a separate AI/export worker.
- API exposes cheap liveness at `GET /health` and database readiness (`SELECT 1`, `503` on failure) at `GET /ready`.

## Deployment
Use `deploy/compose.yml`; no web build is required. Generate a private `.env` with
`scripts/init-environment.py`, then fill the bot token and actual HTTPS webhook domain.
Compose constructs the internal PostgreSQL URL using service host `db`. The gateway
binds to host `127.0.0.1:8080`; an owner-managed TLS reverse proxy must forward to it.
Do not expose PostgreSQL, API container ports or worker ports directly to the Internet.
Gateway denies backend internal Telegram routes; the worker reaches them on the Docker network.

See [Persian setup guide](telegram-setup-fa.md) for exact commands, distinct credentials,
webhook registration, pairing, verification, logs, backups and troubleshooting.
Health endpoints are liveness checks, not a full production readiness/observability suite.

## TLS termination
The stack never terminates TLS itself. Topology:

```
Android app / Telegram --HTTPS--> owner TLS proxy (host, :443)
    --HTTP--> gateway nginx 127.0.0.1:8080 --> api:8000 / telegram:8081 (Docker network)
```

Requirements for the owner-managed TLS proxy (Caddy, nginx, Traefik …):
- A publicly trusted certificate (e.g. Let's Encrypt) for the API/webhook domain;
  TLS 1.2+ only; redirect or refuse plain HTTP on :80; enable HSTS
  (`Strict-Transport-Security: max-age=31536000`). Telegram webhooks require HTTPS.
- Forward to `http://127.0.0.1:8080` only. Do not publish PostgreSQL, the API container
  or worker ports; the gateway already binds to loopback.
- Set `X-Forwarded-Proto https` and **append** the client address to
  `X-Forwarded-For` (nginx: `$proxy_add_x_forwarded_for`; Caddy does this by default).
- Keep `client_max_body_size` (or equivalent) ≥ 16 MiB so the API, not the proxy,
  returns the clear upload-size error. Release Android builds reject cleartext HTTP.

Minimal nginx example on the host:

```nginx
server {
    listen 443 ssl; http2 on;
    server_name api.your-domain.example;
    ssl_certificate     /etc/letsencrypt/live/api.your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.example/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;
    client_max_body_size 16m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
server { listen 80; server_name api.your-domain.example; return 301 https://$host$request_uri; }
```

## Trusted proxies and client addresses
Authentication throttling is keyed by the client address uvicorn reports. uvicorn only
honours `X-Forwarded-For` from peers listed in `FORWARDED_ALLOW_IPS` and then takes the
right-most address that is not itself trusted, so values a client injects further left
are ignored. The gateway appends its peer (the host TLS proxy) to the header.
- Default `FORWARDED_ALLOW_IPS=127.0.0.1`: forwarded headers from the gateway are **not**
  trusted, every request appears to come from the gateway, and all clients share one auth
  quota. This is safe but can lock out legitimate users during an attack.
- To get per-client quotas, give the Compose network a fixed subnet in a private
  override file and trust exactly that subnet, e.g. `FORWARDED_ALLOW_IPS=172.28.0.0/24`
  with `networks: {default: {ipam: {config: [{subnet: 172.28.0.0/24}]}}}`. Choose a
  subnet that does not collide with other networks on the host.
- Never use `FORWARDED_ALLOW_IPS=*`; production startup refuses it. Never expose the
  gateway or API directly, or clients could forge their address.

## Production configuration validation (fail closed)
With `APP_ENV=production` the API refuses to start (import-time `ValidationError`, so
the container exits and stays unhealthy) and lists **all** problems when:
- `JWT_SECRET` or `TELEGRAM_WORKER_SECRET` is empty, a placeholder (`CHANGE_ME`,
  `replace-with…`, `example`, …) or shorter than 32 characters, or both are equal;
- `SECRET_ENCRYPTION_KEY` is set but not a valid Fernet key (empty is allowed: stored
  provider credentials are then disabled and return `503`);
- an AI provider is enabled with neither `AI_API_KEY` nor `SECRET_ENCRYPTION_KEY`, an
  `AI_API_KEY` placeholder is set, or STT is enabled without `STT_API_KEY`;
- `DATABASE_URL` is not PostgreSQL, has an empty/default/short (<16) password, or
  points to a non-local host (anything other than loopback, a Unix socket or a
  single-label Compose service name such as `db`) without
  `sslmode=require|verify-ca|verify-full` (`disable`, `allow`, `prefer` are refused);
- `DEBUG=true`; `CORS_ALLOWED_ORIGINS` contains `*`, `null` or an `http://` origin
  (CORS is disabled when empty, which is the Android default);
- `FORWARDED_ALLOW_IPS` contains `*`.
Unknown `APP_ENV` values (e.g. `prod`) are refused in every mode so a typo cannot skip
these checks. `scripts/init-environment.py` output plus the Compose overrides passes.

## Known static-analysis debt

`backend/app/geometry` is currently excluded from Ruff and mypy analysis, and its
code contains `type: ignore` comments. Passing those checks does not establish that
geometry is lint- or type-clean; addressing this debt requires a separate, reviewed
geometry change with appropriate golden tests.

## Persistence and recovery
Persist PostgreSQL, `/data/assets`, `/data/exports` and `/data/worker`. API/worker run
as UID 10001; writable volumes need appropriate ownership, not world-wide write access.
Worker mounts exports read-only. Protect and encrypt backups: they contain customer
records, photos, documents and chat linkage. Keep the provider encryption master key
separate from the encrypted database, with an owner-controlled recovery procedure.

1. Pause writes/worker ingestion or take a documented consistent snapshot.
2. `pg_dump -Fc` plus a consistent snapshot of assets, exports and worker state; record
   Alembic revision and checksums. Encrypt and retain an off-host copy.
3. Restore with `pg_restore --no-owner` into an isolated environment; restore permissions.
4. Verify counts, sample hashes, migrations and downloads before switching traffic.
   Prevent external Telegram replay while testing a restored pending-delivery queue.
5. Record recovery point/time and actual results. Owner production recovery is not yet verified.

Never blindly stamp or discard a legacy `create_all` database. Schema changes require a
reviewed Alembic migration. Do not automatically downgrade a production database as a
rollback; compatibility and data loss must be assessed first. Retention/cleanup for
exports, photos, pairing codes and worker retry payloads remains an open release task.
