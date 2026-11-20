"""Register/inspect/delete this bot's webhook using official Telegram HTTPS API.
Run on the owner's secure machine with .env loaded. Never prints the token or URL
containing it. This script changes external bot configuration only when invoked.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def configuration(env):
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    secret = env.get('TELEGRAM_WEBHOOK_SECRET', '')
    url = env.get('TELEGRAM_WEBHOOK_URL', '')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token):
        raise ValueError('TELEGRAM_BOT_TOKEN is missing or malformed')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', secret):
        raise ValueError('TELEGRAM_WEBHOOK_SECRET must be 20-256 URL-safe characters')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('TELEGRAM_WEBHOOK_URL must be a public HTTPS URL without credentials/query')
    return token, secret, url


def call(token, method, payload=None):
    # Token stays in the HTTPS path as required by Telegram, never in argv/logs.
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}', data=data,
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Error descriptions may reflect upstream details; do not dump response/URL.
        raise RuntimeError(f'Telegram returned HTTP {error.code}; check deployment settings') from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('Telegram HTTPS request failed; check connectivity/TLS') from None
    if not result.get('ok'):
        raise RuntimeError(f'Telegram rejected {method} (error {result.get("error_code", "unknown")})')
    return result['result']


def main(env=None):
    env = os.environ if env is None else env
    action = sys.argv[1] if len(sys.argv) > 1 else 'set'
    if action not in {'set', 'info', 'delete'}:
        raise ValueError('Usage: configure-telegram.py [set|info|delete]')
    token, secret, url = configuration(env)
    if action == 'set':
        call(token, 'setWebhook', {'url': url, 'secret_token': secret,
             'allowed_updates': ['message'], 'max_connections': 8, 'drop_pending_updates': False})
        print('Webhook registered. Verify pending_update_count and last_error_date with info.')
    elif action == 'delete':
        call(token, 'deleteWebhook', {'drop_pending_updates': False})
        print('Webhook removed; queued updates were not dropped.')
    else:
        info = call(token, 'getWebhookInfo')
        print(json.dumps({key: info.get(key) for key in
              ['url', 'has_custom_certificate', 'pending_update_count', 'last_error_date', 'max_connections']}, indent=2))
        if info.get('last_error_message'):
            print('Telegram reports a delivery error. Inspect it securely in the official API response; not logged here.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
