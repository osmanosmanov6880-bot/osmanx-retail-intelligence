"""OSMANX Retail Intelligence HTTP API + single-page frontend.

Run locally: OSMANX_DEMO_MODE=1 uvicorn backend.app:app --reload --host 127.0.0.1
For real use configure OSMANX_ADMIN_PASSWORD and OSMANX_SESSION_SECRET.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from backend.analytics import REASONS, dashboard
from backend.database import connect, initialize_db, now_iso
from backend.retail import stock_for_store, stock_matches, daily_metrics, csv_report, create_reward, zone_heatmap
from backend.security import (Principal, check_password, hash_password, issue_session, verify_session,
    visible_store, visible_object, require_role, audit, check_store_access, device_secret, verify_device_signature, utc_iso)
from backend.imports import ensure_import_schema, preview_import, apply_import
from backend.privacy import reward_allowance
from backend.kiosk import ensure_schema as ensure_kiosk_schema, policy as kiosk_policy, rotate as rotate_kiosk, disable as disable_kiosk, verify as verify_kiosk
from backend.pos_webhook import ensure_schema as ensure_pos_schema, new_source, derive_secret, verify_source, apply_receipts
from backend.operations import quality_report
from backend.workflows import ensure_schema as ensure_workflows_schema, build_router as workflows_router
from backend.r07 import ensure_schema as ensure_r07_schema, build_router as r07_router
from backend.r08 import ensure_schema as ensure_r08_schema, build_router as r08_router
from backend.r09 import ensure_schema as ensure_r09_schema, build_router as r09_router
from backend.r10 import ensure_schema as ensure_r10_schema, build_router as r10_router
from backend.r11 import ensure_schema as ensure_r11_schema, build_router as r11_router
from backend.r12 import ensure_schema as ensure_r12_schema, build_router as r12_router
from backend.commerce import (
    ensure_commerce_schema, inventory_with_availability, matching_available,
    reserve_stock, update_reservation, fitting_report, return_report,
    record_return, price_report, price_analysis, decision_report,
    reserved_quantity,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DEMO = os.getenv("OSMANX_DEMO_MODE", "0") == "1"
PASSWORD = os.getenv("OSMANX_ADMIN_PASSWORD", "")
SECRET = os.getenv("OSMANX_SESSION_SECRET", "")
INGEST_KEY = os.getenv("OSMANX_INGEST_KEY", "")
BOOTSTRAP_EMAIL = os.getenv("OSMANX_BOOTSTRAP_EMAIL", "owner@osmanx.local").strip().lower()
DEVICE_MASTER = os.getenv("OSMANX_DEVICE_MASTER_SECRET", "") or ("only-local-demo-secret-not-for-real-world-usage-123" if DEMO else "")
LIMITS: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not DEMO and (len(PASSWORD) < 12 or len(SECRET) < 32):
        raise RuntimeError("Set OSMANX_ADMIN_PASSWORD (12+ chars) and OSMANX_SESSION_SECRET (32+ chars). For local demo only: OSMANX_DEMO_MODE=1")
    initialize_db(demo=DEMO)
    with connect() as db:
        ensure_import_schema(db)
        ensure_kiosk_schema(db)
        ensure_pos_schema(db)
        ensure_commerce_schema(db)
        ensure_workflows_schema(db)
        ensure_r07_schema(db)
        ensure_r08_schema(db)
        ensure_r09_schema(db)
        ensure_r10_schema(db)
        ensure_r11_schema(db)
        ensure_r12_schema(db)
        db.commit()
    yield


app = FastAPI(title="OSMANX Retail Intelligence", version="1.2.0", lifespan=lifespan,
              docs_url="/api/docs" if DEMO else None, redoc_url=None, openapi_url="/api/openapi.json" if DEMO else None)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def response_guards(request: Request, call_next):
    result = await call_next(request)
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "no-referrer"
    result.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        result.headers["Strict-Transport-Security"] = "max-age=31536000"
    result.headers["X-Frame-Options"] = "SAMEORIGIN"
    result.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
    if request.url.path.startswith('/api/admin/') or request.url.path.startswith('/api/auth/'):
        result.headers['Cache-Control'] = 'no-store'
    return result



def db_conn():
    db = connect()
    try:
        yield db
    finally:
        db.close()


def rate_limit(request: Request, category: str, maximum: int, duration: int = 60):
    ip = request.client.host if request.client else "unknown"
    key = f"{category}:{ip}"
    q = LIMITS[key]
    timestamp = time.monotonic()
    while q and q[0] < timestamp-duration:
        q.popleft()
    if len(q) >= maximum:
        raise HTTPException(status_code=429,detail="Слишком много запросов. Повторите позже.")
    q.append(timestamp)


def admin(authorization: str | None = Header(default=None), db: sqlite3.Connection = Depends(db_conn)) -> Principal:
    if DEMO:
        return Principal(0, 1, 'demo@osmanx.local', 'owner', demo=True)
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Требуется вход администратора')
    return verify_session(authorization[7:], SECRET, db)


def find_store(db: sqlite3.Connection, slug: str):
    row = db.execute("SELECT * FROM stores WHERE slug=?",(slug,)).fetchone()
    if not row:
        raise HTTPException(404,"Магазин не найден")
    return row


class Login(BaseModel):
    email: str | None = Field(default=None,max_length=200)
    password: str = Field(min_length=1,max_length=512)


class Survey(BaseModel):
    rating: int = Field(ge=1,le=5)
    purchased: bool
    reason: Literal["", "size", "price", "assortment", "service", "just_looking", "other"] = ""
    liked: str = Field(default="",max_length=100)
    suggestion: str = Field(default="",max_length=400)
    request_id: str | None = Field(default=None,min_length=12,max_length=100)
    liked_tags: list[Literal['assortment','quality','service','atmosphere','fitting']] = Field(default_factory=list,max_length=5)
    improve_tags: list[Literal['size','assortment','price','service','fitting','queue']] = Field(default_factory=list,max_length=6)

    @field_validator("liked","suggestion")
    @classmethod
    def trim_text(cls,value: str) -> str:
        return value.strip()


class ManualEvent(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    kind: Literal["entry","sale","interest","fitting"]
    quantity: int = Field(default=1,ge=1,le=500)
    amount_rub: float = Field(default=0,ge=0,le=20_000_000)


class DemandCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    product: str = Field(min_length=2,max_length=120)
    size: str = Field(default="",max_length=30)
    color: str = Field(default="",max_length=50)


class DemandStatus(BaseModel):
    status: Literal["open","located","notified","converted","closed"]


class StoreUpdate(BaseModel):
    name: str = Field(min_length=2,max_length=100)
    subtitle: str = Field(default="",max_length=150)
    incentive: str = Field(default="",max_length=160)
    timezone: str = Field(default='Europe/Moscow',max_length=64)
    reward_enabled: bool = False
    reward_label: str = Field(default='',max_length=100)
    reward_daily_limit: int = Field(default=20,ge=0,le=200)
    survey_retention_days: int = Field(default=90,ge=7,le=365)
    traffic_mode: Literal['combined','auto','manual','sensor'] = 'combined' 

    @field_validator('timezone')
    @classmethod
    def validate_zone(cls, value: str) -> str:
        try: ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError('Неизвестный часовой пояс') from None
        return value


class TrafficIngest(BaseModel):
    slug: str
    quantity: int = Field(ge=1,le=10000)
    external_id: str = Field(min_length=4,max_length=120)
    occurred_at: datetime


class PosRecord(BaseModel):
    external_id: str = Field(min_length=1,max_length=120)
    amount_rub: float = Field(ge=0,le=20_000_000)
    occurred_at: datetime


class PosBatch(BaseModel):
    slug: str
    sales: list[PosRecord] = Field(min_length=1,max_length=1000)


@app.get("/api/health")
def health():
    return {"status":"ok","service":"osmanx-retail-intelligence","demo":DEMO}


@app.get("/api/ready")
def ready(db: sqlite3.Connection=Depends(db_conn)):
    try:
        db.execute("SELECT 1 FROM stores LIMIT 1").fetchone()
    except sqlite3.Error:
        raise HTTPException(503, "Database not ready") from None
    return {"status":"ready","database":"ok"}


@app.get("/api/config")
def config():
    return {"demo":DEMO,"auth_required":not DEMO,"features":{"camera":"not_connected","pos":"manual_or_json_import","surveys":"active","inventory":"manual_and_batch","rewards":"optional_manual_validation","experiments":"active","paired_kiosk":"optional","signed_pos_webhook":"available"}}


@app.post("/api/auth/login")
def login(value: Login,request: Request,db:sqlite3.Connection=Depends(db_conn)):
    if DEMO:
        return {'token':'demo','expires_in':28800,'role':'owner'}
    rate_limit(request,'login',6,900)
    email = (value.email or BOOTSTRAP_EMAIL).strip().lower()
    user = db.execute('SELECT * FROM users WHERE email=? AND active=1',(email,)).fetchone()
    if not user or not check_password(value.password,user['password_hash']):
        raise HTTPException(401,'Неверная почта или пароль')
    return {'token':issue_session(user,SECRET),'expires_in':28800,'role':user['role']}


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1,max_length=512)
    new_password: str = Field(min_length=12,max_length=512)


@app.post('/api/auth/change-password')
def change_password(value: PasswordChange, principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    if principal.demo:
        raise HTTPException(409,'Password changes are disabled in demo mode')
    row=db.execute('SELECT * FROM users WHERE id=? AND active=1',(principal.user_id,)).fetchone()
    if row is None or not check_password(value.current_password,row['password_hash']):
        raise HTTPException(401,'Wrong current password')
    if value.new_password==value.current_password:
        raise HTTPException(422,'New password must be different')
    db.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',
               (hash_password(value.new_password),principal.user_id))
    audit(db,principal,'auth.password_change',f'user={principal.user_id}')
    db.commit()
    refreshed=db.execute('SELECT * FROM users WHERE id=?',(principal.user_id,)).fetchone()
    return {'changed':True,'token':issue_session(refreshed,SECRET),'sessions_revoked':True}


@app.post('/api/auth/logout-all')
def logout_all(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    if principal.demo:return {'revoked':True}
    db.execute('UPDATE users SET session_version=session_version+1 WHERE id=?',(principal.user_id,))
    audit(db,principal,'auth.logout_all',f'user={principal.user_id}')
    db.commit()
    return {'revoked':True}


@app.get('/api/admin/me')
def me(principal:Principal=Depends(admin)):
    return {'email':principal.email,'role':principal.role,'organization_id':principal.organization_id,'demo':principal.demo}


@app.get("/api/public/store/{slug}")
def public_store(slug: str,db: sqlite3.Connection=Depends(db_conn)):
    row = find_store(db,slug)
    return {"slug":row["slug"],"name":row["name"],"subtitle":row["subtitle"],"incentive":row["incentive"],"reward_enabled":bool(row["reward_enabled"]),"reward_label":row["reward_label"],"survey_retention_days":row["survey_retention_days"],"kiosk_required":bool(kiosk_policy(db,row["id"])["enabled"])}


@app.post("/api/public/survey/{slug}",status_code=201)
def create_survey(slug: str, value: Survey,request: Request,x_osmanx_kiosk:str|None=Header(default=None),db: sqlite3.Connection=Depends(db_conn)):
    rate_limit(request,'survey',120,300)
    store=find_store(db,slug)
    verify_kiosk(db,store['id'],x_osmanx_kiosk)
    if value.purchased and value.reason:
        raise HTTPException(422,'Причина отказа допустима только без покупки')
    canonical=value.model_dump(exclude={'request_id'},mode='json')
    payload_hash=hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    # Atomic: concurrent kiosk retries cannot issue two rewards or exceed the daily quota.
    db.execute('BEGIN IMMEDIATE')
    try:
        if value.request_id:
            old=db.execute('SELECT id,payload_hash FROM surveys WHERE store_id=? AND request_id=?',
                           (store['id'],value.request_id)).fetchone()
            if old:
                if old['payload_hash'] is not None and old['payload_hash']!=payload_hash:
                    raise HTTPException(409,'Этот идентификатор опроса уже использован с другим ответом')
                reward=db.execute('SELECT code,label,expires_at FROM rewards WHERE survey_id=?',(old['id'],)).fetchone()
                db.commit()
                return {'saved':True,'duplicate':True,'reward':dict(reward) if reward else None}
        cur=db.execute("""INSERT INTO surveys(store_id,rating,purchased,reason,liked,suggestion,request_id,liked_tags,improve_tags,payload_hash,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(store['id'],value.rating,int(value.purchased),value.reason,
            value.liked,value.suggestion,value.request_id,json.dumps(value.liked_tags,ensure_ascii=False),
            json.dumps(value.improve_tags,ensure_ascii=False),payload_hash,now_iso()))
        reward=None
        if store['reward_enabled'] and store['reward_label'] and reward_allowance(db,store):
            reward=create_reward(db,store['id'],cur.lastrowid,store['reward_label'])
        db.commit()
        return {'saved':True,'duplicate':False,'reward':reward,
                'reward_unavailable':bool(store['reward_enabled'] and store['reward_label'] and reward is None)}
    except Exception:
        db.rollback()
        raise



@app.get("/api/admin/stores")
def stores(db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    rows=db.execute("""SELECT s.slug,s.name,s.subtitle,s.incentive,s.timezone,s.reward_enabled,s.reward_label,
      s.traffic_mode,s.reward_daily_limit,s.survey_retention_days,
      EXISTS(SELECT 1 FROM kiosk_policies k WHERE k.store_id=s.id AND k.enabled=1) kiosk_required FROM stores s
      WHERE s.organization_id=? AND (?='owner' OR EXISTS
        (SELECT 1 FROM user_store_access a WHERE a.store_id=s.id AND a.user_id=?)) ORDER BY s.id""",
        (principal.organization_id,principal.role,principal.user_id)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/admin/dashboard")
def get_dashboard(slug: str="central",days:int=30,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    if days not in (7, 30):
        raise HTTPException(422,"Период должен составлять 7 или 30 дней")
    store=visible_store(db,slug,principal)
    result=dashboard(db,store['id'],days,store['timezone'])
    for opportunity in result.get('stock_matches',[]):
        allowed=[]
        for match in opportunity.get('matches',[]):
            try:check_store_access(db,match['store_id'],principal)
            except HTTPException:continue
            allowed.append(match)
        opportunity['matches']=allowed
    result['stock_matches']=[x for x in result.get('stock_matches',[]) if x['matches']]
    return result


@app.post("/api/admin/events",status_code=201)
def manual_event(data:ManualEvent,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store_id=visible_store(db,data.slug,principal)["id"]
    timestamp=now_iso()
    if data.kind=="entry":
        db.execute("INSERT INTO visits(store_id,quantity,source,occurred_at) VALUES(?,?,?,?)",
            (store_id,data.quantity,"manual",timestamp))
    elif data.kind=="sale":
        if data.quantity != 1:
            raise HTTPException(422,"Для продаж используйте одну запись на чек")
        db.execute("INSERT INTO sales(store_id,amount_kopeks,source,occurred_at) VALUES(?,?,?,?)",
            (store_id,round(data.amount_rub*100),"manual",timestamp))
    else:
        db.execute("INSERT INTO signals(store_id,kind,quantity,occurred_at) VALUES(?,?,?,?)",
            (store_id,data.kind,data.quantity,timestamp))
    db.commit()
    return {"saved":True}


@app.post("/api/admin/demand",status_code=201)
def create_demand(data:DemandCreate,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store_id=visible_store(db,data.slug,principal)["id"]
    timestamp=now_iso()
    cur=db.execute("INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (store_id,data.product.strip(),data.size.strip(),data.color.strip(),timestamp,timestamp))
    audit(db,principal,'demand.create',f'store={data.slug} demand={cur.lastrowid}')
    db.commit()
    return {"saved":True,"id":cur.lastrowid}


@app.patch("/api/admin/demand/{demand_id}")
def set_demand(demand_id:int,data:DemandStatus,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    previous=visible_object(db,'demand',demand_id,principal)
    if not previous: raise HTTPException(404,'Запрос не найден')
    if data.status == 'converted' and previous['sale_id'] is None:
        raise HTTPException(422,'Подтвердите покупку через привязку кассового чека')
    if previous['status'] != data.status:
        db.execute('UPDATE demand SET status=?,updated_at=? WHERE id=?',(data.status,now_iso(),demand_id))
        db.execute('INSERT INTO demand_history(demand_id,previous_status,next_status,occurred_at) VALUES(?,?,?,?)',
                   (demand_id,previous['status'],data.status,now_iso()))
    db.commit()
    return {'saved':True}


@app.put("/api/admin/store/{slug}")
def update_store(slug:str,data:StoreUpdate,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner')
    store=visible_store(db,slug,principal)
    db.execute("""UPDATE stores SET name=?,subtitle=?,incentive=?,timezone=?,reward_enabled=?,reward_label=?,
      traffic_mode=?,reward_daily_limit=?,survey_retention_days=? WHERE id=?""",
        (data.name.strip(),data.subtitle.strip(),data.incentive.strip(),data.timezone,int(data.reward_enabled),
         data.reward_label.strip(),data.traffic_mode,data.reward_daily_limit,data.survey_retention_days,store['id']))
    db.commit()
    return {"saved":True}


@app.post("/api/admin/import/pos")
def import_pos(data:PosBatch,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store=visible_store(db,data.slug,principal)
    imported=0
    for row in data.sales:
        cur=db.execute("INSERT OR IGNORE INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)",
            (store["id"],round(row.amount_rub*100),"pos_import",row.occurred_at.astimezone(timezone.utc).isoformat(timespec="seconds"),row.external_id))
        imported+=cur.rowcount
    db.commit()
    return {"imported":imported,"duplicates":len(data.sales)-imported}


@app.post("/api/ingest/traffic",status_code=410)
def ingest_traffic_legacy():
    raise HTTPException(410,'Legacy unauthenticated ingestion disabled; use signed v2')


class StockItem(BaseModel):
    sku: str = Field(min_length=2,max_length=80)
    product: str = Field(min_length=2,max_length=120)
    size: str = Field(default='',max_length=30)
    color: str = Field(default='',max_length=50)
    quantity: int = Field(ge=0,le=1_000_000)

class StockImport(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    items: list[StockItem] = Field(min_length=1,max_length=2000)
    source: Literal['manual','csv_import','api_import'] = 'manual'

class ExperimentCreate(BaseModel):
    slug: str
    title: str = Field(min_length=4,max_length=120)
    hypothesis: str = Field(min_length=8,max_length=500)
    metric: Literal['conversion','confirmed_sales','avg_receipt','repeat_visits','gross_profit']
    baseline: float | None = Field(default=None,ge=0)

class ExperimentUpdate(BaseModel):
    status: Literal['planned','running','finished','cancelled']
    result: float | None = Field(default=None,ge=0)
    notes: str = Field(default='',max_length=1000)

class ConfirmDemandSale(BaseModel):
    sale_id: int = Field(gt=0)

class RewardRedemption(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    code: str = Field(min_length=8,max_length=40)

class NewStore(BaseModel):
    slug: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{1,40}$')
    name: str = Field(min_length=2,max_length=100)
    timezone: str = 'Europe/Moscow'

    @field_validator('timezone')
    @classmethod
    def check_zone(cls,value):
        try: ZoneInfo(value)
        except (ValueError,ZoneInfoNotFoundError): raise ValueError('Неизвестный часовой пояс') from None
        return value


class ZoneCreate(BaseModel):
    slug: str
    code: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{1,40}$')
    name: str = Field(min_length=2,max_length=70)
    x: int = Field(ge=0,le=100)
    y: int = Field(ge=0,le=100)

class ZoneIngest(BaseModel):
    slug: str
    zone_code: str
    quantity: int = Field(ge=1,le=10000)
    external_id: str = Field(min_length=4,max_length=120)
    occurred_at: datetime

@app.post('/api/admin/zones',status_code=201)
def create_zone(data:ZoneCreate,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store=visible_store(db,data.slug,principal)
    db.execute("""INSERT INTO zones(store_id,code,name,x,y) VALUES(?,?,?,?,?)
        ON CONFLICT(store_id,code) DO UPDATE SET name=excluded.name,x=excluded.x,y=excluded.y""",
        (store['id'],data.code,data.name.strip(),data.x,data.y))
    db.commit()
    return {'saved':True}

@app.get('/api/admin/zones')
def get_zones(slug:str='central',db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('SELECT id,code,name,x,y FROM zones WHERE store_id=? ORDER BY id',(store['id'],))]

@app.post('/api/ingest/zones',status_code=201)
def ingest_zones(data:ZoneIngest,x_osmanx_ingest_key:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_conn)):
    if not DEMO:
        raise HTTPException(410,'Старый общий ключ отключён. Используйте /api/ingest/v2/{тип} с подписью устройства.')
    if not INGEST_KEY or not x_osmanx_ingest_key or not hmac.compare_digest(x_osmanx_ingest_key,INGEST_KEY):
        raise HTTPException(401,'Неверный ключ интеграции')
    store=find_store(db,data.slug)
    zone=db.execute('SELECT id FROM zones WHERE store_id=? AND code=?',(store['id'],data.zone_code)).fetchone()
    if not zone: raise HTTPException(404,'Зона не зарегистрирована')
    when=data.occurred_at.astimezone(timezone.utc).isoformat(timespec='seconds')
    cur=db.execute('INSERT OR IGNORE INTO zone_events(store_id,zone_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?,?)',
                   (store['id'],zone['id'],data.quantity,'sensor',when,data.external_id))
    db.commit()
    return {'saved':bool(cur.rowcount),'duplicate':not bool(cur.rowcount)}


@app.post('/api/admin/stores',status_code=201)
def add_store(data:NewStore,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner')
    try:
        db.execute('INSERT INTO stores(slug,name,timezone,created_at,organization_id) VALUES(?,?,?,?,?)',
                   (data.slug,data.name.strip(),data.timezone,now_iso(),principal.organization_id))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409,'Филиал с таким кодом уже существует') from None
    return {'created':True,'slug':data.slug}


@app.get('/api/admin/stock')
def get_stock(slug:str='central',db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    store=visible_store(db,slug,principal)
    return {'store':slug,'items':inventory_with_availability(db,store['id'])}


@app.post('/api/admin/stock/import')
def import_stock(value:StockImport,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store=visible_store(db,value.slug,principal)
    stamp=now_iso()
    # Reject duplicate SKUs within a batch to avoid a hidden last-row-wins rule.
    skus=[x.sku.strip().casefold() for x in value.items]
    if len(skus)!=len(set(skus)):
        raise HTTPException(422,'Повторяющиеся артикулы в одном импорте')
    for item in value.items:
        old=db.execute('SELECT id FROM inventory WHERE store_id=? AND sku=?',(store['id'],item.sku.strip())).fetchone()
        if old and item.quantity<reserved_quantity(db,old['id']):
            raise HTTPException(409,'Новый остаток меньше количества действующих резервов для '+item.sku)
    for item in value.items:
        db.execute("""INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(store_id,sku) DO UPDATE SET
          product=excluded.product,size=excluded.size,color=excluded.color,
          quantity=excluded.quantity,source=excluded.source,updated_at=excluded.updated_at""",
          (store['id'],item.sku.strip(),item.product.strip(),item.size.strip(),item.color.strip(),
           item.quantity,value.source,stamp))
    db.commit()
    return {'imported':len(value.items),'store':value.slug}


@app.get('/api/admin/demand/{demand_id}/matches')
def demand_matches(demand_id:int,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    item=visible_object(db,'demand',demand_id,principal)
    if not item: raise HTTPException(404,'Запрос не найден')
    matches=matching_available(db,item['store_id'],item['product'],item['size'],item['color'])
    allowed=[]
    for row in matches:
        try:check_store_access(db,row['store_id'],principal)
        except HTTPException:continue
        allowed.append(row)
    return {'matches':allowed, 'method':'Точное совпадение товара, размера и цвета. Доступность учитывает действующие резервы; фактический остаток следует подтвердить.'}


@app.post('/api/admin/demand/{demand_id}/convert')
def confirm_demand(demand_id:int,value:ConfirmDemandSale,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    item=visible_object(db,'demand',demand_id,principal)
    if not item: raise HTTPException(404,'Запрос не найден')
    sale=db.execute('SELECT id,occurred_at FROM sales WHERE id=? AND store_id=?',(value.sale_id,item['store_id'])).fetchone()
    if not sale: raise HTTPException(422,'Чек не найден в магазине запроса')
    if datetime.fromisoformat(sale['occurred_at']) < datetime.fromisoformat(item['created_at']):
        raise HTTPException(422,'Чек должен быть оформлен после зафиксированного запроса')
    other=db.execute('SELECT id FROM demand WHERE sale_id=? AND id<>?',(value.sale_id,demand_id)).fetchone()
    if other: raise HTTPException(409,'Чек уже связан с другим запросом')
    db.execute('UPDATE demand SET status=?,sale_id=?,updated_at=? WHERE id=?',
               ('converted',sale['id'],now_iso(),demand_id))
    db.execute('INSERT INTO demand_history(demand_id,previous_status,next_status,note,occurred_at) VALUES(?,?,?,?,?)',
               (demand_id,item['status'],'converted',f"Подтверждён чек №{sale['id']}",now_iso()))
    db.commit()
    return {'saved':True,'verified_sale_id':sale['id']}


@app.get('/api/admin/experiments')
def get_experiments(slug:str='central',db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('SELECT * FROM experiments WHERE store_id=? ORDER BY updated_at DESC,id DESC LIMIT 100',(store['id'],))]


@app.post('/api/admin/experiments',status_code=201)
def create_experiment(data:ExperimentCreate,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store=visible_store(db,data.slug,principal)
    now=now_iso()
    cur=db.execute('INSERT INTO experiments(store_id,title,hypothesis,metric,baseline,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (store['id'],data.title.strip(),data.hypothesis.strip(),data.metric,data.baseline,now,now))
    db.commit()
    return {'created':True,'id':cur.lastrowid}


@app.patch('/api/admin/experiments/{experiment_id}')
def update_experiment(experiment_id:int,data:ExperimentUpdate,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    current=visible_object(db,'experiments',experiment_id,principal)
    if not current: raise HTTPException(404,'Гипотеза не найдена')
    if data.status=='finished' and data.result is None:
        raise HTTPException(422,'Для завершения укажите измеренный результат')
    db.execute('UPDATE experiments SET status=?,result=?,notes=?,updated_at=? WHERE id=?',
               (data.status,data.result,data.notes.strip(),now_iso(),experiment_id))
    db.commit()
    return {'saved':True}


@app.get('/api/admin/report/daily')
def report_daily(slug:str='central',days:int=30,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    if days not in (7,30): raise HTTPException(422,'Поддерживаются 7 или 30 дней')
    store=visible_store(db,slug,principal)
    return {'timezone':store['timezone'],'days':daily_metrics(db,store['id'],store['timezone'],days,store['traffic_mode'])}


@app.get('/api/admin/export/{dataset}.csv')
def export_report(dataset:str,slug:str='central',db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal,'owner','manager','analyst')
    store=visible_store(db,slug,principal)
    try: contents=csv_report(db,store['id'],dataset)
    except ValueError: raise HTTPException(404,'Отчёт не найден') from None
    return Response(contents,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="osmanx-{dataset}-{slug}.csv"',
        'Cache-Control':'no-store'})


@app.post('/api/admin/rewards/redeem')
def redeem_reward(data:RewardRedemption,db:sqlite3.Connection=Depends(db_conn),principal:Principal=Depends(admin)):
    require_role(principal, 'owner', 'manager')
    store=visible_store(db,data.slug,principal)
    reward=db.execute('SELECT * FROM rewards WHERE code=? AND store_id=?',
                      (data.code.strip().upper(),store['id'])).fetchone()
    if not reward: raise HTTPException(404,'Код не найден')
    if reward['redeemed_at']: raise HTTPException(409,'Бонус уже погашен')
    if reward['expires_at']<now_iso(): raise HTTPException(410,'Срок действия бонуса истёк')
    updated=db.execute('UPDATE rewards SET redeemed_at=? WHERE id=? AND redeemed_at IS NULL AND expires_at>=?',
               (now_iso(),reward['id'],now_iso()))
    if updated.rowcount!=1:
        db.rollback()
        raise HTTPException(409,'Бонус уже погашен или срок действия истёк')
    audit(db,principal,'reward.redeem',f'reward={reward["id"]}')
    db.commit()
    return {'redeemed':True,'label':reward['label'],'code':reward['code']}



# R0.3: Access management, signed sensor ingestion, staged external imports and audits.
class TeamMemberCreate(BaseModel):
    email: str = Field(min_length=5,max_length=200)
    name: str = Field(min_length=1,max_length=100)
    password: str = Field(min_length=12,max_length=200)
    role: Literal['owner','manager','analyst','viewer']
    stores: list[str] = Field(default_factory=list,max_length=100)

class TeamMemberUpdate(BaseModel):
    active: bool
    stores: list[str] = Field(default_factory=list,max_length=100)

class DeviceCreate(BaseModel):
    slug: str
    name: str = Field(min_length=2,max_length=100)
    kind: Literal['traffic','zones']

class DeviceMessage(BaseModel):
    quantity: int = Field(ge=1,le=10000)
    external_id: str = Field(min_length=4,max_length=120)
    occurred_at: datetime
    zone_code: str | None = Field(default=None,max_length=50)

class ImportDraft(BaseModel):
    slug: str
    kind: Literal['pos','inventory']
    rows: list[dict] = Field(min_length=1,max_length=2000)

class ImportCommit(BaseModel):
    batch_key: str = Field(min_length=16,max_length=100)

@app.get('/api/admin/team')
def list_team(principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner')
    rows=db.execute('SELECT id,email,full_name,role,active,created_at FROM users WHERE organization_id=? ORDER BY id',
                    (principal.organization_id,)).fetchall()
    return [{'id':r['id'],'email':r['email'],'name':r['full_name'],'role':r['role'],
             'active':bool(r['active']),'created_at':r['created_at'],
             'stores':[a['slug'] for a in db.execute('SELECT s.slug FROM user_store_access a JOIN stores s ON s.id=a.store_id WHERE a.user_id=?',(r['id'],))]}
            for r in rows]

@app.post('/api/admin/team',status_code=201)
def create_team_member(data:TeamMemberCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner')
    email=data.email.strip().lower()
    if '@' not in email or any(ch.isspace() for ch in email): raise HTTPException(422,'Неверная почта')
    if data.role!='owner' and not data.stores: raise HTTPException(422,'Назначьте хотя бы один филиал')
    ids=[visible_store(db,slug,principal)['id'] for slug in set(data.stores)]
    try:
        cur=db.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
          (principal.organization_id,email,data.name.strip(),hash_password(data.password),data.role,now_iso()))
        for store_id in ids:
            db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(cur.lastrowid,store_id))
        audit(db,principal,'team.create',f'account={cur.lastrowid} role={data.role}')
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise HTTPException(409,'Адрес электронной почты уже используется') from None
    return {'created':True,'id':cur.lastrowid}

@app.patch('/api/admin/team/{user_id}')
def update_team_member(user_id:int,data:TeamMemberUpdate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner')
    target=db.execute('SELECT * FROM users WHERE id=? AND organization_id=?',(user_id,principal.organization_id)).fetchone()
    if not target: raise HTTPException(404,'Пользователь не найден')
    if user_id==principal.user_id and not data.active: raise HTTPException(422,'Нельзя заблокировать собственный аккаунт')
    if not data.active and target['role']=='owner':
        count=db.execute("SELECT COUNT(*) n FROM users WHERE organization_id=? AND role='owner' AND active=1",
                         (principal.organization_id,)).fetchone()['n']
        if count<=1: raise HTTPException(422,'Нельзя отключить последнего владельца')
    if data.active and target['role']!='owner' and not data.stores:
        raise HTTPException(422,'Назначьте хотя бы один филиал')
    ids=[visible_store(db,slug,principal)['id'] for slug in set(data.stores)]
    db.execute('UPDATE users SET active=?,session_version=session_version+1 WHERE id=?',(int(data.active),user_id))
    db.execute('DELETE FROM user_store_access WHERE user_id=?',(user_id,))
    for store_id in ids: db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(user_id,store_id))
    audit(db,principal,'team.update',f'account={user_id} active={data.active}')
    db.commit()
    return {'saved':True,'sessions_revoked':True}

@app.get('/api/admin/audit')
def get_audit(limit:int=50,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner')
    if not 1<=limit<=100: raise HTTPException(422,'Максимум 100 событий')
    return [dict(r) for r in db.execute('SELECT action,subject,created_at FROM audit_events WHERE organization_id=? ORDER BY id DESC LIMIT ?',
                                       (principal.organization_id,limit))]

@app.get('/api/admin/devices')
def get_devices(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager','analyst')
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('SELECT public_id,name,kind,active,generation,created_at FROM devices WHERE store_id=? ORDER BY id',(store['id'],))]

@app.post('/api/admin/devices',status_code=201)
def create_device(data:DeviceCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    public_id='dvc_'+secrets.token_hex(12)
    secret=device_secret(public_id,1,store['id'],DEVICE_MASTER)
    db.execute('INSERT INTO devices(public_id,organization_id,store_id,name,kind,created_at) VALUES(?,?,?,?,?,?)',
               (public_id,principal.organization_id,store['id'],data.name.strip(),data.kind,now_iso()))
    audit(db,principal,'device.create',public_id)
    db.commit()
    return {'device_id':public_id,'secret':secret,'store':data.slug,'kind':data.kind,
            'note':'Сохраните секрет сейчас: повторно он не отображается.'}

@app.post('/api/admin/devices/{public_id}/rotate')
def rotate_device(public_id:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    row=db.execute('SELECT * FROM devices WHERE public_id=? AND organization_id=?',(public_id,principal.organization_id)).fetchone()
    if not row: raise HTTPException(404,'Устройство не найдено')
    check_store_access(db,row['store_id'],principal)
    generation=row['generation']+1
    secret=device_secret(public_id,generation,row['store_id'],DEVICE_MASTER)
    db.execute('UPDATE devices SET generation=?,active=1 WHERE id=?',(generation,row['id']))
    audit(db,principal,'device.rotate',public_id)
    db.commit()
    return {'device_id':public_id,'secret':secret,'generation':generation}

@app.delete('/api/admin/devices/{public_id}')
def revoke_device(public_id:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    row=db.execute('SELECT * FROM devices WHERE public_id=? AND organization_id=?',(public_id,principal.organization_id)).fetchone()
    if not row: raise HTTPException(404,'Устройство не найдено')
    check_store_access(db,row['store_id'],principal)
    db.execute('UPDATE devices SET active=0,generation=generation+1 WHERE id=?',(row['id'],))
    audit(db,principal,'device.revoke',public_id)
    db.commit()
    return {'revoked':True}

@app.post('/api/ingest/v2/{kind}',status_code=201)
async def ingest_signed(kind:Literal['traffic','zones'],request:Request,
    x_osmanx_device:str|None=Header(default=None),x_osmanx_timestamp:str|None=Header(default=None),
    x_osmanx_signature:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_conn)):
    raw=await request.body()
    if len(raw)>16_384: raise HTTPException(413,'Сообщение устройства слишком большое')
    if not all((x_osmanx_device,x_osmanx_timestamp,x_osmanx_signature)):
        raise HTTPException(401,'Требуется подпись устройства')
    device=verify_device_signature(db,public_id=x_osmanx_device,signature=x_osmanx_signature,
             signed_timestamp=x_osmanx_timestamp,raw_body=raw,kind=kind,master=DEVICE_MASTER)
    try: data=DeviceMessage.model_validate_json(raw)
    except Exception: raise HTTPException(422,'Неверный формат события') from None
    when=utc_iso(data.occurred_at)
    if abs((datetime.now(timezone.utc)-datetime.fromisoformat(when)).total_seconds())>86400*31:
        raise HTTPException(422,'Событие вне допустимого периода ±31 день')
    if kind=='zones':
        if not data.zone_code: raise HTTPException(422,'Не указан код зоны')
        zone=db.execute('SELECT id FROM zones WHERE store_id=? AND code=?',(device['store_id'],data.zone_code)).fetchone()
        if not zone: raise HTTPException(404,'Зона не найдена в магазине устройства')
    else:
        if data.zone_code: raise HTTPException(422,'Для счётчика входов зона не требуется')
    payload_sha=hashlib.sha256(raw).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        old=db.execute('SELECT payload_sha256 FROM device_events WHERE device_id=? AND kind=? AND external_id=?',
                       (device['id'],kind,data.external_id)).fetchone()
        if old:
            if old['payload_sha256']!=payload_sha:
                raise HTTPException(409,'Это ID события уже использован с другим содержимым')
            db.commit()
            return {'saved':False,'duplicate':True}
        if kind=='traffic':
            db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                       (device['store_id'],data.quantity,'signed_sensor',when,f"{device['public_id']}:{data.external_id}"))
        else:
            db.execute('INSERT INTO zone_events(store_id,zone_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?,?)',
                       (device['store_id'],zone['id'],data.quantity,'signed_sensor',when,f"{device['public_id']}:{data.external_id}"))
        db.execute('INSERT INTO device_events(device_id,kind,external_id,payload_sha256,received_at) VALUES(?,?,?,?,?)',
                   (device['id'],kind,data.external_id,payload_sha,now_iso()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'saved':True,'duplicate':False}

class PosSourceCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=2,max_length=100)


@app.post('/api/admin/kiosks/{slug}/rotate')
def pair_kiosk(slug:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,slug,principal)
    token,generation=rotate_kiosk(db,store['id'])
    audit(db,principal,'kiosk.rotate',f'store={slug} generation={generation}')
    db.commit()
    return {'slug':slug,'token':token,'generation':generation,
            'pair_url_fragment':'#access='+token,'note':'Copy token now; it cannot be displayed again.'}


@app.delete('/api/admin/kiosks/{slug}')
def unpair_kiosk(slug:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,slug,principal)
    disable_kiosk(db,store['id'])
    audit(db,principal,'kiosk.disable',f'store={slug}')
    db.commit()
    return {'disabled':True}


@app.get('/api/admin/pos/sources')
def list_pos_sources(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    require_role(principal,'owner','manager','analyst')
    return [dict(x) for x in db.execute('''SELECT p.public_id,p.name,p.active,p.generation,p.created_at,
        MAX(e.received_at) last_seen,COUNT(e.id) accepted_events FROM pos_sources p
        LEFT JOIN pos_events e ON e.source_id=p.id WHERE p.store_id=? GROUP BY p.id ORDER BY p.id''',(store['id'],))]


@app.post('/api/admin/pos/sources',status_code=201)
def create_pos_source(value:PosSourceCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,value.slug,principal)
    source=new_source(db,principal.organization_id,store['id'],value.name,DEVICE_MASTER)
    audit(db,principal,'pos.create',source['source_id'])
    db.commit()
    return {**source,'note':'Keep the secret safe; it is shown only once.'}


def owned_pos_source(db:sqlite3.Connection,public_id:str,principal:Principal)->sqlite3.Row:
    row=db.execute('SELECT * FROM pos_sources WHERE public_id=? AND organization_id=?',
                   (public_id,principal.organization_id)).fetchone()
    if not row:raise HTTPException(404,'POS source not found')
    check_store_access(db,row['store_id'],principal)
    return row


@app.post('/api/admin/pos/sources/{public_id}/rotate')
def rotate_pos_source(public_id:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    row=owned_pos_source(db,public_id,principal)
    db.execute('UPDATE pos_sources SET generation=generation+1,active=1 WHERE id=?',(row['id'],))
    updated=db.execute('SELECT * FROM pos_sources WHERE id=?',(row['id'],)).fetchone()
    audit(db,principal,'pos.rotate',public_id)
    db.commit()
    return {'source_id':public_id,'secret':derive_secret(updated,DEVICE_MASTER),'generation':updated['generation']}


@app.delete('/api/admin/pos/sources/{public_id}')
def revoke_pos_source(public_id:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    row=owned_pos_source(db,public_id,principal)
    db.execute('UPDATE pos_sources SET active=0,generation=generation+1 WHERE id=?',(row['id'],))
    audit(db,principal,'pos.revoke',public_id)
    db.commit()
    return {'revoked':True}


@app.post('/api/ingest/pos',status_code=201)
async def signed_pos(request:Request,x_osmanx_source:str|None=Header(default=None),
       x_osmanx_timestamp:str|None=Header(default=None),x_osmanx_signature:str|None=Header(default=None),
       db:sqlite3.Connection=Depends(db_conn)):
    raw=await request.body()
    if len(raw)>131_072:raise HTTPException(413,'POS payload too large')
    source=verify_source(db,x_osmanx_source,x_osmanx_timestamp,x_osmanx_signature,raw,DEVICE_MASTER)
    return apply_receipts(db,source,raw)


@app.get('/api/admin/operations/quality')
def get_quality(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7,30):raise HTTPException(422,'Period must be 7 or 30 days')
    return quality_report(db,visible_store(db,slug,principal),days)


@app.post('/api/admin/imports/preview',status_code=201)
def preview_batch(data:ImportDraft,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    return preview_import(db,organization_id=principal.organization_id,store_id=store['id'],
                          user_id=None if principal.demo else principal.user_id,kind=data.kind,rows=data.rows)

@app.post('/api/admin/imports/apply')
def apply_batch(data:ImportCommit,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    result=apply_import(db,batch_key=data.batch_key,organization_id=principal.organization_id,
                        check_store=lambda store_id:check_store_access(db,store_id,principal))
    audit(db,principal,'import.apply',data.batch_key)
    db.commit()
    return result

@app.get('/api/admin/imports')
def list_import_batches(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('SELECT batch_key,kind,status,preview_json,created_at,applied_at FROM import_batches WHERE organization_id=? AND store_id=? ORDER BY id DESC LIMIT 40',
                                        (principal.organization_id,store['id']))]


# R0.5: branch reservations, anonymous fitting observations, returns, pricing and decisions.
class HoldRequest(BaseModel):
    demand_id:int=Field(gt=0)
    inventory_id:int=Field(gt=0)
    request_id:str=Field(min_length=12,max_length=100)
    quantity:int=Field(default=1,ge=1,le=20)
    hours:int=Field(default=24,ge=1,le=72)

class HoldChange(BaseModel):
    action:Literal['collect','cancel']

class FittingEntry(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    product:str=Field(min_length=2,max_length=120)
    size:str=Field(default='',max_length=30)
    trials:int=Field(ge=1,le=500)
    purchases:int=Field(ge=0,le=500)
    reason:Literal['none','fit','price','size','quality','other']='none'

class ReturnEntry(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    sale_id:int=Field(gt=0)
    external_id:str=Field(min_length=12,max_length=100)
    item:str=Field(min_length=2,max_length=120)
    amount_kopeks:int=Field(gt=0,le=2_000_000_000)
    reason:Literal['size','fit','quality','different','other']

class PriceEntry(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    title:str=Field(min_length=3,max_length=120)
    sku:str=Field(min_length=2,max_length=80)
    price_kopeks:int=Field(gt=0,le=2_000_000_000)
    cost_kopeks:int=Field(ge=0,le=2_000_000_000)
    discount_bps:int=Field(ge=0,le=9000)
    baseline_units:int=Field(ge=0,le=1000000)
    planned_units:int=Field(ge=0,le=1000000)

class DecisionUpdate(BaseModel):
    status:Literal['new','testing','done','dismissed']
    note:str=Field(default='',max_length=1000)

@app.get('/api/admin/reservations')
def list_holds(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('''SELECT r.*,i.sku,i.product,i.size,i.color,s.name AS source_name
       FROM reservations r JOIN inventory i ON i.id=r.source_inventory_id
       JOIN stores s ON s.id=r.source_store_id
       WHERE r.destination_store_id=? ORDER BY r.id DESC LIMIT 100''',(store['id'],))]

@app.post('/api/admin/reservations',status_code=201)
def create_hold(data:HoldRequest,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    demand=visible_object(db,'demand',data.demand_id,principal)
    item=db.execute('''SELECT i.*,s.organization_id FROM inventory i JOIN stores s ON s.id=i.store_id
         WHERE i.id=?''',(data.inventory_id,)).fetchone()
    if not item or item['organization_id']!=principal.organization_id:
        raise HTTPException(404,'Товар не найден')
    check_store_access(db,item['store_id'],principal)
    result=reserve_stock(db,organization_id=principal.organization_id,demand_id=demand['id'],
       inventory_id=data.inventory_id,request_id=data.request_id,quantity=data.quantity,hours=data.hours)
    if not result['duplicate']:
        audit(db,principal,'reservation.create',f'hold={result["id"]}')
        db.commit()
    return result

@app.post('/api/admin/reservations/{hold_id}/action')
def change_hold(hold_id:int,data:HoldChange,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    row=db.execute('SELECT * FROM reservations WHERE id=? AND organization_id=?',(hold_id,principal.organization_id)).fetchone()
    if not row:raise HTTPException(404,'Резерв не найден')
    check_store_access(db,row['source_store_id'],principal)
    check_store_access(db,row['destination_store_id'],principal)
    result=update_reservation(db,hold_id,data.action)
    audit(db,principal,'reservation.'+data.action,f'hold={hold_id}')
    db.commit()
    return result

@app.get('/api/admin/fittings')
def get_fittings(slug:str='central',days:int=30,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7,30):raise HTTPException(422,'Выберите 7 или 30 дней')
    store=visible_store(db,slug,principal)
    return fitting_report(db,store['id'],days)

@app.post('/api/admin/fittings',status_code=201)
def add_fitting(data:FittingEntry,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    if data.purchases>data.trials:raise HTTPException(422,'Число покупок не может превышать число примерок')
    stamp=now_iso()
    cur=db.execute('''INSERT INTO fitting_observations(store_id,product,size,trials,purchases,reason,observed_at,created_at)
       VALUES(?,?,?,?,?,?,?,?)''',(store['id'],data.product.strip(),data.size.strip(),data.trials,data.purchases,data.reason,stamp,stamp))
    audit(db,principal,'fitting.observe',f'entry={cur.lastrowid}')
    db.commit()
    return {'created':True,'id':cur.lastrowid}

@app.get('/api/admin/receipts')
def recent_receipts(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    return [dict(r) for r in db.execute('''SELECT id,amount_kopeks,source,occurred_at FROM sales
       WHERE store_id=? ORDER BY id DESC LIMIT 100''',(store['id'],))]

@app.get('/api/admin/returns')
def get_returns(slug:str='central',days:int=30,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7,30):raise HTTPException(422,'Выберите 7 или 30 дней')
    store=visible_store(db,slug,principal)
    return return_report(db,store['id'],days)

@app.post('/api/admin/returns',status_code=201)
def add_return(data:ReturnEntry,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    result=record_return(db,store_id=store['id'],sale_id=data.sale_id,external_id=data.external_id,
                         item=data.item.strip(),reason=data.reason,amount_kopeks=data.amount_kopeks)
    if not result['duplicate']:
        audit(db,principal,'return.record',f'return={result["id"]}')
        db.commit()
    return result

@app.get('/api/admin/pricing')
def get_pricing(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    return price_report(db,store['id'])

@app.post('/api/admin/pricing',status_code=201)
def add_pricing(data:PriceEntry,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    row=data.model_dump(exclude={'slug'})
    summary=price_analysis(row)
    cur=db.execute('''INSERT INTO price_scenarios(store_id,title,sku,price_kopeks,cost_kopeks,
      discount_bps,baseline_units,planned_units,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
      (store['id'],data.title.strip(),data.sku.strip(),data.price_kopeks,data.cost_kopeks,
       data.discount_bps,data.baseline_units,data.planned_units,now_iso()))
    audit(db,principal,'pricing.scenario',f'scenario={cur.lastrowid}')
    db.commit()
    return {'created':True,'id':cur.lastrowid,'analysis':summary}

@app.get('/api/admin/decisions')
def get_decisions(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    store=visible_store(db,slug,principal)
    return {'items':decision_report(db,store['id']),
       'methodology':'Только наблюдения с указанием объёма данных. Рекомендации — гипотезы, не прогноз прибыли.'}

@app.patch('/api/admin/decisions/{decision_key}')
def set_decision(decision_key:str,data:DecisionUpdate,slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
    require_role(principal,'owner','manager')
    store=visible_store(db,slug,principal)
    if not any(x['key']==decision_key for x in decision_report(db,store['id'])):
        raise HTTPException(404,'Актуальное решение не найдено')
    db.execute('''INSERT INTO decision_tasks(store_id,decision_key,status,note,updated_at) VALUES(?,?,?,?,?)
      ON CONFLICT(store_id,decision_key) DO UPDATE SET status=excluded.status,note=excluded.note,updated_at=excluded.updated_at''',
       (store['id'],decision_key,data.status,data.note.strip(),now_iso()))
    audit(db,principal,'decision.update',decision_key)
    db.commit()
    return {'saved':True,'key':decision_key,'status':data.status}

app.include_router(workflows_router(admin, db_conn))
app.include_router(r07_router(admin, db_conn))
app.include_router(r08_router(admin, db_conn))
app.include_router(r09_router(admin, db_conn))
app.include_router(r10_router(admin, db_conn))
app.include_router(r11_router(admin, db_conn))
app.include_router(r12_router(admin, db_conn))

@app.get("/{path:path}",include_in_schema=False)
def spa(path:str):
    if path.startswith("api/") or path=="api":
        raise HTTPException(404,"API route not found")
    return FileResponse(FRONTEND/"index.html",headers={"Cache-Control":"no-store"})
