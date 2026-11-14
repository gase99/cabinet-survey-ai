# Agent instructions

## Product invariants
- Platforms: Android + Web. Client: Flutter/Dart; backend: FastAPI.
- Support Persian RTL and English.
- Persist all dimensions as integer millimetres; convert only at UI/API boundaries.
- AI output is untrusted proposal data. Confidence is never approval.
- Never guess missing measurements or infer scale from sketch pixels.
- Never let an LLM generate authoritative drawing coordinates.
- Deterministic geometry generates both plan and elevations from one shared model.
- Offline project capture and geometry must work without network.
- Telegram bot application runs on external user-controlled compute and uses Telegram Bot API.
- Secrets must never enter source, client bundles, logs, fixtures or documentation.

## Workflow
- Read relevant docs before changing architecture.
- Work through roadmap phases autonomously; ask only for genuine blockers, requirement changes or external authorization.
- Add tests for every behavior change; geometry changes require golden fixtures.
- Preserve original observations and append revisions; never silently overwrite approved measurements.
- Do not claim a feature is implemented based on a stub, mock or documentation.
- Run relevant tests, formatting and static analysis; report exact commands and results.
- Ask before changing approved product decisions or introducing paid infrastructure/providers.

## Repository map
- `apps/client`: Flutter Android/Web client.
- `backend/app`: FastAPI API and domain services.
- `services/telegram-bot`: Telegram integration worker.
- `packages`: shared contracts and geometry.
- `docs`: product and engineering documentation.
- `test_fixtures`: anonymized inputs and golden outputs.
