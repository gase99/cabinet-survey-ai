# Cabinet Survey AI

AI-assisted field surveying and 2D documentation for cabinet makers.

> **Status:** Initial architecture/scaffold, not a feature-complete product. See the roadmap for implementation phases.

## Approved scope
- Android + Web client using Flutter/Dart; Persian RTL and English.
- Offline-first customer/project capture, rooms, walls, dimensions, obstacles, photos and notes.
- Online multimodal AI for text, voice transcripts and annotated hand sketches.
- Human review and explicit approval before extracted values become authoritative.
- Deterministic geometry engine generating a top-down plan and individual wall elevations from one canonical model.
- FastAPI backend, PostgreSQL server storage, SQLite local storage, PDF/PNG export and Telegram delivery.

## Telegram hosting clarification
Telegram provides the Bot API; it does **not** host arbitrary customer bot application code. The bot worker must run on a VPS, Docker host or managed cloud runtime controlled by the project owner and communicate with Telegram over HTTPS. See [Telegram deployment](docs/telegram-deployment.md).

## Repository map
- `apps/client`: Flutter Android/Web app.
- `backend`: FastAPI API and domain services.
- `services/telegram-bot`: separately deployable Telegram integration worker.
- `packages`: shared contracts and geometry core.
- `docs`: architecture, requirements, data, AI, geometry, security and operations.
- `test_fixtures`: anonymized inputs and golden outputs.

## Quick start (backend scaffold)
1. Copy `.env.example` to `.env`; never commit real credentials.
2. Start PostgreSQL: `docker compose up -d db`.
3. Install `backend/requirements.txt` in a Python 3.11+ virtual environment.
4. Run: `uvicorn app.main:app --app-dir backend --reload`.
5. Visit `http://127.0.0.1:8000/health`.

The Flutter client is a foundation scaffold. Follow [local development](docs/local-development.md).

## Non-negotiable rules
- Store canonical dimensions as integer millimetres.
- Never infer real-world scale from sketch pixels alone.
- AI proposes observations; it never silently fills missing dimensions or publishes final engineering drawings.
- User approval is mandatory before extracted values become approved data.
- Deterministic geometry, not an LLM, owns coordinates and drawings.
- Plan and wall elevations share one canonical geometry model.
- Preserve provenance, source regions, confidence, review status and edit history.
- Keep provider credentials and Telegram tokens server-side.
- Offline capture and geometry must work without AI/network access.

See [roadmap](docs/development-roadmap.md) and [agent instructions](AGENTS.md).
