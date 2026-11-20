"""Create a private local .env once. Never overwrite or print generated secrets."""
import base64
import os
from pathlib import Path
import secrets


def initialize(root):
    target = root / '.env'
    if target.exists():
        raise FileExistsError('.env already exists; refusing to overwrite it')
    text = (root / '.env.example').read_text()
    password = secrets.token_hex(24)
    values = {
        'POSTGRES_PASSWORD': password,
        'DATABASE_URL': f'postgresql+psycopg://cabinet:{password}@localhost:5432/cabinet_survey',
        'JWT_SECRET': secrets.token_urlsafe(48),
        'SECRET_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'TELEGRAM_WEBHOOK_SECRET': secrets.token_urlsafe(32),
        'TELEGRAM_WORKER_SECRET': secrets.token_urlsafe(32),
    }
    for key, value in values.items():
        text = '\n'.join(f'{key}={value}' if line.startswith(key+'=') else line for line in text.splitlines())+'\n'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(text)
    return values


if __name__ == '__main__':
    try:
        initialize(Path(__file__).resolve().parents[1])
    except FileExistsError as error:
        raise SystemExit(str(error))
    print('Created private .env. Add your bot token and real HTTPS domain before deployment; no secrets were printed.')
