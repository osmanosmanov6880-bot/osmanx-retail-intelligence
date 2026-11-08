"""R0.8: replenishment, supplier performance, fitting evidence, actions and daily brief.

All writes are tenant/store scoped. Suggestions are not purchases or revenue forecasts.
No individual video tracking, customer IDs, or automatic supplier notifications.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.security import Principal, audit, check_store_access, require_role, visible_store
from backend.retail import safe_spreadsheet_cell
from backend.r07 import held_quantity

SCHEMA = """
CREATE TABLE IF NOT EXISTS replenishment_plans_r08 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), request_id TEXT NOT NULL,
 period_days INTEGER NOT NULL, safety_units INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('draft','ordered','cancelled')),
 order_id INTEGER REFERENCES purchase_orders(id), created_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE TABLE IF NOT EXISTS replenishment_lines_r08 (
 id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES replenishment_plans_r08(id),
 sku TEXT NOT NULL, product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '',
 requests INTEGER NOT NULL CHECK(requests>=1), available INTEGER NOT NULL CHECK(available>=0),
 recommended_qty INTEGER NOT NULL CHECK(recommended_qty BETWEEN 1 AND 10000),
 UNIQUE(plan_id,sku)
);
CREATE TABLE IF NOT EXISTS supplier_reviews_r08 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), supplier TEXT NOT NULL,
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), issue TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_supplier_reviews_r08 ON supplier_reviews_r08(store_id,supplier,created_at);
CREATE TABLE IF NOT EXISTS fitting_actions_r08 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '',
 hypothesis TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','testing','done','cancelled')),
 evidence TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_tasks_r08 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), request_id TEXT NOT NULL,
 title TEXT NOT NULL, category TEXT NOT NULL CHECK(category IN ('demand','supplier','fitting','service','operations')),
 assigned_user_id INTEGER REFERENCES users(id), due_date TEXT,
 status TEXT NOT NULL CHECK(status IN ('open','in_progress','done','cancelled')),
 evidence TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_action_tasks_r08 ON action_tasks_r08(store_id,status,due_date);
CREATE TABLE IF NOT EXISTS brief_snapshots_r08 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), day TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(store_id,day)
);
"""


def ensure_schema(db:sqlite3.Connection)->None:
    db.executescript(SCHEMA)


def text_norm(value:str)->str:
    return ' '.join((value or '').casefold().strip().split())


def money(v:Decimal)->int:
    return int((v*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def tz_for(store):
    try:return ZoneInfo(store['timezone'] or 'UTC')
    except (ZoneInfoNotFoundError,KeyError):return timezone.utc


def current_day(store)->date:
    return datetime.now(timezone.utc).astimezone(tz_for(store)).date()


def store_object(db,table:str,obj:int,principal:Principal):
    if table not in ('replenishment_plans_r08','fitting_actions_r08','action_tasks_r08'):
        raise ValueError('invalid resource')
    item=db.execute(f'SELECT * FROM {table} WHERE id=? AND organization_id=?',(obj,principal.organization_id)).fetchone()
    if not item:raise HTTPException(404,'Запись не найдена')
    check_store_access(db,item['store_id'],principal)
    return item


def preview_replenishment(db,store,period_days:int,safety_units:int):
    """Interest counts are requests, not confirmed intent or predicted sales.

    Uses exact SKU mapping from existing inventory or demand_cases; unknown SKUs
    are left unresolved instead of fabricating a product identifier.
    """
    since=(datetime.now(timezone.utc)-timedelta(days=period_days)).isoformat(timespec='seconds')
    demand=db.execute("""SELECT d.id,d.product,d.size,d.color,c.sku AS case_sku
        FROM demand d LEFT JOIN demand_cases c ON c.demand_id=d.id
        WHERE d.store_id=? AND d.status IN ('open','located','notified') AND d.created_at>=?
        ORDER BY d.id DESC LIMIT 20001""",(store['id'],since)).fetchall()
    if len(demand)>20000:raise HTTPException(413,'Слишком много запросов — сократите период')
    org_stock=db.execute("""SELECT i.*,s.organization_id FROM inventory i JOIN stores s ON s.id=i.store_id
        WHERE s.organization_id=? ORDER BY i.id LIMIT 20001""",(store['organization_id'],)).fetchall()
    if len(org_stock)>20000:raise HTTPException(413,'Слишком много товарных позиций для интерактивного расчёта')
    grouped=defaultdict(list)
    for r in org_stock: grouped[(text_norm(r['product']),text_norm(r['size']),text_norm(r['color']))].append(r)
    accum=defaultdict(lambda:dict(count=0,sku='',product='',size='',color='',unknown=False,available=0))
    unresolved=[]
    for d in demand:
        key=(text_norm(d['product']),text_norm(d['size']),text_norm(d['color']))
        matches=grouped.get(key,[])
        skus={r['sku'] for r in matches}
        if d['case_sku']:skus.add(d['case_sku'])
        if len(skus)!=1:
            unresolved.append({'demand_id':d['id'],'product':d['product'],'size':d['size'],
                               'reason':'Неоднозначный артикул' if len(skus)>1 else 'Не указан артикул'})
            continue
        sku=next(iter(skus)); z=accum[sku]
        z['count']+=1;z['sku']=sku;z['product']=d['product'];z['size']=d['size'];z['color']=d['color']
    results=[]
    for z in accum.values():
        # Only the requesting branch's stock counts as immediately available.
        same=[r for r in org_stock if r['store_id']==store['id'] and r['sku']==z['sku']]
        available=sum(max(0,r['quantity']-held_quantity(db,r)) for r in same)
        z['available']=available
        # A configurable planning heuristic, never a promise of conversion.
        qty=max(0,z['count']+safety_units-available)
        if qty:
            results.append({'sku':z['sku'],'product':z['product'],'size':z['size'],'color':z['color'],
                            'requests':z['count'],'available':available,'recommended_qty':min(qty,10000)})
    results.sort(key=lambda r:(-r['requests'],r['sku']))
    return {'lines':results[:100],'unresolved':unresolved[:100],
            'total_unresolved':len(unresolved),'total_requests':len(demand),
            'method':'requests + safety_units - current_available; planning heuristic, not a sales forecast',
            'warnings':['Запрос посетителя не означает гарантированную продажу.',
                        'Если артикул не определён однозначно, товар исключён из заказа.',
                        'Доступность учитывает активные резервы в этом филиале.']}


def supplier_scorecards(db,store,days:int):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    orders=db.execute('SELECT * FROM purchase_orders WHERE store_id=? AND created_at>=? ORDER BY id DESC LIMIT 20001',
                      (store['id'],cutoff)).fetchall()
    if len(orders)>20000:raise HTTPException(413,'Сократите период анализа поставщиков')
    suppliers=defaultdict(lambda:{'orders':0,'received':0,'on_time':0,'late_received':0,
                                  'overdue_open':0,'missing_expected':0,'outstanding_units':0,'receipt_events':0})
    today=current_day(store)
    for o in orders:
        x=suppliers[o['supplier']];x['orders']+=1
        remaining=db.execute('SELECT COALESCE(SUM(ordered_qty-received_qty),0) AS n FROM purchase_order_lines WHERE order_id=?',(o['id'],)).fetchone()['n']
        x['outstanding_units']+=remaining
        if not o['expected_date']:x['missing_expected']+=1
        delivered=(o['status']=='received' and remaining==0)
        if delivered:
            x['received']+=1
            last=db.execute('SELECT MAX(received_at) FROM purchase_receipts WHERE order_id=?',(o['id'],)).fetchone()[0]
            if last and o['expected_date']:
                if date.fromisoformat(last[:10])<=date.fromisoformat(o['expected_date']):x['on_time']+=1
                else:x['late_received']+=1
        elif remaining and o['status'] not in ('cancelled','draft') and o['expected_date'] and date.fromisoformat(o['expected_date'])<today:
            x['overdue_open']+=1
    results=[]
    for name,values in suppliers.items():
        known=values['on_time']+values['late_received']
        last=db.execute('SELECT rating,issue,created_at FROM supplier_reviews_r08 WHERE store_id=? AND supplier=? ORDER BY id DESC LIMIT 3',(store['id'],name)).fetchall()
        results.append({'supplier':name,**values,
          'on_time_percent':round(values['on_time']/known*100,1) if known>=3 else None,
          'samples_for_timeliness':known,'reviews':[dict(r) for r in last],
          'warnings':(['Мало подтверждённых поставок: оценка срока ненадёжна.'] if known<3 else [])+
                     (['У части заказов нет плановой даты.'] if values['missing_expected'] else [])})
    return sorted(results,key=lambda x:(-x['overdue_open'],-x['outstanding_units'],x['supplier']))


def fitting_insights(db,store,days:int):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    # Exact local R0.7 schema uses fittings; legacy released R0.5 used fitting_observations.
    has_observations=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fitting_observations'").fetchone()
    has_fittings=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fittings'").fetchone()
    acc=defaultdict(lambda:{'trials':0,'purchases':0,'reasons':defaultdict(int),'rows':0})
    if has_observations:
        rows=db.execute('SELECT product,size,trials,purchases,reason FROM fitting_observations WHERE store_id=? AND observed_at>=? LIMIT 20001',(store['id'],cutoff)).fetchall()
        if len(rows)>20000:raise HTTPException(413,'Сократите период')
        for r in rows:
            key=(text_norm(r['product']),text_norm(r['size']))
            b=acc[key];b['trials']+=r['trials'];b['purchases']+=r['purchases'];b['rows']+=1
            if r['reason']!='none':b['reasons'][r['reason']]+=max(1,r['trials']-r['purchases'])
    elif has_fittings:
        rows=db.execute('SELECT sku,quantity,outcome,reason FROM fittings WHERE store_id=? AND occurred_at>=? LIMIT 20001',(store['id'],cutoff)).fetchall()
        if len(rows)>20000:raise HTTPException(413,'Сократите период')
        for r in rows:
            b=acc[(text_norm(r['sku']),'')];b['rows']+=1;b['trials']+=r['quantity']
            if r['outcome']=='purchased':b['purchases']+=r['quantity']
            else:b['reasons'][r['reason'] or 'other']+=r['quantity']
    out=[]
    for (product,size),a in acc.items():
        conversion=round(a['purchases']/a['trials']*100,1) if a['trials'] else None
        out.append({'product':product,'size':size,'trials':a['trials'],'purchases':a['purchases'],
                    'conversion_percent':conversion,'reasons':dict(a['reasons']),'samples':a['rows'],
                    'signal':'needs_review' if a['trials']>=5 and conversion<25 else 'insufficient' if a['trials']<5 else 'normal',
                    'warning':'Причины отказа фиксируются вручную и могут быть неполными.'})
    out.sort(key=lambda x:(x['signal']!='needs_review',-x['trials']))
    return out[:100]


def daily_brief(db,store,day:date):
    tz=tz_for(store)
    start=datetime.combine(day,time.min,tzinfo=tz).astimezone(timezone.utc)
    end=datetime.combine(day+timedelta(days=1),time.min,tzinfo=tz).astimezone(timezone.utc)
    # Fetch bounded data; timestamp offsets may vary, so compare parsed UTC dates.
    cutoff=(start-timedelta(days=2)).date().isoformat()
    visits=db.execute('SELECT quantity,source,occurred_at FROM visits WHERE store_id=? AND occurred_at>=? LIMIT 100001',(store['id'],cutoff)).fetchall()
    sales=db.execute('SELECT amount_kopeks,source,occurred_at FROM sales WHERE store_id=? AND occurred_at>=? LIMIT 100001',(store['id'],cutoff)).fetchall()
    if len(visits)>100000 or len(sales)>100000:raise HTTPException(413,'Слишком много событий за период')
    def within(row):
        try:
            t=datetime.fromisoformat(row['occurred_at'])
            return t.tzinfo is not None and start<=t.astimezone(timezone.utc)<end
        except (TypeError,ValueError):return False
    vv=[r for r in visits if within(r)];ss=[r for r in sales if within(r)]
    sources=sorted({r['source'] for r in vv})
    by_source={source:sum(r['quantity'] for r in vv if r['source']==source) for source in sources}
    visitors=sum(r['quantity'] for r in vv)
    purchases=len(ss)
    outstanding=db.execute("SELECT COUNT(*) FROM demand WHERE store_id=? AND status IN ('open','located','notified')",(store['id'],)).fetchone()[0]
    tasks=db.execute("SELECT status,COUNT(*) n FROM action_tasks_r08 WHERE store_id=? GROUP BY status",(store['id'],)).fetchall()
    tasks_by_status={r['status']:r['n'] for r in tasks}
    help_q=db.execute("SELECT COUNT(*) FROM assistance_requests_r07 WHERE store_id=? AND status IN ('open','accepted')",(store['id'],)).fetchone()[0]
    pending_transfer=db.execute("SELECT COUNT(*) FROM transfers_r07 WHERE (source_store_id=? OR target_store_id=?) AND status='shipped'",(store['id'],store['id'])).fetchone()[0]
    warnings=[]
    if not vv:warnings.append('Нет зарегистрированных посещений за выбранный день.')
    if 'manual' in sources and any(s!='manual' for s in sources):warnings.append('Возможно двойное суммирование ручного и автоматического потока.')
    if any('demo' in s for s in sources) or any('demo' in r['source'] for r in ss):warnings.append('Обнаружены демонстрационные данные; не использовать как фактическую отчётность.')
    if purchases>visitors and vv:warnings.append('Продаж больше, чем посещений: проверьте источники и период.')
    if not ss:warnings.append('Нет чеков за выбранный день либо источник кассы ещё не подключён.')
    return {'store':store['slug'],'day':day.isoformat(),'timezone':str(tz),'visitors':visitors,
            'visitor_sources':by_source,'purchases':purchases,'revenue_kopeks':sum(r['amount_kopeks'] for r in ss),
            'conversion_percent':round(purchases/visitors*100,2) if visitors else None,
            'open_demand':outstanding,'open_assistance':help_q,'in_transit_transfers':pending_transfer,
            'tasks':tasks_by_status,'warnings':warnings,
            'methodology':'Only recorded visits and receipts; gross receipt revenue before returns, not net profit; no inferred customer motives or profit forecasts.'}


class PlanRequest(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=120)
    period_days:int=Field(default=30,ge=7,le=90)
    safety_units:int=Field(default=0,ge=0,le=50)

class CostLine(BaseModel):
    sku:str=Field(min_length=1,max_length=100)
    unit_cost_rub:Decimal=Field(gt=0,le=20000000,decimal_places=2)

class ConvertPlan(BaseModel):
    supplier:str=Field(min_length=2,max_length=150)
    reference:str=Field(min_length=3,max_length=100)
    expected_date:date|None=None
    costs:list[CostLine]=Field(min_length=1,max_length=100)

class ReviewRequest(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    supplier:str=Field(min_length=2,max_length=150)
    rating:int=Field(ge=1,le=5)
    issue:str=Field(default='',max_length=400)

class FittingActionRequest(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    product:str=Field(min_length=2,max_length=120)
    size:str=Field(default='',max_length=40)
    hypothesis:str=Field(min_length=8,max_length=500)

class FittingStatusRequest(BaseModel):
    status:Literal['testing','done','cancelled']
    evidence:str=Field(default='',max_length=1200)

class TaskRequest(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=120)
    title:str=Field(min_length=5,max_length=180)
    category:Literal['demand','supplier','fitting','service','operations']
    assigned_user_id:int|None=Field(default=None,gt=0)
    due_date:date|None=None

class TaskUpdate(BaseModel):
    status:Literal['in_progress','done','cancelled']
    evidence:str=Field(default='',max_length=1200)


def build_router(admin_dep,db_dep):
    router=APIRouter(prefix='/api/admin/r08',tags=['R0.8: коммерческие решения'])

    @router.get('/replenishment/preview')
    def preview(slug:str='central',period_days:int=30,safety_units:int=0,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        if not (7<=period_days<=90 and 0<=safety_units<=50):raise HTTPException(422,'Недопустимый период или страховой запас')
        store=visible_store(db,slug,principal)
        return preview_replenishment(db,store,period_days,safety_units)

    @router.get('/replenishment')
    def list_plans(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        result=[]
        for p in db.execute('SELECT * FROM replenishment_plans_r08 WHERE store_id=? ORDER BY id DESC LIMIT 40',(store['id'],)):
            entry=dict(p);entry['lines']=[dict(x) for x in db.execute('SELECT * FROM replenishment_lines_r08 WHERE plan_id=? ORDER BY requests DESC',(p['id'],))];result.append(entry)
        return {'items':result}

    @router.post('/replenishment',status_code=201)
    def create_plan(payload:PlanRequest,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT * FROM replenishment_plans_r08 WHERE organization_id=? AND request_id=?',(principal.organization_id,payload.request_id)).fetchone()
            if old:
                if (old['store_id'],old['period_days'],old['safety_units'])!=(store['id'],payload.period_days,payload.safety_units):
                    raise HTTPException(409,'Идентификатор повторно использован для другого плана')
                db.commit();return {'id':old['id'],'status':old['status'],'duplicate':True}
            report=preview_replenishment(db,store,payload.period_days,payload.safety_units)
            if not report['lines']:raise HTTPException(422,'Не найдено товарных предложений с однозначным артикулом')
            pid=db.execute('''INSERT INTO replenishment_plans_r08(organization_id,store_id,request_id,period_days,safety_units,status,created_at)
               VALUES(?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.request_id,payload.period_days,payload.safety_units,'draft',now_iso())).lastrowid
            for x in report['lines']:
                db.execute('''INSERT INTO replenishment_lines_r08(plan_id,sku,product,size,color,requests,available,recommended_qty)
                  VALUES(?,?,?,?,?,?,?,?)''',(pid,x['sku'],x['product'],x['size'],x['color'],x['requests'],x['available'],x['recommended_qty']))
            audit(db,principal,'r08.replenishment.create',str(pid));db.commit()
            return {'id':pid,'status':'draft','lines':len(report['lines']),'duplicate':False}
        except Exception:db.rollback();raise

    @router.post('/replenishment/{plan_id}/order',status_code=201)
    def plan_to_order(plan_id:int,payload:ConvertPlan,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        plan=store_object(db,'replenishment_plans_r08',plan_id,principal)
        db.execute('BEGIN IMMEDIATE')
        try:
            plan=store_object(db,'replenishment_plans_r08',plan_id,principal)
            if plan['status']=='ordered':db.commit();return {'id':plan['order_id'],'duplicate':True,'status':'draft'}
            if plan['status']!='draft':raise HTTPException(409,'План закрыт')
            lines=[dict(x) for x in db.execute('SELECT * FROM replenishment_lines_r08 WHERE plan_id=?',(plan_id,))]
            costs={x.sku:money(x.unit_cost_rub) for x in payload.costs}
            if len(costs)!=len(payload.costs) or set(costs)!={x['sku'] for x in lines}:
                raise HTTPException(422,'Укажите себестоимость отдельно для каждой позиции плана')
            now=now_iso()
            try:
                oid=db.execute('''INSERT INTO purchase_orders(organization_id,store_id,supplier,reference,status,expected_date,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?)''',(principal.organization_id,plan['store_id'],payload.supplier.strip(),payload.reference.strip(),
                    'draft',payload.expected_date.isoformat() if payload.expected_date else None,now,now)).lastrowid
            except sqlite3.IntegrityError:raise HTTPException(409,'Этот номер заказа уже существует в филиале') from None
            for x in lines:
                db.execute('''INSERT INTO purchase_order_lines(order_id,sku,product,size,color,ordered_qty,unit_cost_kopeks)
                   VALUES(?,?,?,?,?,?,?)''',(oid,x['sku'],x['product'],x['size'],x['color'],x['recommended_qty'],costs[x['sku']]))
            db.execute("UPDATE replenishment_plans_r08 SET status='ordered',order_id=? WHERE id=?",(oid,plan_id))
            audit(db,principal,'r08.replenishment.convert',str(oid));db.commit()
            return {'id':oid,'status':'draft','duplicate':False,'lines':len(lines)}
        except Exception:db.rollback();raise

    @router.get('/suppliers')
    def suppliers(slug:str='central',days:int=180,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        if not 7<=days<=365:raise HTTPException(422,'Недопустимый период')
        store=visible_store(db,slug,principal)
        return {'items':supplier_scorecards(db,store,days),'warnings':['Процент соблюдения срока показывается только при 3+ завершённых заказах с датой.']}

    @router.post('/suppliers/review',status_code=201)
    def review(payload:ReviewRequest,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        if not db.execute('SELECT 1 FROM purchase_orders WHERE store_id=? AND supplier=? LIMIT 1',(store['id'],payload.supplier.strip())).fetchone():
            raise HTTPException(422,'Поставщик отсутствует в заказах этого филиала')
        with db:
            iid=db.execute('''INSERT INTO supplier_reviews_r08(organization_id,store_id,supplier,rating,issue,created_at)
             VALUES(?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.supplier.strip(),payload.rating,payload.issue.strip(),now_iso())).lastrowid
            audit(db,principal,'r08.supplier.review',str(iid))
        return {'id':iid}

    @router.get('/fittings')
    def fittings(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        if not 7<=days<=180:raise HTTPException(422,'Недопустимый период')
        store=visible_store(db,slug,principal)
        actions=[dict(r) for r in db.execute('SELECT * FROM fitting_actions_r08 WHERE store_id=? ORDER BY id DESC LIMIT 100',(store['id'],))]
        return {'items':fitting_insights(db,store,days),'actions':actions}

    @router.post('/fittings/actions',status_code=201)
    def create_fitting_action(payload:FittingActionRequest,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        with db:
            now=now_iso()
            iid=db.execute('''INSERT INTO fitting_actions_r08(organization_id,store_id,product,size,hypothesis,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.product.strip(),payload.size.strip(),payload.hypothesis.strip(),'open',now,now)).lastrowid
            audit(db,principal,'r08.fitting.action.create',str(iid))
        return {'id':iid,'status':'open'}

    @router.patch('/fittings/actions/{action_id}')
    def update_fitting(action_id:int,payload:FittingStatusRequest,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        row=store_object(db,'fitting_actions_r08',action_id,principal)
        if row['status'] in ('done','cancelled'):raise HTTPException(409,'Завершённое наблюдение не изменяется')
        if payload.status=='done' and len(payload.evidence.strip())<12:
            raise HTTPException(422,'Для завершения укажите проверяемый результат (12+ символов)')
        with db:
            db.execute('UPDATE fitting_actions_r08 SET status=?,evidence=?,updated_at=? WHERE id=?',
                       (payload.status,payload.evidence.strip(),now_iso(),action_id))
            audit(db,principal,'r08.fitting.action.update',str(action_id))
        return {'id':action_id,'status':payload.status}

    @router.get('/tasks')
    def tasks(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        items=[dict(x) for x in db.execute('''SELECT t.*,u.full_name AS assigned_name FROM action_tasks_r08 t LEFT JOIN users u ON u.id=t.assigned_user_id
           WHERE t.store_id=? ORDER BY (t.status IN ('done','cancelled')),t.due_date ASC,t.id DESC LIMIT 200''',(store['id'],))]
        return {'items':items}

    @router.post('/tasks',status_code=201)
    def create_task(payload:TaskRequest,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        if payload.assigned_user_id:
            user=db.execute('SELECT * FROM users WHERE id=? AND organization_id=? AND active=1',(payload.assigned_user_id,principal.organization_id)).fetchone()
            if not user:raise HTTPException(422,'Сотрудник не найден')
            if user['role']!='owner':check_store_access(db,store['id'],Principal(user['id'],principal.organization_id,user['email'],user['role']))
        with db:
            existing=db.execute('SELECT id,title,category,store_id FROM action_tasks_r08 WHERE organization_id=? AND request_id=?',(principal.organization_id,payload.request_id)).fetchone()
            if existing:
                if existing['title']!=payload.title or existing['category']!=payload.category or existing['store_id']!=store['id']:
                    raise HTTPException(409,'Идентификатор задачи уже используется')
                return {'id':existing['id'],'duplicate':True}
            now=now_iso()
            iid=db.execute('''INSERT INTO action_tasks_r08(organization_id,store_id,request_id,title,category,assigned_user_id,due_date,status,created_at,updated_at)
             VALUES(?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],payload.request_id,payload.title.strip(),payload.category,
              payload.assigned_user_id,payload.due_date.isoformat() if payload.due_date else None,'open',now,now)).lastrowid
            audit(db,principal,'r08.task.create',str(iid))
        return {'id':iid,'duplicate':False,'status':'open'}

    @router.patch('/tasks/{task_id}')
    def update_task(task_id:int,payload:TaskUpdate,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        row=store_object(db,'action_tasks_r08',task_id,principal)
        if row['status'] in ('done','cancelled'):raise HTTPException(409,'Задача уже завершена')
        if payload.status=='done' and len(payload.evidence.strip())<12:
            raise HTTPException(422,'Для закрытия задачи нужен проверяемый результат (12+ символов)')
        with db:
            db.execute('UPDATE action_tasks_r08 SET status=?,evidence=?,updated_at=? WHERE id=?',
                       (payload.status,payload.evidence.strip(),now_iso(),task_id))
            audit(db,principal,'r08.task.update',str(task_id))
        return {'id':task_id,'status':payload.status}

    @router.get('/brief')
    def brief(slug:str='central',day:date|None=None,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        target=day or current_day(store)
        if target>current_day(store) or (current_day(store)-target).days>366:
            raise HTTPException(422,'Дата вне допустимого диапазона')
        return daily_brief(db,store,target)

    @router.post('/brief/snapshot',status_code=201)
    def snapshot(slug:str='central',day:date|None=None,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,slug,principal)
        target=day or current_day(store)
        if target>current_day(store) or (current_day(store)-target).days>366:
            raise HTTPException(422,'Дата вне допустимого диапазона')
        value=daily_brief(db,store,target)
        encoded=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        with db:
            existing=db.execute('SELECT * FROM brief_snapshots_r08 WHERE store_id=? AND day=?',(store['id'],target.isoformat())).fetchone()
            if existing:
                return {'id':existing['id'],'duplicate':True,'saved_sha256':existing['payload_sha256'],'current_sha256':digest}
            iid=db.execute('''INSERT INTO brief_snapshots_r08(organization_id,store_id,day,payload_json,payload_sha256,created_at)
               VALUES(?,?,?,?,?,?)''',(principal.organization_id,store['id'],target.isoformat(),encoded,digest,now_iso())).lastrowid
            audit(db,principal,'r08.brief.snapshot',str(iid))
        return {'id':iid,'duplicate':False,'saved_sha256':digest}

    @router.get('/brief/snapshots')
    def snapshots(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return {'items':[{'id':r['id'],'day':r['day'],'payload_sha256':r['payload_sha256'],
                         'created_at':r['created_at'],'brief':json.loads(r['payload_json'])}
                         for r in db.execute('SELECT * FROM brief_snapshots_r08 WHERE store_id=? ORDER BY day DESC LIMIT 90',(store['id'],))]}

    @router.get('/brief/export.csv')
    def export(slug:str='central',day:date|None=None,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        target=day or current_day(store)
        if target>current_day(store) or (current_day(store)-target).days>366:raise HTTPException(422,'Недопустимая дата')
        data=daily_brief(db,store,target)
        buf=io.StringIO();writer=csv.writer(buf)
        writer.writerow(['Показатель','Значение'])
        for field,label in [('day','Дата'),('visitors','Посетители'),('purchases','Покупки'),('revenue_kopeks','Выручка, коп'),
                            ('conversion_percent','Конверсия, %'),('open_demand','Открытый спрос'),('open_assistance','Запросы помощи'),
                            ('in_transit_transfers','Перемещения в пути')]:
            writer.writerow([label,safe_spreadsheet_cell(data[field])])
        writer.writerow(['Предупреждения',safe_spreadsheet_cell('; '.join(data['warnings']))])
        return Response('\ufeff'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={
          'Content-Disposition':f'attachment; filename="osmanx-brief-{target.isoformat()}.csv"','Cache-Control':'no-store'})

    return router
