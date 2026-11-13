# Local development

## Prerequisites
Git, Python 3.11+, Docker Engine/Desktop, Flutter stable SDK with Android and Web toolchains for client work.

## Backend
```bash
cp .env.example .env
docker compose up -d db
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload
```
Health: `http://127.0.0.1:8000/health`; OpenAPI: `http://127.0.0.1:8000/docs`.

## Flutter
```bash
cd apps/client
flutter create . --platforms=android,web
flutter pub get
flutter run -d chrome
```
Review generated platform files before committing. Android builds require Android SDK/toolchain.

## Tests
```bash
cd backend
pytest -q
```

Do not use production credentials locally. Keep `.env` untracked.

## Implemented backend and migration workflow
Use Python 3.11+, a venv and `pip install -r backend/requirements.txt`. In `backend/`:

```sh
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest -q
```

Settings load `.env` relative to the process working directory. Export settings as
environment variables or place a private `.env` in the correct directory. Do not
run production against the default SQLite URL. Production startup does not create
schema automatically; the container entrypoint runs Alembic first. Production
rejects default JWT secrets, SQLite and wildcard CORS.

For client bootstrap/build, follow `apps/client/README.md`. Browser API URLs must be
same-origin/proxied or explicit remote HTTPS, never sandbox-local loopback. Backend
and worker tests run independently:

```sh
cd services/telegram-bot
PYTHONPATH=. pytest -q
```

Current sandbox lacks Flutter/Dart, Java, Android SDK and Docker. GitHub Actions is
used for remote Flutter gates and PostgreSQL migration verification. No local
Android/Web build is claimed.
