"""Test-only same-origin host for the actual production Web bundle and real FastAPI.
Never run this harness against customer or production databases.
"""
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.main import app

root=Path(__file__).resolve().parents[1]/'apps/client/build/web'
if root.exists():
    app.router.routes[:]=[route for route in app.router.routes if getattr(route,'path',None)!='/']
    @app.middleware('http')
    async def isolation(request,call_next):
        response=await call_next(request)
        response.headers['Cross-Origin-Opener-Policy']='same-origin'
        response.headers['Cross-Origin-Embedder-Policy']='require-corp'
        return response
    app.mount('/',StaticFiles(directory=root,html=True),name='acceptance-web')
