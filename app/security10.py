"""Optional local-only security gateway. No third-party dependencies."""
import base64, hashlib, hmac, json, os, secrets, time
from pathlib import Path
from urllib.parse import parse_qs
from fastapi import Request
from fastapi.responses import JSONResponse

ROOT=Path(__file__).resolve().parent.parent
CONFIG=ROOT/'.security10.json'
COOKIE='nm_session'

def config():
    if not CONFIG.exists(): return None
    try: return json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError,ValueError): return None

def sign(value, secret):
    return hmac.new(bytes.fromhex(secret),value.encode(),hashlib.sha256).hexdigest()

def token_valid(token,cfg):
    try:
        value, mac=token.rsplit('.',1)
        ts=int(value)
        return time.time()-ts < 28800 and time.time()-ts >= -60 and hmac.compare_digest(mac,sign(value,cfg['session_secret']))
    except (ValueError,KeyError,TypeError): return False

def verify_password(password,cfg):
    try:
        salt=bytes.fromhex(cfg['password_salt'])
        candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600000)
        return hmac.compare_digest(candidate,bytes.fromhex(cfg['password_hash']))
    except (ValueError,KeyError,TypeError): return False

def audit(event,request):
    # Do not log passwords, tokens or request bodies.
    try:
        with (ROOT/'security10_audit.log').open('a',encoding='utf-8') as f:
            f.write(f"{int(time.time())} {event} {request.client.host if request.client else '-'}\n")
    except OSError: pass

async def gateway(request:Request,call_next):
    cfg=config()
    if not cfg or not cfg.get('enabled',False): return await call_next(request)
    path=request.url.path
    if path in ('/health','/auth/status'):
        if path=='/auth/status': return JSONResponse({'enabled':True,'authenticated':token_valid(request.cookies.get(COOKIE,''),cfg)})
        return await call_next(request)
    if path=='/auth/login' and request.method=='POST':
        # Same-origin check to mitigate login CSRF.
        origin=request.headers.get('origin','')
        if origin and origin not in ('http://localhost:5173','http://127.0.0.1:5173','http://localhost:8000','http://127.0.0.1:8000'):
            return JSONResponse({'detail':'Forbidden origin'},status_code=403)
        try:
            data=await request.json()
        except Exception: return JSONResponse({'detail':'Invalid JSON'},status_code=400)
        if not isinstance(data,dict) or not isinstance(data.get('password'),str):
            return JSONResponse({'detail':'Password required'},status_code=400)
        if not verify_password(data['password'],cfg):
            audit('login_failed',request)
            # Small fixed delay; additional rate limiting should be applied for remote deployments.
            import asyncio
            await asyncio.sleep(1)
            return JSONResponse({'detail':'Invalid credentials'},status_code=401)
        value=str(int(time.time()))
        response=JSONResponse({'ok':True})
        response.set_cookie(COOKIE,value+'.'+sign(value,cfg['session_secret']),httponly=True,samesite='strict',secure=False,max_age=28800,path='/')
        audit('login_ok',request)
        return response
    if path=='/auth/logout' and request.method=='POST':
        response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/');audit('logout',request);return response
    # Email agent uses a distinct local bearer token, never the admin password.
    auth=request.headers.get('authorization','')
    service_ok=(request.client is not None and request.client.host in ('127.0.0.1','::1')
        and request.method=='GET' and auth.startswith('Bearer ')
        and hmac.compare_digest(auth[7:],cfg.get('agent_token','')))
    browser_ok=token_valid(request.cookies.get(COOKIE,''),cfg)
    if not (service_ok or browser_ok): return JSONResponse({'detail':'Authentication required'},status_code=401)
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin','')
        if origin not in ('http://localhost:5173','http://127.0.0.1:5173','http://localhost:8000','http://127.0.0.1:8000'):
            return JSONResponse({'detail':'Forbidden origin'},status_code=403)
        audit('write_'+request.method+'_'+path.replace('/','_')[:90],request)
    return await call_next(request)
