import asyncio
import json
import sqlite3
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from worker import Config, Worker, create_app


def config(tmp_path):
    root=tmp_path/'exports';root.mkdir(exist_ok=True)
    return Config('test-token-not-a-real-credential','test-webhook-secret-at-least-20',
                  'test-backend-secret-at-least-20','http://backend/api/v1/',root,str(tmp_path/'worker.sqlite'))


def test_webhook_auth_durable_deduplication(tmp_path,monkeypatch):
    async def no_loop(self):
        await asyncio.Event().wait()
    monkeypatch.setattr(Worker,'loop',no_loop)
    app=create_app(config(tmp_path))
    with TestClient(app) as client:
        assert client.post('/webhook',json={'update_id':123}).status_code==401
        headers={'X-Telegram-Bot-Api-Secret-Token':app.state.worker.config.webhook_secret}
        assert client.post('/webhook',headers=headers,json={'bad':'payload'}).status_code==422
        for _ in range(2): assert client.post('/webhook',headers=headers,json={'update_id':123}).status_code==200
        with sqlite3.connect(str(tmp_path/'worker.sqlite')) as check:
            assert check.execute('SELECT count(*) FROM updates').fetchone()[0]==1
        assert client.get('/health').status_code==200
    db=Worker(config(tmp_path),None)
    assert db.db.execute('SELECT id FROM updates').fetchone()[0]==123
    db.db.close()


def test_private_pairing_only_and_backend_header(tmp_path):
    calls=[]
    def transport(request):
        calls.append(request)
        if request.url.host=='backend':
            assert request.headers['X-Webhook-Secret']=='test-backend-secret-at-least-20'
            assert json.loads(request.content)['telegram_chat_id']=='123'
            return httpx.Response(200,json={'status':'linked'})
        return httpx.Response(200,json={'ok':True,'result':{'message_id':42}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            worker=Worker(config(tmp_path),client)
            private={'message':{'chat':{'id':123,'type':'private'},'from':{'id':123},'text':'/pair ABCDEFGH'}}
            await worker.update(private)
            assert len(calls)==2
            private['message']['chat']['type']='group'
            await worker.update(private)
            assert len(calls)==2
            worker.db.close()
    asyncio.run(run())


def test_delivery_retry_does_not_resend_after_successful_send(tmp_path):
    cfg=config(tmp_path)
    path=cfg.export_root/'drawing.pdf';path.write_bytes(b'%PDF-fixture')
    sends=0;reports=0
    def transport(request):
        nonlocal sends,reports
        if request.url.host=='api.telegram.org':
            sends+=1
            assert b'%PDF-fixture' in request.content
            return httpx.Response(200,json={'ok':True,'result':{'message_id':42}})
        if request.method=='GET':
            return httpx.Response(200,json=[{'delivery_id':'d1','chat_id':'123','file_path':str(path)}])
        reports+=1
        return httpx.Response(503 if reports==1 else 200,json={'status':'updated'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            worker=Worker(cfg,client)
            await worker.process_deliveries()
            assert worker.db.execute('SELECT state FROM deliveries').fetchone()[0]=='sent'
            worker.db.execute('UPDATE deliveries SET due=0');worker.db.commit()
            await worker.process_deliveries()
            assert worker.db.execute('SELECT state FROM deliveries').fetchone()[0]=='done'
            assert sends==1 and reports==2
            worker.db.close()
    asyncio.run(run())


def test_unavailable_file_retries_then_reports_failure(tmp_path):
    cfg=config(tmp_path)
    failures=[]
    def transport(request):
        assert request.url.host=='backend'
        if request.method=='GET':
            return httpx.Response(200,json=[{'delivery_id':'d1','chat_id':'123','file_path':'/etc/passwd'}])
        failures.append(json.loads(request.content))
        return httpx.Response(200,json={'status':'updated'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            worker=Worker(cfg,client)
            for _ in range(6):
                await worker.process_deliveries()
                worker.db.execute('UPDATE deliveries SET due=0');worker.db.commit()
            assert failures[0]['status']=='failed'
            assert worker.db.execute('SELECT state FROM deliveries').fetchone()[0]=='done'
            worker.db.close()
    asyncio.run(run())
