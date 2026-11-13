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
