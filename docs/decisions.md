# Architecture decision records

## ADR-001: Flutter for Android and Web
Status: **superseded by ADR-006** on 2026-11-14 at the owner's request.

## ADR-002: Online AI behind provider abstraction
Status: accepted. Providers are replaceable; keys remain server-side. AI returns proposed observations only.

## ADR-003: Deterministic geometry
Status: accepted. Canonical approved measurements drive plan and wall elevations. LLMs do not own final coordinates.

## ADR-004: Offline-first field capture
Status: accepted. Native Android SQLite and a transactional outbox support disconnected capture and local previews.

## ADR-005: Telegram bot hosting
Status: accepted. Bot application runs on owner-controlled compute and communicates with Telegram Bot API. Telegram is not general-purpose app hosting.

## ADR-006: Cancel web; Android is the only client
Status: accepted, 2026-11-14, explicit owner direction. Remove browser dependencies,
web builds/acceptance/deployment and browser CORS configuration. Commit Android platform
sources, scoped-storage document saving, explicit API endpoint configuration and owner
signing support. Keep FastAPI/nginx as an API/webhook gateway, not a web client host.
Historical Android/Web reports remain marked historical, not current evidence.
This scope completes packaging work, not every unfinished product feature or release gate.
Phase-boundary user approval remains required.
