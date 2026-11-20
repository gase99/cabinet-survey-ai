# API specification outline

Base path: `/api/v1`. OpenAPI is generated from FastAPI schemas.

## Planned resources
- `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- `/customers`, `/projects`, `/projects/{id}`
- `/projects/{id}/rooms`, `/rooms/{id}/walls`, `/walls/{id}/elements`
- `/assets`, `/ai/sketch-analysis`, `/ai/transcription`
- `/reviews/{id}/approve`, `/reviews/{id}/reject`
- `/drawings/{project_id}/plan`, `/drawings/{project_id}/elevations`
- `/exports`, `/deliveries/telegram`
- `/sync/push`, `/sync/pull`

## API rules
- **Client domain write path:** The Flutter Android client mutates survey domain entities exclusively via `POST /api/v1/sync/push` (never direct REST `PUT`/`DELETE`). Direct REST `PUT` endpoints require `version`/`base_version` or `If-Match` and return `409` on stale writes; all `DELETE` endpoints perform soft deletes (`is_deleted=true`) and emit tombstones on `GET /api/v1/sync/pull`.
- **Idempotency:** `POST /api/v1/exports/{project_id}` and `POST /api/v1/telegram/send` honor the `Idempotency-Key` header with TTL expiry (`IDEMPOTENCY_TTL_SECONDS`): identical key + body replays the stored response; identical key + different body returns `422`.
- **Rate limits & audit:** Per-user `RATE_LIMIT_AI_PER_MINUTE` enforced across `/ai/parse-text`, `/ai/sketch-analysis`, and `/ai/transcription` (`429` + `Retry-After`). Append-only server audit log exposed to admins at `GET /api/v1/admin/audit`.
- **AI provenance & approval gate:** AI candidates are persisted separately in `observations` (`/ai/candidates`) with source, region, `prompt_id`, `confidence`, `model_name`, `review_status`, and optional link to `walls`/`elements`; confidence never approves anything, and measurements become `approved` only via `POST /walls/{id}/approve` or `POST /elements/{id}/approve`.
- **Units & tenant isolation:** Tenant/user authorization on every project-scoped request; integer millimetres (`*_mm`) everywhere; typed validation errors.
