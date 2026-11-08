"""R0.6: demand recovery, purchasing, SKU evidence, before/after evaluation and action center.

Every write is store/organization scoped. Financial amounts are integer kopeks.
No invented sales, unverified profit claims or customer tracking.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS demand_cases (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), demand_id INTEGER NOT NULL UNIQUE REFERENCES demand(id),
 sku TEXT NOT NULL, requested_quantity INTEGER NOT NULL CHECK(requested_quantity BETWEEN 1 AND 100),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','reserved','ordered','converted','closed')),
 reservation_id INTEGER UNIQUE REFERENCES reservations(id), order_line_id INTEGER REFERENCES purchase_order_lines(id),
 sale_id INTEGER UNIQUE REFERENCES sales(id), notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_demand_cases_store ON demand_cases(store_id,status);
CREATE TABLE IF NOT EXISTS purchase_orders (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), supplier TEXT NOT NULL,
 reference TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft'
 CHECK(status IN ('draft','ordered','partial','received','cancelled')),
 expected_date TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(store_id,reference)
);
CREATE TABLE IF NOT EXISTS purchase_order_lines (
 id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
 sku TEXT NOT NULL, product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '',
 color TEXT NOT NULL DEFAULT '', ordered_qty INTEGER NOT NULL CHECK(ordered_qty BETWEEN 1 AND 10000),
 received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty>=0 AND received_qty<=ordered_qty),
 unit_cost_kopeks INTEGER NOT NULL CHECK(unit_cost_kopeks>=0), UNIQUE(order_id,sku)
);
CREATE TABLE IF NOT EXISTS purchase_receipts (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 order_id INTEGER NOT NULL REFERENCES purchase_orders(id), external_id TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL, received_at TEXT NOT NULL, UNIQUE(order_id,external_id)
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), sku TEXT NOT NULL,
 delta INTEGER NOT NULL CHECK(delta>0), kind TEXT NOT NULL CHECK(kind='purchase_receipt'),
 receipt_id INTEGER NOT NULL REFERENCES purchase_receipts(id), line_id INTEGER NOT NULL REFERENCES purchase_order_lines(id),
 created_at TEXT NOT NULL, UNIQUE(receipt_id,line_id)
);
CREATE TABLE IF NOT EXISTS sale_items (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), sale_id INTEGER NOT NULL REFERENCES sales(id),
 sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 unit_revenue_kopeks INTEGER NOT NULL CHECK(unit_revenue_kopeks>=0),
 unit_cost_kopeks INTEGER NOT NULL CHECK(unit_cost_kopeks>=0),
 external_id TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE(store_id,external_id)
);
CREATE INDEX IF NOT EXISTS ix_sale_items_sale ON sale_items(sale_id);
CREATE TABLE IF NOT EXISTS decision_evaluations (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), experiment_id INTEGER NOT NULL REFERENCES experiments(id),
 metric TEXT NOT NULL CHECK(metric IN ('conversion','visitors','purchases','revenue')),
 source_mode TEXT NOT NULL CHECK(source_mode IN ('manual','sensor','combined')),
 before_start TEXT NOT NULL,before_end TEXT NOT NULL,after_start TEXT NOT NULL,after_end TEXT NOT NULL,
 before_value REAL,after_value REAL,delta REAL,warnings_json TEXT NOT NULL DEFAULT '[]',
 notes TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decision_evaluations_store ON decision_evaluations(store_id,created_at);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def price_kopeks(v: Decimal) -> int:
    return int((v * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def valid_store(db, principal, slug):
    return visible_store(db, slug, principal)


def ensure_order(db, principal, id):
    row = db.execute('SELECT * FROM purchase_orders WHERE id=? AND organization_id=?',
                     (id, principal.organization_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Заказ не найден')
    check_store_access(db, row['store_id'], principal)
    return row


def ensure_case(db, principal, case_id):
    row = db.execute('SELECT * FROM demand_cases WHERE id=? AND organization_id=?',
                     (case_id, principal.organization_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Запрос не найден')
    check_store_access(db, row['store_id'], principal)
    return row


class CaseCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    demand_id: int = Field(gt=0)
    sku: str = Field(min_length=1,max_length=100)
    requested_quantity: int = Field(default=1,ge=1,le=100)
    notes: str = Field(default='',max_length=500)


class CaseLink(BaseModel):
    action: Literal['reserve','order','convert','close']
    reservation_id: int|None = Field(default=None,gt=0)
    order_line_id: int|None = Field(default=None,gt=0)
    sale_id: int|None = Field(default=None,gt=0)
    notes: str = Field(default='',max_length=500)


class OrderLine(BaseModel):
    sku: str = Field(min_length=1,max_length=100)
    product: str = Field(min_length=1,max_length=120)
    size: str = Field(default='',max_length=40)
    color: str = Field(default='',max_length=40)
    quantity: int = Field(ge=1,le=10000)
    unit_cost_rub: Decimal = Field(ge=0,le=20000000,decimal_places=2)


class OrderCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    supplier: str = Field(min_length=2,max_length=150)
    reference: str = Field(min_length=3,max_length=100)
    expected_date: date|None = None
    lines: list[OrderLine] = Field(min_length=1,max_length=50)


class OrderTransition(BaseModel):
    status: Literal['ordered','cancelled']


class ReceiptLine(BaseModel):
    line_id: int = Field(gt=0)
    quantity: int = Field(ge=1,le=10000)


class ReceiptCreate(BaseModel):
    external_id: str = Field(min_length=3,max_length=100)
    lines: list[ReceiptLine] = Field(min_length=1,max_length=50)


class SaleItemCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    sale_id: int = Field(gt=0)
    sku: str = Field(min_length=1,max_length=100)
    quantity: int = Field(ge=1,le=10000)
    unit_revenue_rub: Decimal = Field(ge=0,le=20000000,decimal_places=2)
    unit_cost_rub: Decimal = Field(ge=0,le=20000000,decimal_places=2)
    external_id: str = Field(min_length=3,max_length=100)


class EvaluationCreate(BaseModel):
    slug: str = Field(min_length=1,max_length=80)
    experiment_id: int = Field(gt=0)
    metric: Literal['conversion','visitors','purchases','revenue']
    source_mode: Literal['manual','sensor','combined'] = 'sensor'
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    notes: str = Field(default='',max_length=1000)


def comparable_periods(db, store, metric, source_mode, left_start, left_end, right_start, right_end):
    """Date boundary comparisons use the store's actual timezone, not text ISO sorting."""
    try:
        tz=ZoneInfo(store['timezone'] or 'UTC')
    except (ZoneInfoNotFoundError, KeyError):
        tz=timezone.utc
    lo=datetime.combine(left_start,time.min,tzinfo=tz).astimezone(timezone.utc)
    hi=datetime.combine(right_end+timedelta(days=1),time.min,tzinfo=tz).astimezone(timezone.utc)
    start_utc=lo.isoformat(timespec='seconds')
    sources={'manual':{'manual'},'sensor':{'signed_sensor','sensor','demo_sensor'}}
    # Pre-filter with generous buffer; offsets in incoming ISO strings may vary.
    cutoff=(lo-timedelta(days=2)).date().isoformat()
    visits=db.execute('SELECT source,quantity,occurred_at FROM visits WHERE store_id=? AND occurred_at>=? LIMIT 200001',
                      (store['id'],cutoff)).fetchall()
    sales=db.execute('SELECT source,amount_kopeks,occurred_at FROM sales WHERE store_id=? AND occurred_at>=? LIMIT 200001',
                     (store['id'],cutoff)).fetchall()
    if len(visits)>200000 or len(sales)>200000:
        raise HTTPException(413, 'Слишком большой период для интерактивной проверки; сократите диапазон')
    intervals=[(left_start,left_end),(right_start,right_end)]
    warning=[]
    def selected(record):
        try: ts=datetime.fromisoformat(record['occurred_at'])
        except ValueError: return None
        if ts.tzinfo is None: return None
        return ts.astimezone(tz).date()
    vs=[]; ss=[]
    for a,b in intervals:
        v=[r for r in visits if (date_value:=selected(r)) is not None and a<=date_value<=b
           and (source_mode=='combined' or r['source'] in sources[source_mode])]
        s=[r for r in sales if (date_value:=selected(r)) is not None and a<=date_value<=b]
        visitors=sum(r['quantity'] for r in v)
        purchases=len(s)
        vs.append({'visitors':visitors,'purchases':purchases,'revenue':sum(r['amount_kopeks'] for r in s)/100,
                   'conversion':round(purchases/visitors*100,3) if visitors else None,
                   'visit_sources':sorted({r['source'] for r in v}), 'sale_sources':sorted({r['source'] for r in s})})
    if source_mode=='combined' and any('manual' in r['visit_sources'] and set(r['visit_sources']) & sources['sensor'] for r in vs):
        warning.append('Смешаны ручной и автоматический подсчёт: возможны дубли.')
    if vs[0]['visit_sources'] != vs[1]['visit_sources']:
        warning.append('Источники посещений различаются между периодами.')
    if any(r['visitors'] and r['purchases']>r['visitors'] for r in vs):
        warning.append('Чеков больше, чем входов: конверсия может быть недостоверной.')
    if any(any(name.startswith('demo') for name in r['visit_sources']+r['sale_sources']) for r in vs):
        warning.append('В сравнении присутствуют демонстрационные данные.')
    if not all(r['visitors'] for r in vs) and metric=='conversion':
        warning.append('Недостаточно данных о посещаемости для расчёта конверсии.')
    if not any(r['purchases'] for r in vs):
        warning.append('Нет чеков в выбранных периодах.')
    before=vs[0][metric]; after=vs[1][metric]
    return {'before_value':before,'after_value':after,'delta':round(after-before,3) if before is not None and after is not None else None,
            'periods':vs,'warnings':warning,'disclaimer':'Сравнение до/после не доказывает, что изменение вызвано конкретным решением.'}


def build_router(admin_dependency, db_dependency):
    router=APIRouter(prefix='/api/admin/workflows',tags=['R0.6: сквозные операции'])

    @router.get('/overview')
    def overview(slug:str='central',principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        store=valid_store(db,principal,slug)
        sid=store['id']
        cases=[dict(r) for r in db.execute('''SELECT c.*,d.product,d.size,d.color FROM demand_cases c
          JOIN demand d ON d.id=c.demand_id WHERE c.store_id=? ORDER BY c.id DESC LIMIT 100''',(sid,))]
        orders=[]
        for r in db.execute('''SELECT p.*,COALESCE(SUM(l.ordered_qty*l.unit_cost_kopeks),0) as order_total_kopeks,
          COALESCE(SUM(l.received_qty*l.unit_cost_kopeks),0) as delivered_cost_kopeks,
          COALESCE(SUM(l.ordered_qty-l.received_qty),0) as outstanding_units
          FROM purchase_orders p LEFT JOIN purchase_order_lines l ON p.id=l.order_id
          WHERE p.store_id=? GROUP BY p.id ORDER BY p.id DESC LIMIT 100''',(sid,)):
            obj=dict(r)
            obj['lines']=[dict(z) for z in db.execute('SELECT * FROM purchase_order_lines WHERE order_id=? ORDER BY id',(r['id'],))]
            orders.append(obj)
        financial=db.execute('''SELECT COUNT(*) AS item_records,COALESCE(SUM(quantity*unit_revenue_kopeks),0) AS revenue_kopeks,
          COALESCE(SUM(quantity*unit_cost_kopeks),0) AS cost_kopeks FROM sale_items WHERE store_id=?''',(sid,)).fetchone()
        unassigned=db.execute('''SELECT COUNT(*) FROM sales s WHERE s.store_id=? AND NOT EXISTS
           (SELECT 1 FROM sale_items x WHERE x.sale_id=s.id)''',(sid,)).fetchone()[0]
        returns_table='merchandise_returns' if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchandise_returns'").fetchone() else 'returns_log'
        returns_total=db.execute(f'SELECT COALESCE(SUM(amount_kopeks),0) FROM {returns_table} WHERE store_id=?',(sid,)).fetchone()[0]
        evaluations=[dict(x) for x in db.execute('''SELECT e.*,d.title AS decision_title FROM decision_evaluations e
             JOIN experiments d ON d.id=e.experiment_id WHERE e.store_id=? ORDER BY e.id DESC LIMIT 40''',(sid,))]
        for row in evaluations:
            row['warnings']=json.loads(row.pop('warnings_json'))
        backlog_total=db.execute("""SELECT COUNT(*) FROM demand d WHERE d.store_id=? AND d.status IN ('open','located','notified')
          AND NOT EXISTS (SELECT 1 FROM demand_cases c WHERE c.demand_id=d.id)""",(sid,)).fetchone()[0]
        backlog=[dict(x) for x in db.execute('''SELECT d.id,d.product,d.size,d.color,d.status,d.created_at FROM demand d
          WHERE d.store_id=? AND d.status IN ('open','located','notified')
          AND NOT EXISTS (SELECT 1 FROM demand_cases c WHERE c.demand_id=d.id) ORDER BY d.id DESC LIMIT 80''',(sid,))]
        decisions=[dict(r) for r in db.execute('SELECT id,title,status,metric,baseline,result FROM experiments WHERE store_id=? ORDER BY id DESC LIMIT 100',(sid,))]
        receipts=[dict(r) for r in db.execute('''SELECT s.id,s.amount_kopeks,s.occurred_at,s.source,
            COALESCE((SELECT SUM(si.quantity*si.unit_revenue_kopeks) FROM sale_items si WHERE si.sale_id=s.id),0) allocated_kopeks
            FROM sales s WHERE s.store_id=? ORDER BY s.id DESC LIMIT 70''',(sid,))]
        reservation_columns={x['name'] for x in db.execute('PRAGMA table_info(reservations)')}
        if 'destination_store_id' in reservation_columns:
            reservations=[dict(r) for r in db.execute('''SELECT r.id,i.sku,r.status AS state,r.expires_at,r.source_store_id AS target_store_id
              FROM reservations r JOIN inventory i ON i.id=r.source_inventory_id
              WHERE r.destination_store_id=? ORDER BY r.id DESC LIMIT 50''',(sid,))]
        else:
            reservations=[dict(r) for r in db.execute("SELECT id,sku,state,expires_at,target_store_id FROM reservations WHERE store_id=? ORDER BY id DESC LIMIT 50",(sid,))]
        margin=financial['revenue_kopeks']-financial['cost_kopeks']
        pending_units=sum(o['outstanding_units'] for o in orders if o['status'] in ('ordered','partial'))
        notes=[]
        if unassigned:notes.append('Не все чеки содержат товарные строки и себестоимость: маржа охватывает только разнесённые позиции.')
        if returns_total:notes.append('Возвраты учтены отдельно: прибыль по SKU не корректируется без товарных строк возврата.')
        if any(z['warnings'] for z in evaluations):notes.append('Есть предупреждения о качестве данных в сравнении периодов.')
        return {'store':slug,'cases':cases,'unassigned_demand':backlog,'orders':orders,'decisions':decisions,
          'receipts':receipts,'reservations':reservations,
          'evaluations':evaluations,'finance':{'item_records':financial['item_records'],
          'documented_revenue_kopeks':financial['revenue_kopeks'],'documented_cost_kopeks':financial['cost_kopeks'],
          'documented_gross_margin_kopeks':margin,'receipts_without_items':unassigned,
          'store_returns_kopeks':returns_total},
          'kpi':{'open_cases':sum(c['status'] in ('open','reserved','ordered') for c in cases),
                 'awaiting_restock_units':pending_units,'unassigned_requests':backlog_total,
                 'orders_in_progress':sum(o['status'] in ('ordered','partial') for o in orders)},
          'notes':notes,'status':'Real events only; no estimated lost sales are counted as fact.'}

    @router.post('/cases',status_code=201)
    def create_case(body:CaseCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        store=valid_store(db,principal,body.slug)
        demand=db.execute('SELECT * FROM demand WHERE id=? AND store_id=?',(body.demand_id,store['id'])).fetchone()
        if not demand:raise HTTPException(404,'Запрос покупателя не найден в филиале')
        if demand['status'] in ('closed','converted'):raise HTTPException(409,'Этот запрос уже завершён')
        try:
            with db:
                cur=db.execute('INSERT INTO demand_cases(organization_id,store_id,demand_id,sku,requested_quantity,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                    (principal.organization_id,store['id'],body.demand_id,body.sku.strip(),body.requested_quantity,body.notes,now_iso(),now_iso()))
                audit(db,principal,'workflow.case.create',str(cur.lastrowid))
                return {'id':cur.lastrowid,'status':'open'}
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Для этого запроса уже существует рабочий кейс') from None

    @router.patch('/cases/{case_id}')
    def link_case(case_id:int,body:CaseLink,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        item=ensure_case(db,principal,case_id)
        if item['status'] in ('closed','converted'):raise HTTPException(409,'Кейс завершён')
        if body.action=='reserve' and item['status']=='ordered':raise HTTPException(409,'Нельзя вернуть заказанный товар в резерв')
        if body.action=='order' and item['status']=='reserved':raise HTTPException(409,'Сначала закройте бронирование')
        with db:
            reservation_id=order_line_id=sale_id=None
            status={'reserve':'reserved','order':'ordered','convert':'converted','close':'closed'}[body.action]
            if body.action=='reserve':
                cols={x['name'] for x in db.execute('PRAGMA table_info(reservations)')}
                if 'destination_store_id' in cols:
                    r=db.execute('''SELECT r.* FROM reservations r JOIN inventory i ON i.id=r.source_inventory_id
                       WHERE r.id=? AND r.organization_id=? AND r.destination_store_id=?
                       AND r.demand_id=? AND i.sku=? AND r.status='held' ''',
                       (body.reservation_id,principal.organization_id,item['store_id'],item['demand_id'],item['sku'])).fetchone()
                else:
                    r=db.execute("SELECT * FROM reservations WHERE id=? AND organization_id=? AND store_id=? AND sku=? AND state='held'",
                                 (body.reservation_id,principal.organization_id,item['store_id'],item['sku'])).fetchone()
                if not r or r['expires_at']<=now_iso():
                    raise HTTPException(422,'Нет действительного резерва для этого запроса и артикула')
                reservation_id=r['id']
                if db.execute('SELECT 1 FROM demand_cases WHERE reservation_id=? AND id<>?',(reservation_id,case_id)).fetchone():
                    raise HTTPException(409,'Резерв уже привязан к другому запросу')
            elif body.action=='order':
                r=db.execute('''SELECT l.id,l.sku,p.store_id,p.organization_id,p.status FROM purchase_order_lines l
                      JOIN purchase_orders p ON p.id=l.order_id WHERE l.id=? AND p.store_id=? AND p.organization_id=?''',
                      (body.order_line_id,item['store_id'],principal.organization_id)).fetchone()
                if not r or r['sku']!=item['sku'] or r['status'] not in ('ordered','partial','received'):
                    raise HTTPException(422,'Позиция заказа не соответствует кейсу')
                order_line_id=r['id']
            elif body.action=='convert':
                sale=db.execute('SELECT id,store_id FROM sales WHERE id=?',(body.sale_id,)).fetchone()
                if not sale:raise HTTPException(422,'Чек не найден')
                # A held reservation may be fulfilled at a destination store.
                if item['reservation_id']:
                    reservation=db.execute('SELECT * FROM reservations WHERE id=?',(item['reservation_id'],)).fetchone()
                    if not reservation:raise HTTPException(422,'Бронирование не найдено')
                    source_store_id=reservation['source_store_id'] if 'source_store_id' in reservation.keys() else reservation['target_store_id']
                    if sale['store_id'] not in (item['store_id'],source_store_id):
                        raise HTTPException(422,'Чек не принадлежит магазину обращения или резервирования')
                elif sale['store_id']!=item['store_id']:
                    raise HTTPException(422,'Чек другого филиала не доказывает конверсию')
                qty_proof=db.execute('SELECT COALESCE(SUM(quantity),0) FROM sale_items WHERE sale_id=? AND sku=?',(sale['id'],item['sku'])).fetchone()[0]
                if qty_proof < item['requested_quantity']:
                    raise HTTPException(422,'Для подтверждения требуется товарная строка чека с нужным артикулом и количеством')
                if db.execute('SELECT 1 FROM demand WHERE sale_id=? AND id<>?',(sale['id'],item['demand_id'])).fetchone():
                    raise HTTPException(409,'Чек уже подтверждает другой запрос')
                if db.execute('SELECT 1 FROM demand_cases WHERE sale_id=? AND id<>?',(sale['id'],case_id)).fetchone():
                    raise HTTPException(409,'Чек уже используется в другом кейсе')
                sale_id=sale['id']
                old_demand_status=db.execute('SELECT status FROM demand WHERE id=?',(item['demand_id'],)).fetchone()['status']
                db.execute('UPDATE demand SET status=?,sale_id=?,updated_at=? WHERE id=?',('converted',sale_id,now_iso(),item['demand_id']))
                # Sale verification is separate from R0.5 reservation collection status.
                # Never silently mutate a held/collected reservation into a POS sale.
                db.execute('''INSERT INTO demand_history(demand_id,previous_status,next_status,note,occurred_at)
                    VALUES(?,?,?,?,?)''',(item['demand_id'],
                          old_demand_status,
                          'converted','R0.6 sale '+str(sale_id),now_iso()))
            elif body.action=='close':
                if len(body.notes.strip())<5:raise HTTPException(422,'Укажите причину закрытия')
                db.execute('UPDATE demand SET status=?,updated_at=? WHERE id=?',('closed',now_iso(),item['demand_id']))
            else:raise HTTPException(422,'Недопустимый переход')
            db.execute('''UPDATE demand_cases SET status=?,reservation_id=COALESCE(?,reservation_id),
                    order_line_id=COALESCE(?,order_line_id),sale_id=COALESCE(?,sale_id),notes=?,updated_at=? WHERE id=?''',
                    (status,reservation_id,order_line_id,sale_id,body.notes or item['notes'],now_iso(),case_id))
            audit(db,principal,'workflow.case.'+body.action,str(case_id))
        return {'id':case_id,'status':status}

    @router.post('/orders',status_code=201)
    def create_order(body:OrderCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        store=valid_store(db,principal,body.slug)
        if len({line.sku.strip().casefold() for line in body.lines})!=len(body.lines):
            raise HTTPException(422,'Повторяющийся артикул в заказе')
        try:
            with db:
                cur=db.execute('''INSERT INTO purchase_orders(organization_id,store_id,supplier,reference,expected_date,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?)''',
                         (principal.organization_id,store['id'],body.supplier.strip(),body.reference.strip(),
                          body.expected_date.isoformat() if body.expected_date else None,now_iso(),now_iso()))
                oid=cur.lastrowid
                for line in body.lines:
                    db.execute('''INSERT INTO purchase_order_lines(order_id,sku,product,size,color,ordered_qty,unit_cost_kopeks)
                        VALUES(?,?,?,?,?,?,?)''',
                        (oid,line.sku.strip(),line.product.strip(),line.size.strip(),line.color.strip(),line.quantity,price_kopeks(line.unit_cost_rub)))
                audit(db,principal,'workflow.order.create',str(oid))
            return {'id':oid,'status':'draft'}
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Заказ с таким номером уже существует') from None

    @router.patch('/orders/{order_id}')
    def transition_order(order_id:int,body:OrderTransition,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        order=ensure_order(db,principal,order_id)
        if body.status=='ordered' and order['status']!='draft':raise HTTPException(409,'Отправить можно только черновик')
        if body.status=='cancelled' and order['status'] not in ('draft','ordered'):
            raise HTTPException(409,'Нельзя отменить принятый или закрытый заказ')
        if body.status=='cancelled' and db.execute('''SELECT 1 FROM purchase_order_lines WHERE order_id=? AND received_qty>0''',(order_id,)).fetchone():
            raise HTTPException(409,'Товар уже оприходован')
        with db:
            db.execute('UPDATE purchase_orders SET status=?,updated_at=? WHERE id=?',(body.status,now_iso(),order_id))
            audit(db,principal,'workflow.order.'+body.status,str(order_id))
        return {'id':order_id,'status':body.status}

    @router.post('/orders/{order_id}/receipts',status_code=201)
    def receive_order(order_id:int,body:ReceiptCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        order=ensure_order(db,principal,order_id)
        if len({x.line_id for x in body.lines})!=len(body.lines):raise HTTPException(422,'Позиция указана дважды')
        canonical=json.dumps(sorted([(x.line_id,x.quantity) for x in body.lines]),separators=(',',':'))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        db.execute('BEGIN IMMEDIATE')
        try:
            seen=db.execute('SELECT payload_sha256 FROM purchase_receipts WHERE order_id=? AND external_id=?',
                            (order_id,body.external_id)).fetchone()
            if seen:
                if seen['payload_sha256']!=digest:raise HTTPException(409,'Идентификатор поставки уже используется с другими данными')
                db.commit();return {'duplicate':True,'order_id':order_id,'received_units':0}
            status=db.execute('SELECT status FROM purchase_orders WHERE id=?',(order_id,)).fetchone()['status']
            if status not in ('ordered','partial'):raise HTTPException(409,'Заказ недоступен для приёмки')
            lines=[]
            for x in body.lines:
                line=db.execute('SELECT * FROM purchase_order_lines WHERE id=? AND order_id=?',(x.line_id,order_id)).fetchone()
                if not line:raise HTTPException(422,'Позиция не принадлежит заказу')
                if x.quantity>line['ordered_qty']-line['received_qty']:
                    raise HTTPException(409,'Количество превышает остаток заказа')
                lines.append((line,x.quantity))
            receipt_id=db.execute('''INSERT INTO purchase_receipts(organization_id,order_id,external_id,payload_sha256,received_at)
                VALUES(?,?,?,?,?)''',(principal.organization_id,order_id,body.external_id,digest,now_iso())).lastrowid
            for line,qty in lines:
                old_stock=db.execute('SELECT product,size,color FROM inventory WHERE store_id=? AND sku=?',
                                     (order['store_id'],line['sku'])).fetchone()
                if old_stock and any(old_stock[col].casefold().strip()!=line[col].casefold().strip() for col in ('product','size','color')):
                    raise HTTPException(409,'Артикул на складе принадлежит товару с другими характеристиками')
                db.execute('UPDATE purchase_order_lines SET received_qty=received_qty+? WHERE id=?',(qty,line['id']))
                db.execute('''INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
                    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(store_id,sku)
                    DO UPDATE SET quantity=inventory.quantity+excluded.quantity,updated_at=excluded.updated_at,
                      source='purchase_receipt' ''',
                   (order['store_id'],line['sku'],line['product'],line['size'],line['color'],qty,'purchase_receipt',now_iso()))
                db.execute('''INSERT INTO stock_movements(organization_id,store_id,sku,delta,kind,receipt_id,line_id,created_at)
                       VALUES(?,?,?,?,?,?,?,?)''',
                   (principal.organization_id,order['store_id'],line['sku'],qty,'purchase_receipt',receipt_id,line['id'],now_iso()))
            remaining=db.execute('SELECT COALESCE(SUM(ordered_qty-received_qty),0) FROM purchase_order_lines WHERE order_id=?',
                                 (order_id,)).fetchone()[0]
            new_status='received' if remaining==0 else 'partial'
            db.execute('UPDATE purchase_orders SET status=?,updated_at=? WHERE id=?',(new_status,now_iso(),order_id))
            audit(db,principal,'workflow.order.receive',str(order_id))
            db.commit();return {'duplicate':False,'order_id':order_id,'received_units':sum(x[1] for x in lines),
                                'remaining_units':remaining,'status':new_status}
        except Exception:
            if db.in_transaction:db.rollback()
            raise

    @router.post('/sale-items',status_code=201)
    def add_sale_item(body:SaleItemCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager')
        store=valid_store(db,principal,body.slug)
        revenue=price_kopeks(body.unit_revenue_rub)
        cost=price_kopeks(body.unit_cost_rub)
        db.execute('BEGIN IMMEDIATE')
        try:
            sale=db.execute('SELECT * FROM sales WHERE id=? AND store_id=?',(body.sale_id,store['id'])).fetchone()
            if not sale:raise HTTPException(422,'Чек другого филиала или не существует')
            assigned=db.execute('SELECT COALESCE(SUM(quantity*unit_revenue_kopeks),0) FROM sale_items WHERE sale_id=?',
                                (body.sale_id,)).fetchone()[0]
            if assigned+body.quantity*revenue>sale['amount_kopeks']:
                raise HTTPException(409,'Стоимость позиций превышает сумму чека')
            try:
                cur=db.execute('''INSERT INTO sale_items(organization_id,store_id,sale_id,sku,quantity,unit_revenue_kopeks,
                     unit_cost_kopeks,external_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (principal.organization_id,store['id'],sale['id'],body.sku.strip(),body.quantity,revenue,cost,body.external_id,now_iso()))
            except sqlite3.IntegrityError:raise HTTPException(409,'Повторный идентификатор позиции') from None
            audit(db,principal,'workflow.sale_item.record',str(cur.lastrowid))
            db.commit()
            return {'id':cur.lastrowid,'documented_margin_kopeks':body.quantity*(revenue-cost),
                    'note':'Маржа по разнесённой позиции до учёта возвратов, налогов и общих расходов.'}
        except Exception:
            if db.in_transaction:db.rollback()
            raise

    @router.post('/evaluations',status_code=201)
    def evaluate(body:EvaluationCreate,principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        require_role(principal,'owner','manager','analyst')
        store=valid_store(db,principal,body.slug)
        decision=db.execute('SELECT * FROM experiments WHERE id=? AND store_id=?',
                            (body.experiment_id,store['id'])).fetchone()
        if not decision:raise HTTPException(404,'Решение не найдено')
        if not (body.before_start<=body.before_end<body.after_start<=body.after_end<=datetime.now(timezone.utc).date()):
            raise HTTPException(422,'Периоды должны быть непересекающимися и завершёнными')
        if (body.before_end-body.before_start).days>=90 or (body.after_end-body.after_start).days>=90:
            raise HTTPException(422,'Максимальный период — 90 дней')
        comparison=comparable_periods(db,store,body.metric,body.source_mode,
             body.before_start,body.before_end,body.after_start,body.after_end)
        with db:
            cur=db.execute('''INSERT INTO decision_evaluations(organization_id,store_id,experiment_id,metric,source_mode,
              before_start,before_end,after_start,after_end,before_value,after_value,delta,warnings_json,notes,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,store['id'],body.experiment_id,body.metric,body.source_mode,
               *(x.isoformat() for x in (body.before_start,body.before_end,body.after_start,body.after_end)),
               comparison['before_value'],comparison['after_value'],comparison['delta'],
               json.dumps(comparison['warnings'],ensure_ascii=False),body.notes,now_iso()))
            audit(db,principal,'workflow.decision.evaluate',str(cur.lastrowid))
        return {'id':cur.lastrowid,**comparison}

    @router.get('/export')
    def export(slug:str='central',dataset:Literal['cases','orders','sale_items','evaluations']='cases',
               principal:Principal=Depends(admin_dependency),db:sqlite3.Connection=Depends(db_dependency)):
        store=valid_store(db,principal,slug)
        columns={
            'cases':('id','demand_id','sku','requested_quantity','status','reservation_id','order_line_id','sale_id','notes','created_at'),
            'orders':('id','reference','supplier','status','expected_date','created_at'),
            'sale_items':('id','sale_id','sku','quantity','unit_revenue_kopeks','unit_cost_kopeks','recorded_at'),
            'evaluations':('id','experiment_id','metric','source_mode','before_start','before_end','after_start','after_end','before_value','after_value','delta','created_at')
        }
        table={'cases':'demand_cases','orders':'purchase_orders','sale_items':'sale_items','evaluations':'decision_evaluations'}[dataset]
        fields=columns[dataset]
        out=io.StringIO();w=csv.writer(out);w.writerow(fields)
        for row in db.execute(f"SELECT {','.join(fields)} FROM {table} WHERE store_id=? ORDER BY id DESC LIMIT 10000",(store['id'],)):
            w.writerow([safe_spreadsheet_cell(v) for v in row])
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition':f'attachment; filename="osmanx-{dataset}.csv"','Cache-Control':'no-store'})

    return router
