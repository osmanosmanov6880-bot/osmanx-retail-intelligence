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
from datetime import datetime, timezone
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

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DEMO = os.getenv("OSMANX_DEMO_MODE", "0") == "1"
PASSWORD = os.getenv("OSMANX_ADMIN_PASSWORD", "")
SECRET = os.getenv("OSMANX_SESSION_SECRET", "")
INGEST_KEY = os.getenv("OSMANX_INGEST_KEY", "")
LIMITS: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not DEMO and (len(PASSWORD) < 12 or len(SECRET) < 32):
        raise RuntimeError("Set OSMANX_ADMIN_PASSWORD (12+ chars) and OSMANX_SESSION_SECRET (32+ chars). For local demo only: OSMANX_DEMO_MODE=1")
    initialize_db(demo=DEMO)
    yield


app = FastAPI(title="OSMANX Retail Intelligence", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs" if DEMO else None, redoc_url=None, openapi_url="/api/openapi.json" if DEMO else None)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def response_guards(request: Request, call_next):
    result = await call_next(request)
    result.headers["X-Content-Type-Options"] = "nosniff"
    result.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
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


def token_for_admin() -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp":int(time.time())+8*3600,"nonce":secrets.token_hex(8)},
            separators=(",",":")).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def admin(authorization: str | None = Header(default=None)) -> bool:
    if DEMO:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401,"Требуется вход администратора")
    token = authorization[7:]
    try:
        payload, signature = token.split(".",1)
        expected = hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):
            raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "="*((-len(payload))%4)))
        if not isinstance(data.get("exp"),int) or data["exp"] < time.time():
            raise ValueError("expired")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401,"Сессия недействительна или истекла") from None
    return True


def find_store(db: sqlite3.Connection, slug: str):
    row = db.execute("SELECT * FROM stores WHERE slug=?",(slug,)).fetchone()
    if not row:
        raise HTTPException(404,"Магазин не найден")
    return row


class Login(BaseModel):
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


@app.get("/api/config")
def config():
    return {"demo":DEMO,"auth_required":not DEMO,"features":{"camera":"not_connected","pos":"manual_or_json_import","surveys":"active","inventory":"manual_and_batch","rewards":"optional_manual_validation","experiments":"active"}}


@app.post("/api/auth/login")
def login(value: Login,request: Request):
    if DEMO:
        return {"token":"demo","expires_in":28800}
    rate_limit(request,"login",6,900)
    if not hmac.compare_digest(value.password.encode(),PASSWORD.encode()):
        raise HTTPException(401,"Неверный пароль")
    return {"token":token_for_admin(),"expires_in":28800}


@app.get("/api/public/store/{slug}")
def public_store(slug: str,db: sqlite3.Connection=Depends(db_conn)):
    row = find_store(db,slug)
    return {"slug":row["slug"],"name":row["name"],"subtitle":row["subtitle"],"incentive":row["incentive"],"reward_enabled":bool(row["reward_enabled"]),"reward_label":row["reward_label"]}


@app.post("/api/public/survey/{slug}",status_code=201)
def create_survey(slug: str, value: Survey,request: Request,db: sqlite3.Connection=Depends(db_conn)):
    rate_limit(request,"survey",120,300)
    store = find_store(db,slug)
    if value.purchased and value.reason:
        raise HTTPException(422,"Причина отказа допустима только без покупки")
    if value.request_id:
        existing=db.execute('SELECT id FROM surveys WHERE store_id=? AND request_id=?',(store['id'],value.request_id)).fetchone()
        if existing:
            reward=db.execute('SELECT code,label,expires_at FROM rewards WHERE survey_id=?',(existing['id'],)).fetchone()
            return {'saved':True,'duplicate':True,'reward':dict(reward) if reward else None}
    try:
        cur=db.execute("""INSERT INTO surveys(store_id,rating,purchased,reason,liked,suggestion,request_id,liked_tags,improve_tags,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
           (store['id'],value.rating,int(value.purchased),value.reason,value.liked,value.suggestion,
            value.request_id,json.dumps(value.liked_tags,ensure_ascii=False),json.dumps(value.improve_tags,ensure_ascii=False),now_iso()))
        reward = None
        if store['reward_enabled'] and store['reward_label']:
            reward=create_reward(db,store['id'],cur.lastrowid,store['reward_label'])
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise HTTPException(409,'Повторная отправка анкеты') from None
    return {'saved':True,'duplicate':False,'reward':reward}



@app.get("/api/admin/stores",dependencies=[Depends(admin)])
def stores(db:sqlite3.Connection=Depends(db_conn)):
    return [dict(row) for row in db.execute("SELECT slug,name,subtitle,incentive,timezone,reward_enabled,reward_label FROM stores ORDER BY id").fetchall()]


@app.get("/api/admin/dashboard",dependencies=[Depends(admin)])
def get_dashboard(slug: str="central",days:int=30,db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7, 30):
        raise HTTPException(422,"Период должен составлять 7 или 30 дней")
    store=find_store(db,slug)
    return dashboard(db,store['id'],days,store['timezone'])


@app.post("/api/admin/events",dependencies=[Depends(admin)],status_code=201)
def manual_event(data:ManualEvent,db:sqlite3.Connection=Depends(db_conn)):
    store_id=find_store(db,data.slug)["id"]
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


@app.post("/api/admin/demand",dependencies=[Depends(admin)],status_code=201)
def create_demand(data:DemandCreate,db:sqlite3.Connection=Depends(db_conn)):
    store_id=find_store(db,data.slug)["id"]
    timestamp=now_iso()
    cur=db.execute("INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (store_id,data.product.strip(),data.size.strip(),data.color.strip(),timestamp,timestamp))
    db.commit()
    return {"saved":True,"id":cur.lastrowid}


@app.patch("/api/admin/demand/{demand_id}",dependencies=[Depends(admin)])
def set_demand(demand_id:int,data:DemandStatus,db:sqlite3.Connection=Depends(db_conn)):
    previous=db.execute('SELECT status,sale_id FROM demand WHERE id=?',(demand_id,)).fetchone()
    if not previous: raise HTTPException(404,'Запрос не найден')
    if data.status == 'converted' and previous['sale_id'] is None:
        raise HTTPException(422,'Подтвердите покупку через привязку кассового чека')
    if previous['status'] != data.status:
        db.execute('UPDATE demand SET status=?,updated_at=? WHERE id=?',(data.status,now_iso(),demand_id))
        db.execute('INSERT INTO demand_history(demand_id,previous_status,next_status,occurred_at) VALUES(?,?,?,?)',
                   (demand_id,previous['status'],data.status,now_iso()))
    db.commit()
    return {'saved':True}


@app.put("/api/admin/store/{slug}",dependencies=[Depends(admin)])
def update_store(slug:str,data:StoreUpdate,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    db.execute("UPDATE stores SET name=?,subtitle=?,incentive=?,timezone=?,reward_enabled=?,reward_label=? WHERE id=?",
        (data.name.strip(),data.subtitle.strip(),data.incentive.strip(),data.timezone,int(data.reward_enabled),
         data.reward_label.strip(),store['id']))
    db.commit()
    return {"saved":True}


@app.post("/api/admin/import/pos",dependencies=[Depends(admin)])
def import_pos(data:PosBatch,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,data.slug)
    imported=0
    for row in data.sales:
        cur=db.execute("INSERT OR IGNORE INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)",
            (store["id"],round(row.amount_rub*100),"pos_import",row.occurred_at.astimezone(timezone.utc).isoformat(timespec="seconds"),row.external_id))
        imported+=cur.rowcount
    db.commit()
    return {"imported":imported,"duplicates":len(data.sales)-imported}


@app.post("/api/ingest/traffic",status_code=201)
def ingest_traffic(data:TrafficIngest,x_osmanx_ingest_key:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_conn)):
    if not INGEST_KEY or not x_osmanx_ingest_key or not hmac.compare_digest(x_osmanx_ingest_key,INGEST_KEY):
        raise HTTPException(401,"Неверный ключ интеграции")
    store=find_store(db,data.slug)
    when=data.occurred_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    cur=db.execute("INSERT OR IGNORE INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)",
       (store["id"],data.quantity,"sensor",when,data.external_id))
    db.commit()
    return {"saved":bool(cur.rowcount),"duplicate":not bool(cur.rowcount)}


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

@app.post('/api/admin/zones',dependencies=[Depends(admin)],status_code=201)
def create_zone(data:ZoneCreate,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,data.slug)
    db.execute("""INSERT INTO zones(store_id,code,name,x,y) VALUES(?,?,?,?,?)
        ON CONFLICT(store_id,code) DO UPDATE SET name=excluded.name,x=excluded.x,y=excluded.y""",
        (store['id'],data.code,data.name.strip(),data.x,data.y))
    db.commit()
    return {'saved':True}

@app.get('/api/admin/zones',dependencies=[Depends(admin)])
def get_zones(slug:str='central',db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    return [dict(r) for r in db.execute('SELECT id,code,name,x,y FROM zones WHERE store_id=? ORDER BY id',(store['id'],))]

@app.post('/api/ingest/zones',status_code=201)
def ingest_zones(data:ZoneIngest,x_osmanx_ingest_key:str|None=Header(default=None),db:sqlite3.Connection=Depends(db_conn)):
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


@app.post('/api/admin/stores',dependencies=[Depends(admin)],status_code=201)
def add_store(data:NewStore,db:sqlite3.Connection=Depends(db_conn)):
    try:
        db.execute('INSERT INTO stores(slug,name,timezone,created_at) VALUES(?,?,?,?)',
                   (data.slug,data.name.strip(),data.timezone,now_iso()))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409,'Филиал с таким кодом уже существует') from None
    return {'created':True,'slug':data.slug}


@app.get('/api/admin/stock',dependencies=[Depends(admin)])
def get_stock(slug:str='central',db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    return {'store':slug,'items':stock_for_store(db,store['id'])}


@app.post('/api/admin/stock/import',dependencies=[Depends(admin)])
def import_stock(value:StockImport,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,value.slug)
    stamp=now_iso()
    # Reject duplicate SKUs within a batch to avoid a hidden last-row-wins rule.
    skus=[x.sku.strip().casefold() for x in value.items]
    if len(skus)!=len(set(skus)):
        raise HTTPException(422,'Повторяющиеся артикулы в одном импорте')
    for item in value.items:
        db.execute("""INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(store_id,sku) DO UPDATE SET
          product=excluded.product,size=excluded.size,color=excluded.color,
          quantity=excluded.quantity,source=excluded.source,updated_at=excluded.updated_at""",
          (store['id'],item.sku.strip(),item.product.strip(),item.size.strip(),item.color.strip(),
           item.quantity,value.source,stamp))
    db.commit()
    return {'imported':len(value.items),'store':value.slug}


@app.get('/api/admin/demand/{demand_id}/matches',dependencies=[Depends(admin)])
def demand_matches(demand_id:int,db:sqlite3.Connection=Depends(db_conn)):
    item=db.execute('SELECT * FROM demand WHERE id=?',(demand_id,)).fetchone()
    if not item: raise HTTPException(404,'Запрос не найден')
    return {'matches':stock_matches(db,item['store_id'],item['product'],item['size'],item['color']),
            'method':'Точное совпадение товара, размера и цвета; без проверки доступности для резерва.'}


@app.post('/api/admin/demand/{demand_id}/convert',dependencies=[Depends(admin)])
def confirm_demand(demand_id:int,value:ConfirmDemandSale,db:sqlite3.Connection=Depends(db_conn)):
    item=db.execute('SELECT * FROM demand WHERE id=?',(demand_id,)).fetchone()
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


@app.get('/api/admin/experiments',dependencies=[Depends(admin)])
def get_experiments(slug:str='central',db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    return [dict(r) for r in db.execute('SELECT * FROM experiments WHERE store_id=? ORDER BY updated_at DESC,id DESC LIMIT 100',(store['id'],))]


@app.post('/api/admin/experiments',dependencies=[Depends(admin)],status_code=201)
def create_experiment(data:ExperimentCreate,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,data.slug)
    now=now_iso()
    cur=db.execute('INSERT INTO experiments(store_id,title,hypothesis,metric,baseline,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (store['id'],data.title.strip(),data.hypothesis.strip(),data.metric,data.baseline,now,now))
    db.commit()
    return {'created':True,'id':cur.lastrowid}


@app.patch('/api/admin/experiments/{experiment_id}',dependencies=[Depends(admin)])
def update_experiment(experiment_id:int,data:ExperimentUpdate,db:sqlite3.Connection=Depends(db_conn)):
    current=db.execute('SELECT * FROM experiments WHERE id=?',(experiment_id,)).fetchone()
    if not current: raise HTTPException(404,'Гипотеза не найдена')
    if data.status=='finished' and data.result is None:
        raise HTTPException(422,'Для завершения укажите измеренный результат')
    db.execute('UPDATE experiments SET status=?,result=?,notes=?,updated_at=? WHERE id=?',
               (data.status,data.result,data.notes.strip(),now_iso(),experiment_id))
    db.commit()
    return {'saved':True}


@app.get('/api/admin/report/daily',dependencies=[Depends(admin)])
def report_daily(slug:str='central',days:int=30,db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7,30): raise HTTPException(422,'Поддерживаются 7 или 30 дней')
    store=find_store(db,slug)
    return {'timezone':store['timezone'],'days':daily_metrics(db,store['id'],store['timezone'],days)}


@app.get('/api/admin/export/{dataset}.csv',dependencies=[Depends(admin)])
def export_report(dataset:str,slug:str='central',db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    try: contents=csv_report(db,store['id'],dataset)
    except ValueError: raise HTTPException(404,'Отчёт не найден') from None
    return Response(contents,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="osmanx-{dataset}-{slug}.csv"',
        'Cache-Control':'no-store'})


@app.post('/api/admin/rewards/redeem',dependencies=[Depends(admin)])
def redeem_reward(data:RewardRedemption,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,data.slug)
    reward=db.execute('SELECT * FROM rewards WHERE code=? AND store_id=?',
                      (data.code.strip().upper(),store['id'])).fetchone()
    if not reward: raise HTTPException(404,'Код не найден')
    if reward['redeemed_at']: raise HTTPException(409,'Бонус уже погашен')
    if reward['expires_at']<now_iso(): raise HTTPException(410,'Срок действия бонуса истёк')
    db.execute('UPDATE rewards SET redeemed_at=? WHERE id=? AND redeemed_at IS NULL',
               (now_iso(),reward['id']))
    db.commit()
    return {'redeemed':True,'label':reward['label'],'code':reward['code']}



@app.get("/{path:path}",include_in_schema=False)
def spa(path:str):
    if path.startswith("api/") or path=="api":
        raise HTTPException(404,"API route not found")
    return FileResponse(FRONTEND/"index.html",headers={"Cache-Control":"no-store"})
