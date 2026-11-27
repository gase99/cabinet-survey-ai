import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/run-personal-server.sh'


def run_with(**values):
    env = os.environ.copy()
    env.pop('PERSONAL_SERVER_HOST', None)
    env.pop('APP_ENV', None)
    env.update(values)
    return subprocess.run(['bash', str(SCRIPT)], env=env, text=True, capture_output=True, timeout=5)


def test_refuses_non_loopback_before_doing_any_work():
    for host in ('0.0.0.0', '192.168.1.1', 'localhost', '::'):
        result = run_with(PERSONAL_SERVER_HOST=host)
        assert result.returncode == 2
        assert 'Refusing non-loopback' in result.stderr


def test_refuses_production_and_other_non_development_environments():
    for mode in ('production', 'test', 'prod'):
        result = run_with(APP_ENV=mode)
        assert result.returncode == 2
        assert 'requires APP_ENV=development' in result.stderr


def test_runtime_overrides_file_and_parent_environment():
    script = SCRIPT.read_text()
    assert script.count('APP_ENV=development DATABASE_URL=') == 2
    assert '--host 127.0.0.1 --port 8000' in script
    assert '0.0.0.0' not in script


def test_migrations_and_server_are_forced_to_development_with_host_fixed(tmp_path):
    import shutil

    root = tmp_path / 'checkout'
    (root / 'scripts').mkdir(parents=True)
    (root / 'backend').mkdir()
    (root / 'var/data/personal').mkdir(parents=True)
    shutil.copy(SCRIPT, root / 'scripts/run-personal-server.sh')
    (root / 'var/data/personal/.env').write_text('APP_ENV=production\nDATABASE_URL=postgresql://example\n')
    fakebin = tmp_path / 'bin'
    fakebin.mkdir()
    fakepython = fakebin / 'python'
    fakepython.write_text('''#!/usr/bin/env bash
set -eu
if [[ "$1" == -m && "$2" == dotenv ]]; then
  shift 6
  # Simulate dotenv overriding the parent with the existing file's production value.
  export APP_ENV=production DATABASE_URL=postgresql://example
  exec "$@"
fi
printf '%s|%s|%s\\n' "$APP_ENV" "$DATABASE_URL" "$*" >> "$TRACE"
''')
    fakepython.chmod(0o755)
    trace = tmp_path / 'trace'
    env = os.environ.copy()
    env.update(PATH=f'{fakebin}:{env["PATH"]}', TRACE=str(trace), APP_ENV='development', DATABASE_URL='postgresql://parent')
    env.pop('PERSONAL_SERVER_HOST', None)
    result = subprocess.run(['bash', str(root / 'scripts/run-personal-server.sh')], env=env, text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    calls = trace.read_text().splitlines()
    assert len(calls) == 2
    assert all(line.startswith(f'development|sqlite:///{root}/var/data/personal/cabinet_survey.db|') for line in calls)
    assert '-m alembic upgrade head' in calls[0]
    assert '-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers' in calls[1]
