"""Structural deployment gates (not a live deployment test)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_api_container_never_trusts_all_forwarders_and_debug_is_off():
    compose = yaml.safe_load((ROOT / 'deploy/compose.yml').read_text())
    env = compose['services']['api']['environment']
    assert env['APP_ENV'] == 'production'
    assert env['FORWARDED_ALLOW_IPS'] == '${FORWARDED_ALLOW_IPS:-127.0.0.1}'
    assert env['DEBUG'] == 'false'
    assert '*' not in env['CORS_ALLOWED_ORIGINS']
    assert compose['services']['gateway']['ports'] == ['127.0.0.1:8080:80']


def test_gateway_appends_forwarded_for_instead_of_passing_client_value():
    conf = (ROOT / 'deploy/gateway.conf').read_text()
    assert 'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' in conf
    assert '$http_x_forwarded_for' not in conf
