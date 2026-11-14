"""ASGI ingress bound: reject before multipart parsing or JSON allocation."""
from starlette.responses import JSONResponse
from app.core.config import settings


class RequestLimitMiddleware:
    def __init__(self, app):
        self.app=app

    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or scope['method'] not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]))
        multipart=headers.get(b'content-type',b'').lower().startswith(b'multipart/form-data')
        limit=settings.upload_max_bytes+65536 if multipart else 1024*1024
        try:
            declared=int(headers.get(b'content-length',b'0'))
            if declared<0:raise ValueError()
        except ValueError:
            return await JSONResponse({'detail':'Invalid Content-Length'},400)(scope,receive,send)
        body=bytearray()
        if declared>limit:
            return await JSONResponse({'detail':'Request body too large'},413)(scope,receive,send)
        while True:
            event=await receive()
            if event['type']=='http.disconnect':return
            body.extend(event.get('body',b''))
            if len(body)>limit:
                return await JSONResponse({'detail':'Request body too large'},413)(scope,receive,send)
            if not event.get('more_body',False):break
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if delivered:return await receive()
            delivered=True
            return {'type':'http.request','body':bytes(body),'more_body':False}
        await self.app(scope,bounded_receive,send)
