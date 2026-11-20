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

## ADR-007: Local-first voice intake and three-source unification (فاز صوت)
Status: accepted, 2026-11-14, phase 1 of the local-first product decision set.
Scope of this phase:

- **Local-first:** project data stays on-device (native SQLite). No automatic cloud
  sync of project data; manual "Sync" against the user's own backend remains an
  explicit operation, unchanged. Permanent storage lifecycle and encryption at rest
  are later phases of the same decision set, not silently changed here.
- **Three input methods, one workflow:** image/sketch analysis (`ai/sketch-analysis`),
  spoken measurements (`ai/transcription` + typed/pasted transcript via
  `ai/parse-text`) and manual entry all feed the same confirm-first forms. Different
  sources never outrank each other automatically: conflicts are surfaced
  (`conflicting_values`) and the user resolves them.
- **Speech recognition is provider-independent and optional:** an
  OpenAI-compatible HTTPS STT endpoint is configurable server-side; without
  credentials the API fails closed (503) with a clear message and the typed-text
  path stays fully functional. When audio is processed by an external provider the
  API response carries `external_transmission: true` and a user-facing notice.
- **Spoken parsing is deterministic, Persian-first:** word numerals, compound
  measurements ("سه متر و بیست سانتی‌متر" → 3200 mm), scale words, corrections
  ("نه، …" → correction intent) and conflicts are extracted with their exact spoken
  source quote. Missing units stay questions (`missing_unit`); values are never
  invented and coordinates are never produced by the parser.
- **Human confirmation is structural:** voice proposals prefill the same manual
  forms; a voice-sourced new wall is stored as `voice_ai`/`needs_review` and must be
  approved exactly like sketch proposals. Corrections go through the normal edit
  path so previous observations remain in revision history.
- **On-device audio capture is deferred:** recording (RECORD_AUDIO) changes the
  Android permission posture and needs real-device acceptance, so phase 1 ships the
  transcript/text path only. This is an explicit, documented limitation.
