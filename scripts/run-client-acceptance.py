"""Disposable real HTTP server runner. No external integrations or customer data."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
mode=sys.argv[1] if len(sys.argv)>1 else '--native'
if mode != '--native':
    raise SystemExit('Only Android/native Dart acceptance is supported; web is cancelled')
with tempfile.TemporaryDirectory(prefix='cabinet-acceptance-') as temp:
    env={**os.environ,'DATABASE_URL':f'sqlite:///{temp}/server.sqlite',
         'AI_PROVIDER':'disabled','TELEGRAM_WORKER_SECRET':'',
         'EXPORT_STORAGE_DIR':f'{temp}/exports','ASSET_STORAGE_DIR':f'{temp}/assets',
         'PYTHONPATH':os.pathsep.join([str(ROOT/'backend'),str(ROOT/'scripts')])}
    with open(f'{temp}/server.log','w+') as log:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','acceptance_server:app','--host','0.0.0.0',
            '--port','8173','--no-access-log'],env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError('Acceptance API exited')
                try:
                    urllib.request.urlopen('http://127.0.0.1:8173/health',timeout=1);break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('Acceptance API not ready')
            command=['flutter','test','test/workflow_acceptance_test.dart',
                '--dart-define=ACCEPTANCE_API_URL=http://127.0.0.1:8173/api/v1/','--reporter','expanded']
            subprocess.run(command,cwd=ROOT/'apps/client',env=os.environ,check=True)
        except Exception:
            log.flush();log.seek(0);print(log.read());raise
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
