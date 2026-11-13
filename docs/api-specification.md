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
Tenant/user authorization on every project-scoped request; convert units to integer mm at boundaries; idempotency keys for uploads/exports/delivery; optimistic concurrency with entity versions; typed validation errors; documented pagination, rate limits, upload limits and retention.
