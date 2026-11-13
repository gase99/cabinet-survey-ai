# System architecture

## Approved baseline
- Client: Flutter/Dart for Android and Web, Material 3; Riverpod planned for state management.
- API: Python + FastAPI.
- Server persistence: PostgreSQL; local persistence: SQLite.
- AI: online multimodal provider adapter; credentials remain server-side.
- Image processing: OpenCV/OCR plus vision model; OCR is assistive, not authoritative.
- Drawing: deterministic geometry core and vector output (SVG); no LLM-generated final coordinates.
- Export: server-side PDF/PNG pipeline.
- Telegram: independent worker using Telegram Bot API.
- Deployment: Docker, HTTPS, managed secrets and backups.

## Logical flow
Flutter client -> FastAPI -> project/measurement, AI orchestration, geometry, export and delivery services. PostgreSQL stores synced records. SQLite stores local projects and a durable outbox. Sync uses versions and explicit conflict states.

## Trust boundaries
- Client is untrusted; authorization and validation are server-side.
- AI output is untrusted proposal data.
- Telegram updates and uploaded media are untrusted input.
- Secrets exist only in backend/worker secret stores.
- Customer images/contact data require access controls, retention policy and transport encryption.

## Canonical model
A project contains rooms, connected walls, openings/obstacles, observations, approvals, drawing versions, assets and audit events. Plan and wall elevations are projections of the same canonical geometry model.

## Deployment
Deploy API, PostgreSQL, background worker and Telegram integration as separately configurable services. The worker may share a host with the API but remains a separate process/container. Telegram itself is not the compute host.
