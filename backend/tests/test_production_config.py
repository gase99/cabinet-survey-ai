"""Production configuration must fail closed: the app refuses to start when unsafe."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
SAFE = {
    'app_env': 'production',
    'jwt_secret': 'J' * 20 + 'x9Qm4tVb7sLk2nPw',
    'telegram_worker_secret': 'W' * 20 + 'r8Hd3fGz6cYe1aUo',
    'database_url': 'postgresql+psycopg://cabinet:3f9a1c7e5b2d4f6a8c0e@db:5432/cabinet_survey',
}


def build(**overrides):
    return Settings(_env_file=None, **{**SAFE, **overrides})  # type: ignore[call-arg]


def refused(match: str, **overrides):
    with pytest.raises(ValidationError, match=match):
        build(**overrides)


def test_safe_production_configuration_is_accepted():
    config = build()
    assert config.app_env == 'production' and config.debug is False


def test_production_refuses_default_secrets_and_sqlite():
    with pytest.raises(ValidationError):
        Settings(app_env='production', _env_file=None)  # type: ignore[call-arg]
    refused('JWT_SECRET', jwt_secret='replace-with-a-long-random-secret-change-me')
    refused('JWT_SECRET', jwt_secret='CHANGE_ME_AT_LEAST_32_RANDOM_CHARACTERS')
    refused('JWT_SECRET', jwt_secret='')
    refused('JWT_SECRET', jwt_secret='short-but-random-1234')
    refused('PostgreSQL', database_url='sqlite:///./prod.db')


def test_production_refuses_empty_or_default_worker_secret():
    refused('TELEGRAM_WORKER_SECRET', telegram_worker_secret=None)
    refused('TELEGRAM_WORKER_SECRET', telegram_worker_secret='')
    refused('TELEGRAM_WORKER_SECRET', telegram_worker_secret='CHANGE_ME' * 5)
    refused('must differ', telegram_worker_secret=SAFE['jwt_secret'])


def test_production_refuses_invalid_encryption_key_but_allows_empty():
    refused('SECRET_ENCRYPTION_KEY', secret_encryption_key='not-a-fernet-key')
    assert build(secret_encryption_key=None).secret_encryption_key is None
    assert build(secret_encryption_key=Fernet.generate_key().decode()).secret_encryption_key


def test_production_refuses_enabled_providers_without_credentials():
    refused('AI_PROVIDER is enabled', ai_provider='openai_compatible')
    refused('AI_API_KEY is a placeholder', ai_api_key='your-api-key')
    refused('STT_API_KEY', stt_provider='openai_compatible', stt_api_key='')
    assert build(ai_provider='openai_compatible', secret_encryption_key=Fernet.generate_key().decode())


def test_production_refuses_wildcard_or_insecure_cors():
    refused('wildcard', cors_allowed_origins='*')
    refused('wildcard', cors_allowed_origins='https://ok.example.org, https://*.example.org')
    refused('wildcard', cors_allowed_origins='null')
    refused('https://', cors_allowed_origins='http://admin.example.org')
    assert build(cors_allowed_origins='https://admin.example.org').cors_origins() == ['https://admin.example.org']


def test_production_refuses_debug():
    refused('DEBUG must be false', debug=True)


def test_production_refuses_wildcard_forwarded_trust():
    refused('FORWARDED_ALLOW_IPS', forwarded_allow_ips='*')
    assert build(forwarded_allow_ips='172.28.0.0/16').forwarded_allow_ips == '172.28.0.0/16'


@pytest.mark.parametrize('url, reason', [
    ('postgresql+psycopg://cabinet:@db:5432/c', 'password'),
    ('postgresql+psycopg://cabinet@db:5432/c', 'password'),
    ('postgresql+psycopg://cabinet:CHANGE_ME@db:5432/c', 'password'),
    ('postgresql+psycopg://postgres:postgres@db:5432/c', 'password'),
    ('postgresql+psycopg://cabinet:3f9a1c7e5b2d4f6a8c0e@db.example.org:5432/c', 'requires sslmode'),
    ('postgresql+psycopg://cabinet:3f9a1c7e5b2d4f6a8c0e@10.0.0.5:5432/c?sslmode=prefer', 'insecure'),
    ('postgresql+psycopg://cabinet:3f9a1c7e5b2d4f6a8c0e@db.example.org/c?sslmode=disable', 'insecure'),
])
def test_production_refuses_insecure_database_url(url, reason):
    refused(reason, database_url=url)


def test_production_accepts_tls_remote_and_internal_database_hosts():
    pw = '3f9a1c7e5b2d4f6a8c0e'
    for url in [f'postgresql+psycopg://cabinet:{pw}@db.example.org:5432/c?sslmode=verify-full',
                f'postgresql+psycopg://cabinet:{pw}@10.0.0.5/c?sslmode=require',
                f'postgresql+psycopg://cabinet:{pw}@localhost/c', f'postgresql+psycopg://cabinet:{pw}@db/c']:
        assert build(database_url=url)


def test_unknown_environment_name_fails_closed():
    with pytest.raises(ValidationError, match='APP_ENV'):
        Settings(_env_file=None, app_env='prod')  # type: ignore[call-arg]


def test_all_problems_are_reported_together():
    with pytest.raises(ValidationError) as error:
        build(jwt_secret='', debug=True, cors_allowed_origins='*')
    text = str(error.value)
    assert 'JWT_SECRET' in text and 'DEBUG' in text and 'CORS' in text


def test_generated_environment_with_compose_overrides_is_accepted(tmp_path):
    spec = importlib.util.spec_from_file_location('environment_setup', ROOT / 'scripts/init-environment.py')
    assert spec and spec.loader
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    (tmp_path / '.env.example').write_text((ROOT / '.env.example').read_text())
    values = setup.initialize(tmp_path)
    compose_url = f"postgresql+psycopg://cabinet:{values['POSTGRES_PASSWORD']}@db:5432/cabinet_survey"
    config = Settings(_env_file=str(tmp_path / '.env'), app_env='production',  # type: ignore[call-arg]
                      database_url=compose_url)
    assert config.app_env == 'production'


def test_application_process_refuses_to_start_with_unsafe_production_config():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('JWT_', 'DATABASE_', 'TELEGRAM_', 'DEBUG'))}
    env.update({'APP_ENV': 'production', 'JWT_SECRET': 'CHANGE_ME_AT_LEAST_32_RANDOM_CHARACTERS'})
    result = subprocess.run([sys.executable, '-c', 'import app.main'], check=False, cwd=ROOT / 'backend', env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert 'Refusing to start in production' in result.stderr
