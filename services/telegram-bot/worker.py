"""Independent single-replica worker. Persist retries/receipts before acknowledging.
Telegram delivery is at-least-once: a crash after sending but before persisting the
message ID can produce a duplicate. Never claim exactly-once external side effects.
"""
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from dataclasses import dataclass
import httpx
from fastapi import FastAPI, Header, HTTPException, Request

log = logging.getLogger('telegram-worker')
# HTTP client logs can include the bot token in the request URL.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


@dataclass
class Config:
    token: str
    webhook_secret: str
    backend_secret: str
    backend_url: str
    export_root: Path
    database: str

    @classmethod
    def from_env(cls):
        return cls(os.environ['TELEGRAM_BOT_TOKEN'],os.environ['TELEGRAM_WEBHOOK_SECRET'],
                   os.environ['BACKEND_WORKER_SECRET'],os.environ.get('BACKEND_URL','http://api:8000/api/v1/'),
                   Path(os.environ.get('EXPORT_STORAGE_DIR','/data/exports')),
                   os.environ.get('WORKER_DATABASE','/data/worker/worker.sqlite'))


class Worker:
    def __init__(self, config, client):
        self.config,self.client=config,client
        Path(config.database).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(config.database)
        self.db.execute('CREATE TABLE IF NOT EXISTS updates (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT "pending", attempts INTEGER NOT NULL DEFAULT 0, due REAL NOT NULL DEFAULT 0)')
        self.db.execute('CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT "pending", attempts INTEGER NOT NULL DEFAULT 0, due REAL NOT NULL DEFAULT 0, message_id TEXT)')
        self.db.commit()

    def enqueue(self, update):
        if not isinstance(update.get('update_id'),int):
            raise ValueError('Invalid update ID')
        self.db.execute('INSERT OR IGNORE INTO updates(id,payload) VALUES (?,?)',
                        (update['update_id'],json.dumps(update)))
        self.db.commit()

    async def backend(self,method,path,body=None):
        response=await self.client.request(method,self.config.backend_url.rstrip('/')+'/'+path,
            headers={'X-Webhook-Secret':self.config.backend_secret},json=body)
        if not response.is_success:
            raise RuntimeError('Backend request failed')
        return response.json()

    async def telegram(self,method,data,files=None):
        response=await self.client.post(f'https://api.telegram.org/bot{self.config.token}/{method}',data=data,files=files)
        if not response.is_success or not response.json().get('ok'):
            raise RuntimeError('Telegram request failed')
        return response.json()['result']

    async def update(self,payload):
        message=payload.get('message',{})
        chat=message.get('chat',{})
        sender=message.get('from',{})
        # Pair only private chats from the actual sender, never a group/channel ID.
        if chat.get('type')!='private' or sender.get('id')!=chat.get('id'):
            return
        text=message.get('text','')
        parts=text.split()
        if parts and parts[0].split('@')[0]=='/pair' and len(parts)==2:
            try:
                await self.backend('POST','telegram/verify-pairing',{'code':parts[1],
                    'telegram_chat_id':str(chat['id']),'telegram_username':sender.get('username')})
                reply='Account linked. Select an approved export in Cabinet Survey AI to send it here.'
            except RuntimeError:
                reply='Pairing failed. Request a new code in the app and try again.'
        else:
            reply='Use /pair CODE with the one-time code from Cabinet Survey AI.'
        await self.telegram('sendMessage',{'chat_id':str(chat['id']),'text':reply})

    async def process_updates(self):
        for id,payload,attempts in self.db.execute('SELECT id,payload,attempts FROM updates WHERE state="pending" AND due<=? ORDER BY id LIMIT 20',(time.time(),)).fetchall():
            try:
                await self.update(json.loads(payload))
                self.db.execute('UPDATE updates SET state="done",payload="{}" WHERE id=?',(id,))
            except Exception:
                attempts+=1
                self.db.execute('UPDATE updates SET attempts=?,due=?,state=? WHERE id=?',
                    (attempts,time.time()+min(300,2**attempts),'failed' if attempts>=5 else 'pending',id))
                log.warning('Telegram update processing failed; retry scheduled')
            self.db.commit()

    async def process_deliveries(self):
        pending=await self.backend('GET','telegram/internal/pending-deliveries')
        for item in pending:
            self.db.execute('INSERT OR IGNORE INTO deliveries(id,payload) VALUES (?,?)',
                (item['delivery_id'],json.dumps(item)))
        self.db.commit()
        for id,payload,state,attempts,message_id in self.db.execute(
                'SELECT id,payload,state,attempts,message_id FROM deliveries WHERE state!="done" AND due<=? LIMIT 20',(time.time(),)).fetchall():
            item=json.loads(payload)
            try:
                if state=='pending':
                    path=Path(item['file_path']).resolve()
                    root=self.config.export_root.resolve()
                    if not path.is_relative_to(root) or not path.is_file() or path.suffix not in {'.pdf','.png'}:
                        raise ValueError('Export file is unavailable')
                    with path.open('rb') as document:
                        # Send PNG as document too: preserves full engineering resolution.
                        sent=await self.telegram('sendDocument',{'chat_id':item['chat_id']},
                            files={'document':(path.name,document,'application/pdf' if path.suffix=='.pdf' else 'image/png')})
                    message_id=str(sent['message_id'])
                    state='sent'
                    self.db.execute('UPDATE deliveries SET state="sent",message_id=? WHERE id=?',(message_id,id))
                    self.db.commit()
                await self.backend('POST','telegram/internal/delivery-result',{'delivery_id':id,
                    'status':'sent' if state=='sent' else 'failed','message_id':message_id,
                    'error':None if state=='sent' else 'Delivery failed after retries'})
                self.db.execute('UPDATE deliveries SET state="done",payload="{}" WHERE id=?',(id,))
            except Exception:
                attempts+=1
                next_state='failed' if attempts>=5 and state=='pending' else state
                self.db.execute('UPDATE deliveries SET state=?,attempts=?,due=? WHERE id=?',
                    (next_state,attempts,time.time()+min(300,2**min(attempts,9)),id))
                log.warning('Delivery attempt failed; retry state persisted')
            self.db.commit()

    async def loop(self):
        while True:
            try:
                await self.process_updates()
                await self.process_deliveries()
            except Exception:
                log.warning('Worker backend unavailable; retrying')
            await asyncio.sleep(3)


def create_app(config=None):
    @asynccontextmanager
    async def lifespan(app):
        cfg=config or Config.from_env()
        if min(len(cfg.token),len(cfg.webhook_secret),len(cfg.backend_secret))<20:
            raise RuntimeError('Worker secrets must be configured with adequate entropy')
        async with httpx.AsyncClient(timeout=30) as client:
            worker=Worker(cfg,client)
            app.state.worker=worker
            task=asyncio.create_task(worker.loop())
            app.state.task=task
            try: yield
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
                worker.db.close()
    app=FastAPI(lifespan=lifespan)

    @app.get('/health')
    def health():
        if app.state.task.done(): raise HTTPException(503,'Worker stopped')
        return {'status':'ok'}

    @app.post('/webhook')
    async def webhook(request: Request,x_telegram_bot_api_secret_token: str | None=Header(default=None)):
        if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
                app.state.worker.config.webhook_secret,x_telegram_bot_api_secret_token):
            raise HTTPException(401,'Invalid webhook secret')
        body=await request.body()
        if len(body)>1024*1024: raise HTTPException(413,'Update too large')
        try:
            payload=json.loads(body)
            app.state.worker.enqueue(payload)
        except (ValueError,TypeError,AttributeError): raise HTTPException(422,'Invalid update')
        return {'ok':True}
    return app

app=create_app()
