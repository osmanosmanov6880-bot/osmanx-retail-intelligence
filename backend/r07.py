"""R0.7 store operations: cycle counts, branch transfers, anonymous assistance,
zone experiments and evidence-based management brief.

Strict organization/store access, integer stock, idempotent commands and zero
personal surveillance. Reservations are never silently displaced.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, FileResponse
from pathlib import Path
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycle_counts_r07 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','applied','cancelled')),
 created_at TEXT NOT NULL, applied_at TEXT, UNIQUE(organization_id,request_id)
);
CREATE TABLE IF NOT EXISTS cycle_count_lines_r07 (
 id INTEGER PRIMARY KEY, count_id INTEGER NOT NULL REFERENCES cycle_counts_r07(id),
 inventory_id INTEGER NOT NULL REFERENCES inventory(id), sku TEXT NOT NULL,
 expected_qty INTEGER NOT NULL, expected_source TEXT NOT NULL, expected_updated_at TEXT NOT NULL,
 observed_qty INTEGER NOT NULL CHECK(observed_qty>=0),
 reason TEXT NOT NULL DEFAULT '', UNIQUE(count_id,inventory_id)
);
CREATE TABLE IF NOT EXISTS transfers_r07 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 source_store_id INTEGER NOT NULL REFERENCES stores(id), target_store_id INTEGER NOT NULL REFERENCES stores(id),
 inventory_id INTEGER NOT NULL REFERENCES inventory(id), sku TEXT NOT NULL,
 product TEXT NOT NULL, size TEXT NOT NULL, color TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 request_id TEXT NOT NULL,payload_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','shipped','received','cancelled')),
 created_at TEXT NOT NULL, shipped_at TEXT, received_at TEXT,
 UNIQUE(organization_id,request_id)
);
CREATE TABLE IF NOT EXISTS stock_adjustments_r07 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), inventory_id INTEGER NOT NULL REFERENCES inventory(id),
 delta INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('cycle_count','transfer_ship','transfer_receive')),
 reference_id INTEGER NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(kind,reference_id,inventory_id,store_id)
);
CREATE TABLE IF NOT EXISTS assistance_points_r07 (
 id INTEGER PRIMARY KEY,organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), name TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistance_requests_r07 (
 id INTEGER PRIMARY KEY,point_id INTEGER NOT NULL REFERENCES assistance_points_r07(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),request_id TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('size','help','checkout')),
 status TEXT NOT NULL CHECK(status IN ('open','accepted','resolved','cancelled')),
 created_at TEXT NOT NULL,accepted_at TEXT,resolved_at TEXT,
 UNIQUE(point_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_assistance_store_status_r07 ON assistance_requests_r07(store_id,status,created_at);
CREATE TABLE IF NOT EXISTS zone_trials_r07 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),zone_id INTEGER NOT NULL REFERENCES zones(id),
 title TEXT NOT NULL, variant_a TEXT NOT NULL, variant_b TEXT NOT NULL,
 a_start TEXT NOT NULL,a_end TEXT NOT NULL,b_start TEXT NOT NULL,b_end TEXT NOT NULL,
 notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_zone_trials_store_r07 ON zone_trials_r07(store_id,id);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def held_quantity(db: sqlite3.Connection, inventory: sqlite3.Row) -> int:
    """Support the released R0.5 reservations schema and older local development DBs."""
    columns={r['name'] for r in db.execute('PRAGMA table_info(reservations)')}
    if 'source_inventory_id' in columns:
        return int(db.execute("""SELECT COALESCE(SUM(quantity),0) FROM reservations
          WHERE source_inventory_id=? AND status='held' AND expires_at>?""",
          (inventory['id'],now_iso())).fetchone()[0])
    if 'target_store_id' in columns:
        return int(db.execute("""SELECT COUNT(*) FROM reservations
          WHERE target_store_id=? AND sku=? AND state='held' AND expires_at>?""",
          (inventory['store_id'],inventory['sku'],now_iso())).fetchone()[0])
    return 0


def begin(db):
    db.execute('BEGIN IMMEDIATE')


def finish(db):
    db.commit()


def fail(db,code:int,msg:str):
    db.rollback()
    raise HTTPException(code,msg)


def stock_row(db, inventory_id:int, store_id:int):
    r=db.execute('SELECT * FROM inventory WHERE id=? AND store_id=?',(inventory_id,store_id)).fetchone()
    if not r:raise HTTPException(404,'Позиция склада не найдена')
    return r


def scoped(db,table,object_id,principal):
    if table not in ('cycle_counts_r07','transfers_r07','zone_trials_r07'):
        raise ValueError('Invalid table')
    r=db.execute(f'SELECT * FROM {table} WHERE id=? AND organization_id=?',(object_id,principal.organization_id)).fetchone()
    if r is None: raise HTTPException(404,'Запись не найдена')
    field='source_store_id' if table=='transfers_r07' else 'store_id'
    check_store_access(db,r[field],principal)
    if table=='transfers_r07':check_store_access(db,r['target_store_id'],principal)
    return r


class CountLine(BaseModel):
    inventory_id:int=Field(gt=0)
    observed_qty:int=Field(ge=0,le=1000000)
    reason:str=Field(default='',max_length=350)

class CountCreate(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=110)
    lines:list[CountLine]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({r.inventory_id for r in self.lines})!=len(self.lines):
            raise ValueError('Нельзя дважды указать один товар')
        return self

class TransferCreate(BaseModel):
    source_slug:str=Field(min_length=1,max_length=80)
    target_slug:str=Field(min_length=1,max_length=80)
    inventory_id:int=Field(gt=0)
    quantity:int=Field(ge=1,le=10000)
    request_id:str=Field(min_length=8,max_length=110)

class PointCreate(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    name:str=Field(min_length=2,max_length=90)

class HelpRequest(BaseModel):
    request_id:str=Field(min_length=8,max_length=110)
    category:Literal['size','help','checkout']

class HelpStatus(BaseModel):
    status:Literal['accepted','resolved','cancelled']

class ZoneTrialCreate(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    zone_id:int=Field(gt=0)
    title:str=Field(min_length=4,max_length=120)
    variant_a:str=Field(min_length=1,max_length=90)
    variant_b:str=Field(min_length=1,max_length=90)
    a_start:date
    a_end:date
    b_start:date
    b_end:date
    notes:str=Field(default='',max_length=500)

    @model_validator(mode='after')
    def time_window(self):
        if not(self.a_start<=self.a_end<self.b_start<=self.b_end):
            raise ValueError('Периоды A и B должны идти последовательно без пересечений')
        if (self.b_end-self.a_start).days>180:
            raise ValueError('Для пилота выберите период до 180 дней')
        return self


def zone_trial_result(db,trial):
    store=db.execute('SELECT timezone FROM stores WHERE id=?',(trial['store_id'],)).fetchone()
    try:tz=ZoneInfo(store['timezone'] or 'UTC')
    except (ZoneInfoNotFoundError,KeyError):tz=timezone.utc
    windows=[(date.fromisoformat(trial['a_start']),date.fromisoformat(trial['a_end'])),
             (date.fromisoformat(trial['b_start']),date.fromisoformat(trial['b_end']))]
    # Bounded by 180-day trial and store+zone; protects from unbounded scans.
    rows=db.execute('SELECT quantity,source,occurred_at FROM zone_events WHERE store_id=? AND zone_id=? ORDER BY id DESC LIMIT 100001',
      (trial['store_id'],trial['zone_id'])).fetchall()
    if len(rows)>100000:raise HTTPException(413,'Слишком много событий зоны — сократите объём')
    totals=[]
    for a,b in windows:
        selected=[]
        for r in rows:
            try:
                ts=datetime.fromisoformat(r['occurred_at'])
                if ts.tzinfo is None:continue
                day=ts.astimezone(tz).date()
            except ValueError:continue
            if a<=day<=b:selected.append(r)
        days=(b-a).days+1
        n=sum(x['quantity'] for x in selected)
        totals.append({'count':n,'events':len(selected),'days':days,'per_day':round(n/days,2),
                       'sources':sorted(set(x['source'] for x in selected))})
    warnings=[]
    if min(totals[0]['events'],totals[1]['events'])<3:
        warnings.append('Мало событий в одном из периодов: вывод ненадёжен.')
    if totals[0]['sources']!=totals[1]['sources']:
        warnings.append('Разные источники измерений в периодах A и B.')
    if set(totals[0]['sources']) & {'demo','demo_sensor'} or set(totals[1]['sources']) & {'demo','demo_sensor'}:
        warnings.append('Используются демонстрационные события.')
    pct=(round((totals[1]['per_day']/totals[0]['per_day']-1)*100,2) if totals[0]['per_day']>0 else None)
    return {'id':trial['id'],'title':trial['title'],'zone_id':trial['zone_id'],
            'variant_a':trial['variant_a'],'variant_b':trial['variant_b'],'period_a':totals[0],
            'period_b':totals[1],'change_percent':pct,'warnings':warnings,
            'interpretation':'Изменение наблюдаемого потока не доказывает влияние витрины или выкладки на продажи.'}


def report_brief(db,store,slug):
    sid=store['id']
    recent=date.today()-timedelta(days=13)
    # Use capped, direct counts and label source variance; mixed counters are not silently merged into a causal claim.
    recent_text=recent.isoformat()
    sales=db.execute('''SELECT COUNT(*) n,COALESCE(SUM(amount_kopeks),0) rub FROM sales WHERE store_id=? AND occurred_at>=?''',(sid,recent_text)).fetchone()
    visits=db.execute('''SELECT source,COALESCE(SUM(quantity),0) cnt FROM visits WHERE store_id=? AND occurred_at>=? GROUP BY source''',(sid,recent_text)).fetchall()
    total_visits=sum(x['cnt'] for x in visits)
    open_requests=db.execute("SELECT COUNT(*) FROM demand WHERE store_id=? AND status IN ('open','located','notified')",(sid,)).fetchone()[0]
    pending_counts=db.execute("SELECT COUNT(*) FROM cycle_counts_r07 WHERE store_id=? AND status='pending'",(sid,)).fetchone()[0]
    applied=db.execute('''SELECT COUNT(DISTINCT c.id) FROM cycle_counts_r07 c JOIN cycle_count_lines_r07 l ON l.count_id=c.id
      WHERE c.store_id=? AND c.status='applied' AND l.expected_qty!=l.observed_qty''',(sid,)).fetchone()[0]
    in_transit=db.execute("SELECT COUNT(*) FROM transfers_r07 WHERE target_store_id=? AND status='shipped'",(sid,)).fetchone()[0]
    service=db.execute('''SELECT COUNT(*) n,COALESCE(SUM(CASE WHEN accepted_at IS NOT NULL THEN 1 ELSE 0 END),0) accepted,
       COALESCE(AVG((julianday(accepted_at)-julianday(created_at))*86400),0) seconds
       FROM assistance_requests_r07 WHERE store_id=?''',(sid,)).fetchone()
    open_service=db.execute("SELECT COUNT(*) FROM assistance_requests_r07 WHERE store_id=? AND status='open'",(sid,)).fetchone()[0]
    counts=db.execute("SELECT COUNT(*) FROM zone_trials_r07 WHERE store_id=?",(sid,)).fetchone()[0]
    lines=db.execute('''SELECT COALESCE(SUM(quantity*unit_revenue_kopeks),0) revenue,
      COALESCE(SUM(quantity*unit_cost_kopeks),0) cost,COUNT(DISTINCT sale_id) allocated
      FROM sale_items WHERE store_id=?''',(sid,)).fetchone()
    warnings=[]
    sources=[x['source'] for x in visits]
    if 'manual' in sources and any(x in sources for x in ('signed_sensor','sensor','demo_sensor')):
        warnings.append('Смешанный подсчёт посещений: возможны дубли между ручными и автоматическими событиями.')
    if any(x.startswith('demo') for x in sources):warnings.append('Посещаемость включает демонстрационные события.')
    if sales['n'] and lines['allocated']<sales['n']:
        warnings.append('Маржа рассчитана только по разнесённым строкам чеков, а не по всем продажам.')
    if not total_visits:warnings.append('Нет подтверждённых данных о посещаемости за период.')
    if pending_counts:warnings.append('Есть незавершённые инвентаризации — остатки требуют проверки.')
    priorities=[]
    if open_requests:priorities.append({'title':'Разобрать неудовлетворённый спрос','evidence':f'{open_requests} незакрытых запросов','priority':'high'})
    if pending_counts:priorities.append({'title':'Завершить инвентаризацию','evidence':f'{pending_counts} ожидают применения','priority':'high'})
    if in_transit:priorities.append({'title':'Подтвердить доставку между филиалами','evidence':f'{in_transit} перемещений в пути','priority':'medium'})
    if open_service:priorities.append({'title':'Ответить на вызовы покупателей','evidence':f'{open_service} обращений без ответа','priority':'high'})
    return {'store':slug,'generated_at':now_iso(),'window_days':14,
      'metrics':{'visitors':total_visits,'visitor_sources':[dict(x) for x in visits],
                 'sales':sales['n'],'revenue_kopeks':sales['rub'],
                 'conversion_percent':round(sales['n']/total_visits*100,2) if total_visits else None,
                 'open_demand':open_requests,'pending_counts':pending_counts,
                 'counts_with_variance':applied,'transfers_in_transit':in_transit,
                 'service_requests':service['n'],'service_open':open_service,
                 'service_accepted':service['accepted'],
                 'avg_response_seconds':round(service['seconds']) if service['accepted'] else None,
                 'zone_experiments':counts,'sku_revenue_kopeks':lines['revenue'],'allocated_sales':lines['allocated'],
                 'sku_gross_margin_kopeks':lines['revenue']-lines['cost']},
      'warnings':warnings,'priorities':priorities,
      'disclaimer':'Описательная аналитика по имеющимся записям. Корреляции не доказывают причинность; валовая маржа не равна чистой прибыли.'}


def build_router(admin_dependency, db_dependency):
    router=APIRouter(tags=['R0.7: операционное управление'])

    @router.get('/api/admin/r07/stock')
    def stock(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        data=[]
        for inv in db.execute('SELECT * FROM inventory WHERE store_id=? ORDER BY product,size LIMIT 500',(st['id'],)):
            held=held_quantity(db,inv)
            data.append({**dict(inv),'reserved':held,'available':max(0,inv['quantity']-held)})
        return {'items':data}

    @router.get('/api/admin/r07/counts')
    def counts(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        items=[]
        for row in db.execute('SELECT * FROM cycle_counts_r07 WHERE store_id=? ORDER BY id DESC LIMIT 100',(st['id'],)):
            details=[dict(r) for r in db.execute('SELECT * FROM cycle_count_lines_r07 WHERE count_id=?',(row['id'],))]
            items.append({**dict(row),'lines':details,'variance_units':sum(x['observed_qty']-x['expected_qty'] for x in details)})
        return {'items':items}

    @router.post('/api/admin/r07/counts',status_code=201)
    def create_count(payload:CountCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        st=visible_store(db,payload.slug,principal)
        digest=identity(payload.model_dump())
        begin(db)
        try:
            existing=db.execute('SELECT id,payload_hash,status FROM cycle_counts_r07 WHERE organization_id=? AND request_id=?',
                (principal.organization_id,payload.request_id)).fetchone()
            if existing:
                if existing['payload_hash']!=digest:fail(db,409,'Идентификатор уже использован с другими данными')
                finish(db);return {'id':existing['id'],'status':existing['status'],'duplicate':True}
            now=now_iso()
            cur=db.execute('''INSERT INTO cycle_counts_r07(organization_id,store_id,request_id,payload_hash,status,created_at)
              VALUES(?,?,?,?,?,?)''',(principal.organization_id,st['id'],payload.request_id,digest,'pending',now))
            for item in payload.lines:
                inv=stock_row(db,item.inventory_id,st['id'])
                if item.observed_qty<held_quantity(db,inv):fail(db,409,'Подсчитанный остаток ниже действующих резервов')
                if item.observed_qty!=inv['quantity'] and len(item.reason.strip())<4:
                    fail(db,422,'Для расхождения необходимо краткое объяснение')
                db.execute('''INSERT INTO cycle_count_lines_r07(count_id,inventory_id,sku,expected_qty,expected_source,expected_updated_at,observed_qty,reason)
                  VALUES(?,?,?,?,?,?,?,?)''',(cur.lastrowid,inv['id'],inv['sku'],inv['quantity'],inv['source'],inv['updated_at'],item.observed_qty,item.reason.strip()))
            audit(db,principal,'r07.count.create',str(cur.lastrowid));finish(db)
            return {'id':cur.lastrowid,'status':'pending','duplicate':False}
        except Exception:
            db.rollback();raise

    @router.post('/api/admin/r07/counts/{count_id}/apply')
    def apply_count(count_id:int,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        begin(db)
        try:
            row=scoped(db,'cycle_counts_r07',count_id,principal)
            if row['status']=='applied':finish(db);return {'applied':True,'duplicate':True,'id':count_id}
            if row['status']!='pending':fail(db,409,'Инвентаризация уже закрыта')
            lines=db.execute('SELECT * FROM cycle_count_lines_r07 WHERE count_id=?',(count_id,)).fetchall()
            now=datetime.now(timezone.utc).isoformat(timespec='microseconds')
            for line in lines:
                inv=stock_row(db,line['inventory_id'],row['store_id'])
                if (inv['quantity'],inv['source'],inv['updated_at'])!=(line['expected_qty'],line['expected_source'],line['expected_updated_at']):
                    fail(db,409,'Остатки изменились после подсчёта; начните новую инвентаризацию')
                if line['observed_qty']<held_quantity(db,inv):fail(db,409,'Нельзя списать забронированные товары')
            for line in lines:
                delta=line['observed_qty']-line['expected_qty']
                if delta:
                    result=db.execute('UPDATE inventory SET quantity=?,source=?,updated_at=? WHERE id=? AND quantity=?',
                      (line['observed_qty'],'cycle_count',now,line['inventory_id'],line['expected_qty']))
                    if result.rowcount!=1:fail(db,409,'Конфликт при сохранении остатка')
                    db.execute('''INSERT INTO stock_adjustments_r07(organization_id,store_id,inventory_id,delta,kind,reference_id,created_at)
                      VALUES(?,?,?,?,?,?,?)''',(principal.organization_id,row['store_id'],line['inventory_id'],delta,'cycle_count',count_id,now))
            db.execute('UPDATE cycle_counts_r07 SET status=?,applied_at=? WHERE id=?',('applied',now,count_id))
            audit(db,principal,'r07.count.apply',str(count_id));finish(db)
            return {'id':count_id,'applied':True,'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r07/counts/{count_id}/cancel')
    def cancel_count(count_id:int,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        with db:
            row=scoped(db,'cycle_counts_r07',count_id,principal)
            if row['status']=='cancelled':return {'id':count_id,'status':'cancelled','duplicate':True}
            if row['status']!='pending':raise HTTPException(409,'Применённую инвентаризацию отменить нельзя')
            db.execute('UPDATE cycle_counts_r07 SET status=? WHERE id=?',('cancelled',count_id))
            audit(db,principal,'r07.count.cancel',str(count_id))
        return {'id':count_id,'status':'cancelled','duplicate':False}

    @router.get('/api/admin/r07/transfers')
    def list_transfers(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        rows=db.execute('''SELECT t.*,a.name AS source_name,b.name AS target_name
          FROM transfers_r07 t JOIN stores a ON a.id=t.source_store_id JOIN stores b ON b.id=t.target_store_id
          WHERE t.organization_id=? AND (t.source_store_id=? OR t.target_store_id=?) ORDER BY t.id DESC LIMIT 100''',
          (principal.organization_id,st['id'],st['id'])).fetchall()
        results=[]
        for row in rows:
            if principal.role!='owner':
                try:check_store_access(db,row['source_store_id'],principal);check_store_access(db,row['target_store_id'],principal)
                except HTTPException:continue
            results.append(dict(row))
        return {'items':results}

    @router.post('/api/admin/r07/transfers',status_code=201)
    def create_transfer(payload:TransferCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        source=visible_store(db,payload.source_slug,principal)
        dest=visible_store(db,payload.target_slug,principal)
        if source['id']==dest['id']:raise HTTPException(422,'Укажите другой филиал')
        digest=identity(payload.model_dump())
        begin(db)
        try:
            existing=db.execute('SELECT id,payload_hash,status FROM transfers_r07 WHERE organization_id=? AND request_id=?',
              (principal.organization_id,payload.request_id)).fetchone()
            if existing:
                if existing['payload_hash']!=digest:fail(db,409,'Идентификатор уже использован для другого перемещения')
                finish(db);return {'id':existing['id'],'status':existing['status'],'duplicate':True}
            inv=stock_row(db,payload.inventory_id,source['id'])
            if payload.quantity>inv['quantity']-held_quantity(db,inv):fail(db,409,'Недостаточно свободного товара')
            now=now_iso()
            cursor=db.execute('''INSERT INTO transfers_r07(organization_id,source_store_id,target_store_id,inventory_id,
              sku,product,size,color,quantity,request_id,payload_hash,status,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,source['id'],dest['id'],inv['id'],inv['sku'],inv['product'],inv['size'],inv['color'],
              payload.quantity,payload.request_id,digest,'draft',now))
            audit(db,principal,'r07.transfer.create',str(cursor.lastrowid));finish(db)
            return {'id':cursor.lastrowid,'status':'draft','duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r07/transfers/{transfer_id}/{action}')
    def transition(transfer_id:int,action:Literal['ship','receive','cancel'],principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        begin(db)
        try:
            tx=scoped(db,'transfers_r07',transfer_id,principal)
            now=now_iso()
            if action=='cancel':
                if tx['status']!='draft':fail(db,409,'Отменить можно только черновик перемещения')
                db.execute('UPDATE transfers_r07 SET status=? WHERE id=?',('cancelled',transfer_id))
            elif action=='ship':
                if tx['status']!='draft':fail(db,409,'Перемещение уже отправлено или закрыто')
                inv=stock_row(db,tx['inventory_id'],tx['source_store_id'])
                if inv['sku']!=tx['sku'] or tx['quantity']>inv['quantity']-held_quantity(db,inv):
                    fail(db,409,'Доступный остаток изменился; отправка запрещена')
                new=inv['quantity']-tx['quantity']
                result=db.execute('UPDATE inventory SET quantity=?,source=?,updated_at=? WHERE id=? AND quantity=?',
                  (new,'transfer_ship',now,inv['id'],inv['quantity']))
                if result.rowcount!=1:fail(db,409,'Конфликт склада при отправке')
                db.execute('''INSERT INTO stock_adjustments_r07(organization_id,store_id,inventory_id,delta,kind,reference_id,created_at)
                   VALUES(?,?,?,?,?,?,?)''',(principal.organization_id,tx['source_store_id'],inv['id'],-tx['quantity'],'transfer_ship',transfer_id,now))
                db.execute('UPDATE transfers_r07 SET status=?,shipped_at=? WHERE id=?',('shipped',now,transfer_id))
            elif action=='receive':
                if tx['status']=='received':finish(db);return {'id':transfer_id,'status':'received','duplicate':True}
                if tx['status']!='shipped':fail(db,409,'Сначала отправьте товар')
                existing=db.execute('SELECT * FROM inventory WHERE store_id=? AND sku=?',(tx['target_store_id'],tx['sku'])).fetchone()
                if existing:
                    if (existing['product'],existing['size'],existing['color'])!=(tx['product'],tx['size'],tx['color']):
                        fail(db,409,'Артикул в филиале назначения имеет другие характеристики')
                    updated=db.execute('UPDATE inventory SET quantity=?,source=?,updated_at=? WHERE id=? AND quantity=?',
                      (existing['quantity']+tx['quantity'],'transfer_receive',now,existing['id'],existing['quantity']))
                    if updated.rowcount!=1:fail(db,409,'Конфликт склада при приёмке')
                    inventory_id=existing['id']
                else:
                    inventory_id=db.execute('''INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
                      VALUES(?,?,?,?,?,?,?,?)''',(tx['target_store_id'],tx['sku'],tx['product'],tx['size'],tx['color'],tx['quantity'],'transfer_receive',now)).lastrowid
                db.execute('''INSERT INTO stock_adjustments_r07(organization_id,store_id,inventory_id,delta,kind,reference_id,created_at)
                  VALUES(?,?,?,?,?,?,?)''',(principal.organization_id,tx['target_store_id'],inventory_id,tx['quantity'],'transfer_receive',transfer_id,now))
                db.execute('UPDATE transfers_r07 SET status=?,received_at=? WHERE id=?',('received',now,transfer_id))
            audit(db,principal,'r07.transfer.'+action,str(transfer_id));finish(db)
            return {'id':transfer_id,'status':{'cancel':'cancelled','ship':'shipped','receive':'received'}[action],'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r07/assistance')
    def assistance(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        pts=[dict(r) for r in db.execute('SELECT id,name,active,created_at FROM assistance_points_r07 WHERE store_id=? ORDER BY id DESC',(st['id'],))]
        req=[dict(r) for r in db.execute('''SELECT q.*,p.name AS point_name FROM assistance_requests_r07 q
          JOIN assistance_points_r07 p ON p.id=q.point_id WHERE q.store_id=? ORDER BY q.id DESC LIMIT 100''',(st['id'],))]
        return {'points':pts,'requests':req}

    @router.post('/api/admin/r07/assistance/points',status_code=201)
    def create_point(payload:PointCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        st=visible_store(db,payload.slug,principal)
        token=secrets.token_urlsafe(27)
        h=hashlib.sha256(token.encode()).hexdigest()
        with db:
            pid=db.execute('''INSERT INTO assistance_points_r07(organization_id,store_id,name,token_hash,created_at)
              VALUES(?,?,?,?,?)''',(principal.organization_id,st['id'],payload.name.strip(),h,now_iso())).lastrowid
            audit(db,principal,'r07.assistance.point.create',str(pid))
        return {'id':pid,'path':'/assist/'+token,'token_once':token,'notice':'Скопируйте ссылку сейчас — ключ не хранится в открытом виде.'}

    @router.post('/api/admin/r07/assistance/points/{point_id}/disable')
    def disable_point(point_id:int,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        p=db.execute('SELECT * FROM assistance_points_r07 WHERE id=? AND organization_id=?',(point_id,principal.organization_id)).fetchone()
        if not p:raise HTTPException(404,'Точка не найдена')
        check_store_access(db,p['store_id'],principal)
        with db:
            db.execute('UPDATE assistance_points_r07 SET active=0 WHERE id=?',(point_id,))
            audit(db,principal,'r07.assistance.point.disable',str(point_id))
        return {'disabled':True}

    @router.post('/api/assist/{token}',status_code=201)
    def public_help(token:str,payload:HelpRequest,db:sqlite3.Connection=Depends(db_dependency)):
        if len(token)>150:raise HTTPException(404,'Точка не найдена')
        h=hashlib.sha256(token.encode()).hexdigest()
        begin(db)
        try:
            p=db.execute('SELECT id,store_id FROM assistance_points_r07 WHERE token_hash=? AND active=1',(h,)).fetchone()
            if not p:fail(db,404,'Точка не найдена или отключена')
            old=db.execute('SELECT id,category,status FROM assistance_requests_r07 WHERE point_id=? AND request_id=?',
              (p['id'],payload.request_id)).fetchone()
            if old:
                if old['category']!=payload.category:fail(db,409,'Повторный запрос имеет другое содержание')
                finish(db);return {'id':old['id'],'status':old['status'],'duplicate':True}
            pending=db.execute("SELECT COUNT(*) FROM assistance_requests_r07 WHERE point_id=? AND status IN ('open','accepted')",(p['id'],)).fetchone()[0]
            if pending>=3:fail(db,429,'Сотрудник уже получил несколько запросов. Обратитесь к персоналу напрямую.')
            now=now_iso()
            last=db.execute('SELECT created_at FROM assistance_requests_r07 WHERE point_id=? ORDER BY id DESC LIMIT 1',(p['id'],)).fetchone()
            if last and (datetime.now(timezone.utc)-datetime.fromisoformat(last['created_at'])).total_seconds()<5:
                fail(db,429,'Запрос уже передан. Повторите позже.')
            req=db.execute('''INSERT INTO assistance_requests_r07(point_id,store_id,request_id,category,status,created_at)
              VALUES(?,?,?,?,?,?)''',(p['id'],p['store_id'],payload.request_id,payload.category,'open',now))
            finish(db);return {'id':req.lastrowid,'status':'open','duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/api/admin/r07/assistance/{help_id}/status')
    def update_help(help_id:int,payload:HelpStatus,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        begin(db)
        try:
            h=db.execute('''SELECT q.* FROM assistance_requests_r07 q JOIN stores s ON s.id=q.store_id
              WHERE q.id=? AND s.organization_id=?''',(help_id,principal.organization_id)).fetchone()
            if not h:fail(db,404,'Запрос не найден')
            check_store_access(db,h['store_id'],principal)
            transitions={'open':{'accepted','cancelled'},'accepted':{'resolved','cancelled'}}
            if payload.status==h['status']:
                finish(db);return {'id':help_id,'status':payload.status,'duplicate':True}
            if payload.status not in transitions.get(h['status'],set()):fail(db,409,'Недопустимая смена статуса')
            now=now_iso()
            field='accepted_at' if payload.status=='accepted' else 'resolved_at'
            db.execute(f'UPDATE assistance_requests_r07 SET status=?,{field}=? WHERE id=?',(payload.status,now,help_id))
            audit(db,principal,'r07.assistance.'+payload.status,str(help_id));finish(db)
            return {'id':help_id,'status':payload.status,'duplicate':False}
        except Exception:db.rollback();raise

    @router.get('/api/admin/r07/zone-trials')
    def zone_trials(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        zones=[dict(z) for z in db.execute('SELECT id,code,name FROM zones WHERE store_id=? ORDER BY id',(st['id'],))]
        items=[zone_trial_result(db,x) for x in db.execute('SELECT * FROM zone_trials_r07 WHERE store_id=? ORDER BY id DESC LIMIT 50',(st['id'],))]
        return {'zones':zones,'items':items}

    @router.post('/api/admin/r07/zone-trials',status_code=201)
    def create_trial(payload:ZoneTrialCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        st=visible_store(db,payload.slug,principal)
        z=db.execute('SELECT id FROM zones WHERE id=? AND store_id=?',(payload.zone_id,st['id'])).fetchone()
        if not z:raise HTTPException(404,'Зона не найдена')
        with db:
            cur=db.execute('''INSERT INTO zone_trials_r07(organization_id,store_id,zone_id,title,variant_a,variant_b,
              a_start,a_end,b_start,b_end,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,st['id'],payload.zone_id,payload.title,payload.variant_a,payload.variant_b,
               payload.a_start.isoformat(),payload.a_end.isoformat(),payload.b_start.isoformat(),payload.b_end.isoformat(),payload.notes,now_iso()))
            audit(db,principal,'r07.zone_trial.create',str(cur.lastrowid))
        return {'id':cur.lastrowid,'report':zone_trial_result(db,db.execute('SELECT * FROM zone_trials_r07 WHERE id=?',(cur.lastrowid,)).fetchone())}

    @router.get('/api/admin/r07/brief')
    def brief(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        return report_brief(db,st,slug)

    @router.get('/api/admin/r07/brief.csv')
    def export_brief(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        st=visible_store(db,slug,principal)
        result=report_brief(db,st,slug)
        out=io.StringIO();w=csv.writer(out)
        w.writerow(['OSMANX R0.7','Филиал',safe_spreadsheet_cell(st['name'])])
        w.writerow(['Период','Последние 14 дней',''])
        for k,v in result['metrics'].items():
            w.writerow(['Показатель',k,safe_spreadsheet_cell(str(v))])
        for warn in result['warnings']:w.writerow(['Предупреждение',safe_spreadsheet_cell(warn),''])
        for task in result['priorities']:w.writerow(['Приоритет',safe_spreadsheet_cell(task['title']),safe_spreadsheet_cell(task['evidence'])])
        w.writerow(['Методология',safe_spreadsheet_cell(result['disclaimer']),''])
        audit(db,principal,'r07.brief.export',str(st['id']));db.commit()
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={
          'Content-Disposition':'attachment; filename="osmanx-r07-brief.csv"','Cache-Control':'no-store'})

    @router.get("/assist/{token}",include_in_schema=False)
    def help_page(token:str):
        if len(token)>150 or not token:
            raise HTTPException(404,"Ссылка недействительна")
        return FileResponse(Path(__file__).resolve().parent.parent/"frontend"/"assist.html",headers={"Cache-Control":"no-store"})

    return router
