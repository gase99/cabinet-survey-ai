import importlib.util
from pathlib import Path
import stat

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('environment_setup',ROOT/'scripts/init-environment.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


def test_private_distinct_secrets_and_no_overwrite(tmp_path):
    (tmp_path/'.env.example').write_text((ROOT/'.env.example').read_text())
    values=setup.initialize(tmp_path)
    target=tmp_path/'.env'
    assert stat.S_IMODE(target.stat().st_mode)==0o600
    assert values['TELEGRAM_WEBHOOK_SECRET']!=values['TELEGRAM_WORKER_SECRET']
    assert values['POSTGRES_PASSWORD'] in values['DATABASE_URL']
    assert len(values['JWT_SECRET'])>=32
    original=target.read_bytes()
    try: setup.initialize(tmp_path)
    except FileExistsError: pass
    else: raise AssertionError('Existing secrets must not be overwritten')
    assert target.read_bytes()==original
    assert 'TELEGRAM_BOT_TOKEN=\n' in target.read_text()

