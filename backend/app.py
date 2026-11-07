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
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from backend.analytics import REASONS, dashboard
from backend.database import connect, initialize_db, now_iso

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
    return {"demo":DEMO,"auth_required":not DEMO,"features":{"camera":"not_connected","pos":"manual_or_json_import","surveys":"active"}}


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
    return {"slug":row["slug"],"name":row["name"],"subtitle":row["subtitle"],"incentive":row["incentive"]}


@app.post("/api/public/survey/{slug}",status_code=201)
def create_survey(slug: str, value: Survey,request: Request,db: sqlite3.Connection=Depends(db_conn)):
    rate_limit(request,"survey",12,300)
    store = find_store(db,slug)
    if value.purchased and value.reason:
        raise HTTPException(422,"Причина отказа допустима только без покупки")
    db.execute("INSERT INTO surveys(store_id,rating,purchased,reason,liked,suggestion,created_at) VALUES(?,?,?,?,?,?,?)",
        (store["id"],value.rating,int(value.purchased),value.reason,value.liked,value.suggestion,now_iso()))
    db.commit()
    return {"saved":True,"message":"Спасибо! Ваше мнение сохранено."}


@app.get("/api/admin/stores",dependencies=[Depends(admin)])
def stores(db:sqlite3.Connection=Depends(db_conn)):
    return [dict(row) for row in db.execute("SELECT slug,name,subtitle,incentive FROM stores ORDER BY id").fetchall()]


@app.get("/api/admin/dashboard",dependencies=[Depends(admin)])
def get_dashboard(slug: str="central",days:int=30,db:sqlite3.Connection=Depends(db_conn)):
    if days not in (7, 30):
        raise HTTPException(422,"Период должен составлять 7 или 30 дней")
    return dashboard(db,find_store(db,slug)["id"],days)


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
    cur=db.execute("UPDATE demand SET status=?,updated_at=? WHERE id=?",
        (data.status,now_iso(),demand_id))
    if not cur.rowcount:
        raise HTTPException(404,"Запрос не найден")
    db.commit()
    return {"saved":True}


@app.put("/api/admin/store/{slug}",dependencies=[Depends(admin)])
def update_store(slug:str,data:StoreUpdate,db:sqlite3.Connection=Depends(db_conn)):
    store=find_store(db,slug)
    db.execute("UPDATE stores SET name=?,subtitle=?,incentive=? WHERE id=?",
        (data.name.strip(),data.subtitle.strip(),data.incentive.strip(),store["id"]))
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


@app.get("/{path:path}",include_in_schema=False)
def spa(path:str):
    if path.startswith("api/") or path=="api":
        raise HTTPException(404,"API route not found")
    return FileResponse(FRONTEND/"index.html",headers={"Cache-Control":"no-store"})
