"""Destructive only to a clearly named, disposable CI restore DB; never production.
Docker PostgreSQL tools are version-matched to the service image. Asset archives
are fixture-only. This is a recovery mechanism test, not an owner's recovery drill.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from sqlalchemy import create_engine,select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from PIL import Image
from app.models.db_models import User,Project,Asset

url=make_url(os.environ['DATABASE_URL'])
if os.environ.get('ACCEPTANCE_DISPOSABLE_DATABASE')!='1' or url.database!='cabinet_test' or url.host not in {'localhost','127.0.0.1'} or url.username!='fixture':
    raise SystemExit('Refusing restore drill outside the disposable CI fixture database')
container=os.environ['PG_CONTAINER']
restore='cabinet_restore_fixture'
engine=create_engine(url)
with tempfile.TemporaryDirectory(prefix='restore-drill-') as temporary:
    root=Path(temporary)
    assets=root/'assets';assets.mkdir()
    image=io.BytesIO();Image.new('RGB',(16,16),'white').save(image,'PNG')
    (assets/'fixture.png').write_bytes(image.getvalue())
    expected=hashlib.sha256(image.getvalue()).hexdigest()
    with Session(engine) as db:
        user=User(email='restore-fixture@example.com',display_name='Recovery fixture',hashed_password='not-an-authenticatable-fixture-hash')
        db.add(user);db.flush()
        project=Project(owner_id=user.id,title='Recovery fixture')
        db.add(project);db.flush()
        asset=Asset(owner_id=user.id,project_id=project.id,filename='fixture.png',content_type='image/png',size_bytes=len(image.getvalue()),storage_path='/data/assets/fixture.png')
        db.add(asset);db.commit();pid=project.id;aid=asset.id
    archive=root/'assets.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:tar.add(assets,arcname='assets')
    dump=subprocess.check_output(['docker','exec',container,'pg_dump','-U','fixture','-d','cabinet_test','-Fc'])
    subprocess.run(['docker','exec',container,'createdb','-U','fixture',restore],check=True)
    try:
        subprocess.run(['docker','exec','-i',container,'pg_restore','--exit-on-error','--no-owner','-U','fixture','-d',restore],input=dump,check=True)
        restored_engine=create_engine(url.set(database=restore))
        with Session(restored_engine) as db:
            assert db.get(Project,pid).title=='Recovery fixture'
            restored_asset=db.get(Asset,aid)
            assert restored_asset.project_id==pid and restored_asset.storage_path=='/data/assets/fixture.png'
        restored_engine.dispose()
        destination=root/'restored';destination.mkdir()
        with tarfile.open(archive) as tar:tar.extractall(destination,filter='data')
        assert hashlib.sha256((destination/'assets/fixture.png').read_bytes()).hexdigest()==expected
        report={'status':'PASS','scope':'Isolated PostgreSQL custom-format dump/restore and fixture asset checksum',
            'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'dump_bytes':len(dump),'asset_sha256':expected,
            'limitations':['Not a production backup recovery drill','No production/customer data or external delivery']}
        Path('/tmp/acceptance-restore.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        subprocess.run(['docker','exec',container,'dropdb','-U','fixture',restore],check=True)
        engine.dispose()
