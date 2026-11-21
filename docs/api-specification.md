# API specification outline

Base path: `/api/v1` (plus root probe routes `/health` and `/ready`). OpenAPI is generated from FastAPI schemas.

## Endpoints
- Probes: `GET /health` (cheap process liveness, no DB query), `GET /ready` (executes `SELECT 1`; returns `200` when DB is healthy and `503` on failure)
- Auth: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`
- Projects & survey: `/customers`, `/projects`, `/projects/{id}`, `/projects/{id}/rooms`, `/rooms/{id}/walls`, `/walls/{id}/elements`
- Approvals & revisions: `POST /walls/{id}/approve`, `POST /elements/{id}/approve`, `GET /walls/{id}/revisions`, `GET /elements/{id}/revisions`
- AI & assets: `/assets`, `/ai/parse-text`, `/ai/sketch-analysis`, `/ai/transcription`, `/ai/candidates`, `/ai/candidates/{id}`
- Drawings & exports: `/drawings/{project_id}/plan`, `/drawings/{project_id}/elevations`, `/exports`, `POST /exports/{project_id}`, `GET /exports/{id}` (status), `GET /exports/{id}/download`
- **Background exports:** `POST /exports/{project_id}` validates synchronously — every
  non-deleted room of the project is included; unapproved/incomplete walls or elements
  in *any* room return `409` unless `exclude_unapproved` (elements only; walls still
  `409`) or `flag_unapproved` is explicitly set (both together: `422`); invalid geometry
  `400`. On success it returns **`202`** with `{id, status: "queued", status_url,
  download_url, excluded_items, flagged_items}`. Rendering runs after the response.
  `GET /exports/{id}` reports `queued`, `running`, `done` or `failed` (+ `error_message`).
  `GET /exports/{id}/download` returns the file only when `done`, otherwise `409` with
  the current status. Audit: `export.create` (queued), then `export.complete` or
  `export.fail`. A failed render releases its Idempotency-Key so the same key can retry.
- **Export output:** PDF pages use only the bundled Vazirmatn font (Persian shaped, RTL
  ordered) and draw each view at a stated standard scale (e.g. `Scale 1:20 on A4`) with a
  scale bar; PNG is a fitted overview, not to scale. See `docs/export-output.md`.
- Telegram: client routes `/telegram/{pairing-code,link-status,unlink,send,deliveries}`; internal worker-only routes `/telegram/{verify-pairing,internal/pending-deliveries,internal/deliveries/{id},internal/delivery-result}` (denied at the public gateway); `POST /api/v1/telegram/webhook` is intentionally disabled (`501`, gateway `404`) because public Bot API webhooks route to `services/telegram-bot` (`POST /telegram/webhook` -> worker `:8081/webhook`)
- Offline sync & admin: `/sync/push`, `/sync/pull`, `/sync/conflicts`, `/admin/{users,ai-config,ai-usage,audit,health}`

## API rules
- **Client domain write path:** The Flutter Android client mutates survey domain entities exclusively via `POST /api/v1/sync/push` (never direct REST `PUT`/`DELETE`). Direct REST `PUT` endpoints require `version`/`base_version` or `If-Match` and return `409` on stale writes; all `DELETE` endpoints perform soft deletes (`is_deleted=true`) and emit tombstones on `GET /api/v1/sync/pull`.
- **Idempotency:** `POST /api/v1/exports/{project_id}` and `POST /api/v1/telegram/send` honor the `Idempotency-Key` header with TTL expiry (`IDEMPOTENCY_TTL_SECONDS`) and atomic DB unique-constraint reservation (`uq_idempotency_owner_scope_key`): concurrent or sequential requests with the same key + body create at most one `ExportJob` / `TelegramDelivery` and replay the stored response; identical key + different body returns `422`.
- **Rate limits & audit:** Per-user `RATE_LIMIT_AI_PER_MINUTE` is enforced over a **60-second sliding window** across `/ai/parse-text`, `/ai/sketch-analysis`, and `/ai/transcription` (preventing 2× boundary bursts and returning `429` with an exact `Retry-After` header). Auth endpoints enforce `RATE_LIMIT_AUTH_PER_MINUTE`. Append-only server audit log is exposed to admins at `GET /api/v1/admin/audit`.
- **AI provenance & approval gate:** AI candidates are persisted separately in `observations` (`/ai/candidates`) with source, region, `prompt_id`, `confidence`, `model_name`, `review_status`, and optional link to `walls`/`elements`; confidence never approves anything, measurements become `approved` only via explicit user approval (`POST /walls/{id}/approve`, `POST /elements/{id}/approve`, or explicit sync approval), and un-approving, editing-after-approval, or soft-deleting a wall or element resets its linked `Observation` back to `needs_review`.
- **Units & tenant isolation:** Tenant/user authorization on every project-scoped request; integer millimetres (`*_mm`) everywhere; typed validation errors.
