#!/usr/bin/env bash
# Local development only; no network listener beyond this device.
set -euo pipefail
if [[ ${PERSONAL_SERVER_HOST:-127.0.0.1} != 127.0.0.1 ]]; then
  echo 'Refusing non-loopback bind: PERSONAL_SERVER_HOST must be 127.0.0.1' >&2
  exit 2
fi
if [[ ${APP_ENV:-development} != development ]]; then
  echo 'Refusing to run: personal server requires APP_ENV=development' >&2
  exit 2
fi
if (( $# )); then
  echo 'This script accepts no arguments; the host is fixed to 127.0.0.1.' >&2
  exit 2
fi
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
DATA="$ROOT/var/data/personal"
umask 077
mkdir -p "$DATA"
# Keep personal secrets separate from any deployment .env; never replace them.
if [[ ! -e "$DATA/.env" ]]; then
  cp "$ROOT/.env.example" "$DATA/.env.example"
  python - "$ROOT/scripts/init-environment.py" "$DATA" <<'PY'
import importlib.util
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('init_environment', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.initialize(Path(sys.argv[2]))
PY
  rm "$DATA/.env.example"
  echo 'Created private personal .env (keep it for future runs).'
fi
cd "$ROOT/backend"
# The final env command overrides both the caller and dotenv, including an edited .env.
# Never source .env as shell code. Explicit paths avoid /data defaults from the template.
run_personal() {
  python -m dotenv -f "$DATA/.env" run -- env \
    APP_ENV=development DATABASE_URL="sqlite:///$DATA/cabinet_survey.db" \
    ASSET_STORAGE_DIR="$DATA/assets" EXPORT_STORAGE_DIR="$DATA/exports" "$@"
}
run_personal python -m alembic upgrade head
echo 'Personal development server: http://127.0.0.1:8000 (stop with Ctrl+C).'
exec python -m dotenv -f "$DATA/.env" run -- env -u UVICORN_FD -u UVICORN_UDS \
  APP_ENV=development DATABASE_URL="sqlite:///$DATA/cabinet_survey.db" \
  ASSET_STORAGE_DIR="$DATA/assets" EXPORT_STORAGE_DIR="$DATA/exports" \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
