# Architecture decision records

## ADR-001: Flutter for Android and Web
Status: accepted. One client codebase for both approved platforms; web usability must be tested independently.

## ADR-002: Online AI behind provider abstraction
Status: accepted. Vision/LLM providers are replaceable; API keys remain server-side. AI returns proposed observations only.

## ADR-003: Deterministic geometry
Status: accepted. Canonical approved measurement data drives both plan and wall elevations. LLMs do not own final coordinates.

## ADR-004: Offline-first field capture
Status: accepted. SQLite and an outbox support disconnected measurement capture and drawing previews.

## ADR-005: Telegram bot hosting
Status: accepted. Bot application runs on external user-controlled compute and communicates with Telegram Bot API. Telegram infrastructure is not general-purpose app hosting.
