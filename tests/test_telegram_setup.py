import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('telegram_setup', ROOT / 'scripts/configure-telegram.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
ENV = {'TELEGRAM_BOT_TOKEN': '123456:fixture_token_not_real_abcdefghij',
       'TELEGRAM_WEBHOOK_SECRET': 'fixture_ingress_secret_at_least_20',
       'TELEGRAM_WEBHOOK_URL': 'https://api.example.org/telegram/webhook'}


def test_rejects_insecure_or_malformed_configuration():
    for key, value in [('TELEGRAM_BOT_TOKEN', ''), ('TELEGRAM_WEBHOOK_SECRET', 'short'),
                       ('TELEGRAM_WEBHOOK_URL', 'http://api.example.org/telegram/webhook'),
                       ('TELEGRAM_WEBHOOK_URL', 'https://user:secret@example.org/webhook')]:
        with pytest.raises(ValueError):
            setup.configuration({**ENV, key: value})
    assert setup.configuration(ENV)[2] == ENV['TELEGRAM_WEBHOOK_URL']


def test_set_webhook_sends_secret_not_token_in_public_url(monkeypatch, capsys):
    calls = []
    def call(token, method, payload=None):
        calls.append((token, method, payload))
        return {}
    monkeypatch.setattr(setup, 'call', call)
    monkeypatch.setattr(sys, 'argv', ['configure-telegram.py', 'set'])
    setup.main(ENV)
    assert calls[0][1] == 'setWebhook'
    assert calls[0][2]['secret_token'] == ENV['TELEGRAM_WEBHOOK_SECRET']
    assert calls[0][2]['url'] == ENV['TELEGRAM_WEBHOOK_URL']
    assert calls[0][2]['drop_pending_updates'] is False
    assert ENV['TELEGRAM_BOT_TOKEN'] not in capsys.readouterr().out


class Response:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps({'ok': True, 'result': {'pending_update_count': 0}}).encode()


def test_official_https_api_and_redacted_errors(monkeypatch, capsys):
    requests = []
    def urlopen(request, timeout):
        requests.append(request)
        return Response()
    monkeypatch.setattr(setup.urllib.request, 'urlopen', urlopen)
    assert setup.call(ENV['TELEGRAM_BOT_TOKEN'], 'getWebhookInfo') == {'pending_update_count': 0}
    assert requests[0].full_url == 'https://api.telegram.org/bot'+ENV['TELEGRAM_BOT_TOKEN']+'/getWebhookInfo'
    def fail(request, timeout):
        raise setup.urllib.error.HTTPError(request.full_url, 401, ENV['TELEGRAM_BOT_TOKEN'], {}, None)
    monkeypatch.setattr(setup.urllib.request, 'urlopen', fail)
    with pytest.raises(RuntimeError) as error:
        setup.call(ENV['TELEGRAM_BOT_TOKEN'], 'setWebhook', {})
    assert ENV['TELEGRAM_BOT_TOKEN'] not in str(error.value)
