# Backend

FastAPI service scaffold. Current implemented endpoints: `GET /` and `GET /health`. Domain, AI and geometry modules are initial boundaries only; authentication, persistence, project CRUD, AI providers, exports, sync and Telegram delivery are roadmap work, not yet implemented.

Run from repository root:
```bash
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```
