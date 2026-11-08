"""R0.9 Evidence Lab: demand radar, recovery cases, finance integrity,
pre-registered comparisons and immutable executive evidence packs.

No shopper profiling, guaranteed missed-sales claims, or automatic purchases.
All writes are isolated by organization and accessible store.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from backend.database import now_iso
from backend.r07 import held_quantity
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_playbooks_r09 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), demand_id INTEGER NOT NULL REFERENCES demand(id),
 request_id TEXT NOT NULL, payload_sha TEXT NOT NULL,
 sku TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('stock_check','supplier_order','fitting_fix','service_fix')),
 status TEXT NOT NULL CHECK(status IN ('planned','working','resolved','discarded')),
 outcome TEXT NOT NULL DEFAULT '', sale_id INTEGER REFERENCES sales(id),
 evidence TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id), UNIQUE(store_id,demand_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_r09_verified_sale ON recovery_playbooks_r09(sale_id) WHERE sale_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_r09_recoveries_store ON recovery_playbooks_r09(store_id,status,created_at);
CREATE TABLE IF NOT EXISTS experiment_protocols_r09 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), control_store_id INTEGER REFERENCES stores(id),
 request_id TEXT NOT NULL, payload_sha TEXT NOT NULL,
 title TEXT NOT NULL, hypothesis TEXT NOT NULL,
 metric TEXT NOT NULL CHECK(metric IN ('check_rate','receipt_per_entry')),
 source_mode TEXT NOT NULL CHECK(source_mode IN ('sensor','manual','all')),
 before_start TEXT NOT NULL, before_end TEXT NOT NULL,
 after_start TEXT NOT NULL, after_end TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('planned','evaluated')),
 evidence TEXT NOT NULL DEFAULT '', result_json TEXT, result_sha TEXT,
 created_at TEXT NOT NULL, evaluated_at TEXT,
 UNIQUE(organization_id,request_id)
);
CREATE TABLE IF NOT EXISTS executive_dossiers_r09 (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), request_id TEXT NOT NULL,
 params_sha TEXT NOT NULL, start_day TEXT NOT NULL, end_day TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_sha TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r09_dossiers_store ON executive_dossiers_r09(store_id,id);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def canonical(obj) -> str:
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(obj) -> str:
    return hashlib.sha256(canonical(obj).encode('utf-8')).hexdigest()


def norm(value: str) -> str:
    return ' '.join((value or '').casefold().strip().split())


def tz(store):
    try:return ZoneInfo(store['timezone'] or 'UTC')
    except (KeyError,ZoneInfoNotFoundError):return timezone.utc


def daterange(start:date,end:date,max_days:int=90):
    days=(end-start).days+1
    if days<1 or days>max_days:raise HTTPException(422,f'Выберите период от 1 до {max_days} дней')
    return days


def during(iso, start:date,end:date,timezone_value):
    try:
        timestamp=datetime.fromisoformat(iso)
        return timestamp.tzinfo is not None and start<=timestamp.astimezone(timezone_value).date()<=end
    except (TypeError,ValueError,OverflowError):return False


def demand_radar(db,store,days:int=14):
    if not 7<=days<=45:raise HTTPException(422,'Период от 7 до 45 дней')
    end=datetime.now(timezone.utc)
    first=end-timedelta(days=days)
    earlier=first-timedelta(days=days)
    # Bound query with UTC buffer to admit offsets, then compare actual timestamps.
    rows=db.execute('''SELECT d.*, c.sku AS case_sku FROM demand d
      LEFT JOIN demand_cases c ON c.demand_id=d.id WHERE d.store_id=? AND d.created_at>=?
      ORDER BY d.id DESC LIMIT 30001''',(store['id'],(earlier-timedelta(days=2)).isoformat(timespec='seconds'))).fetchall()
    if len(rows)>30000:raise HTTPException(413,'Слишком много запросов; сократите период')
    inv=db.execute('''SELECT i.* FROM inventory i JOIN stores s ON s.id=i.store_id
       WHERE s.organization_id=? LIMIT 20001''',(store['organization_id'],)).fetchall()
    if len(inv)>20000:raise HTTPException(413,'Слишком большой ассортимент')
    by_sku=defaultdict(list)
    for item in inv:by_sku[(norm(item['product']),norm(item['size']),norm(item['color']))].append(item)
    groups={};ambiguous=0
    for r in rows:
        try:created=datetime.fromisoformat(r['created_at'])
        except (TypeError,ValueError):continue
        if created.tzinfo is None:continue
        utc=created.astimezone(timezone.utc)
        if not earlier<=utc<=end:continue
        if r['status'] not in ('open','located','notified'):continue
        matches=by_sku.get((norm(r['product']),norm(r['size']),norm(r['color'])),[])
        skus={x['sku'] for x in matches}
        sku=r['case_sku'] or (next(iter(skus)) if len(skus)==1 else None)
        if not sku:ambiguous+=1
        key=(sku or '',norm(r['product']),norm(r['size']),norm(r['color']))
        group=groups.setdefault(key,{'sku':sku,'product':r['product'],'size':r['size'],'color':r['color'],
                  'current':0,'previous':0,'ids':[],'available_local':0,'available_network':0,'open_order_units':0})
        if utc>=first:group['current']+=1;group['ids'].append(r['id'])
        else:group['previous']+=1
    results=[]
    for group in groups.values():
        if group['sku']:
            for item in inv:
                if item['sku']!=group['sku']:continue
                available=max(0,item['quantity']-held_quantity(db,item))
                group['available_network']+=available
                if item['store_id']==store['id']:group['available_local']+=available
            group['open_order_units']=int(db.execute('''SELECT COALESCE(SUM(l.ordered_qty-l.received_qty),0)
              FROM purchase_order_lines l JOIN purchase_orders o ON o.id=l.order_id
              WHERE o.store_id=? AND l.sku=? AND o.status IN ('ordered','partial')''',
              (store['id'],group['sku'])).fetchone()[0])
        group['trend']=group['current']-group['previous']
        group['signal']=('sku_unresolved' if not group['sku'] else
                         'stock_available' if group['available_local'] else
                         'pipeline' if group['open_order_units'] else 'investigate')
        del group['ids']
        if group['current']:results.append(group)
    results.sort(key=lambda x:(-x['current'],x['available_local'],x['product']))
    return {'days':days,'items':results[:100],'current_requests':sum(x['current'] for x in results),
            'ambiguous_sku_records':ambiguous,'warnings':[
                'Запрос — выраженный интерес, но не доказанная потерянная продажа.',
                'Статусы без покупки учитываются отдельно от подтверждённых чеков.',
                'Сопоставление артикула выполняется только при однозначном совпадении.'
            ],'method':'Two consecutive UTC windows of equal duration; open/located/notified requests only.'}


def get_scoped(db,table:str,object_id:int,principal:Principal):
    if table not in ('recovery_playbooks_r09','experiment_protocols_r09','executive_dossiers_r09'):
        raise ValueError('Invalid table')
    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND organization_id=?',(object_id,principal.organization_id)).fetchone()
    if not row:raise HTTPException(404,'Запись не найдена')
    check_store_access(db,row['store_id'],principal)
    return row


def sku_for_demand(db,store_id:int,demand_id:int):
    d=db.execute('SELECT * FROM demand WHERE id=? AND store_id=?',(demand_id,store_id)).fetchone()
    if not d:raise HTTPException(404,'Запрос не найден')
    case=db.execute('SELECT sku FROM demand_cases WHERE demand_id=? AND store_id=?',(demand_id,store_id)).fetchone()
    if case:return d,case['sku']
    inv=db.execute('''SELECT i.sku,i.product,i.size,i.color FROM inventory i JOIN stores s ON s.id=i.store_id
      WHERE s.organization_id=(SELECT organization_id FROM stores WHERE id=?) LIMIT 20001''',(store_id,)).fetchall()
    if len(inv)>20000:raise HTTPException(413,'Ассортимент слишком большой')
    unique={r['sku'] for r in inv if (norm(r['product']),norm(r['size']),norm(r['color']))==
            (norm(d['product']),norm(d['size']),norm(d['color']))}
    if len(unique)!=1:raise HTTPException(422,'Артикул не определяется однозначно. Уточните его через существующий кейс спроса.')
    return d,next(iter(unique))


def margin_integrity(db,store,start:date,end:date):
    daterange(start,end,90)
    timezone_value=tz(store)
    sales=db.execute('SELECT * FROM sales WHERE store_id=? ORDER BY id DESC LIMIT 100001',(store['id'],)).fetchall()
    if len(sales)>100000:raise HTTPException(413,'Для точного расчёта выберите меньший магазин/период')
    relevant=[r for r in sales if during(r['occurred_at'],start,end,timezone_value)]
    gross=sum(r['amount_kopeks'] for r in relevant)
    covered=0;matched=0;contribution=0;zero_cost=0;difference=0
    for s in relevant:
        items=db.execute('SELECT * FROM sale_items WHERE store_id=? AND sale_id=?',(store['id'],s['id'])).fetchall()
        if not items:continue
        covered+=1
        total=sum(i['quantity']*i['unit_revenue_kopeks'] for i in items)
        if total!=s['amount_kopeks']:
            difference+=1;continue
        if any(i['unit_cost_kopeks']==0 for i in items):
            zero_cost+=1;continue
        matched+=1
        contribution+=sum(i['quantity']*(i['unit_revenue_kopeks']-i['unit_cost_kopeks']) for i in items)
    returns_table=('merchandise_returns' if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchandise_returns'").fetchone() else 'returns_log')
    returned=db.execute(f'SELECT amount_kopeks,created_at FROM {returns_table} WHERE store_id=? ORDER BY id DESC LIMIT 100001',(store['id'],)).fetchall()
    if len(returned)>100000:raise HTTPException(413,'Слишком много записей о возвратах')
    return_amount=sum(r['amount_kopeks'] for r in returned if during(r['created_at'],start,end,timezone_value))
    complete=bool(relevant) and matched==len(relevant)
    warnings=[]
    if not relevant:warnings.append('За период нет зарегистрированных чеков.')
    if covered<len(relevant):warnings.append('Не все чеки содержат товарные строки: себестоимость неполная.')
    if difference:warnings.append(f'В {difference} чеках сумма товарных строк не совпадает с суммой чека.')
    if zero_cost:warnings.append(f'В {zero_cost} чеках себестоимость равна нулю и требует проверки.')
    if return_amount:warnings.append('Возвраты зарегистрированы, но факт банковского возврата и восстановление себестоимости не подтверждены.')
    if any('demo' in str(s['source']).lower() for s in relevant):warnings.append('Есть демо-чеки — не использовать как фактическую прибыль.')
    return {'period':{'start':start.isoformat(),'end':end.isoformat()},'receipts':len(relevant),
            'gross_receipts_kopeks':gross,'receipts_with_lines':covered,'reconciled_receipts':matched,
            'unmatched_receipts':len(relevant)-matched,'amount_mismatches':difference,
            'zero_cost_receipts':zero_cost,'documented_returns_kopeks':return_amount,
            'gross_contribution_kopeks':contribution if complete else None,
            'reconciled_contribution_kopeks':contribution,
            'cost_coverage_percent':round(matched/len(relevant)*100,1) if relevant else None,
            'warnings':warnings,'method':'Recorded receipts; cost margin shown only if all receipts reconcile. Return logs are not verified refunds.'}


def metric_window(db,store,start:date,end:date,source_mode:str,metric:str):
    timezone_value=tz(store)
    cutoff=(start-timedelta(days=2)).isoformat()
    vs=db.execute('SELECT quantity,source,occurred_at FROM visits WHERE store_id=? AND occurred_at>=? LIMIT 100001',(store['id'],cutoff)).fetchall()
    ss=db.execute('SELECT amount_kopeks,source,occurred_at FROM sales WHERE store_id=? AND occurred_at>=? LIMIT 100001',(store['id'],cutoff)).fetchall()
    if len(vs)>100000 or len(ss)>100000:raise HTTPException(413,'Объём событий слишком велик')
    accepted={'sensor':{'signed_sensor','sensor','demo_sensor'},'manual':{'manual'}}
    visits=[v for v in vs if during(v['occurred_at'],start,end,timezone_value) and
            (source_mode=='all' or v['source'] in accepted[source_mode])]
    sales=[s for s in ss if during(s['occurred_at'],start,end,timezone_value)]
    n=sum(v['quantity'] for v in visits)
    amount=sum(s['amount_kopeks'] for s in sales)
    checks=len(sales)
    metric_value=(checks/n*100 if metric=='check_rate' else amount/n/100) if n else None
    return {'entries':n,'receipts':checks,'amount_kopeks':amount,
            'value':round(metric_value,4) if metric_value is not None else None,
            'sources':sorted({v['source'] for v in visits}),
            'demo':any('demo' in v['source'] for v in visits) or any('demo' in s['source'] for s in sales)}


def evaluate_protocol(db,row):
    store=db.execute('SELECT * FROM stores WHERE id=?',(row['store_id'],)).fetchone()
    before=(date.fromisoformat(row['before_start']),date.fromisoformat(row['before_end']))
    after=(date.fromisoformat(row['after_start']),date.fromisoformat(row['after_end']))
    b=metric_window(db,store,*before,row['source_mode'],row['metric'])
    a=metric_window(db,store,*after,row['source_mode'],row['metric'])
    warn=[]
    if min(b['entries'],a['entries'])<100:warn.append('Менее 100 входов в одном из периодов: малый объём наблюдений.')
    if not b['sources'] or not a['sources']:warn.append('Источник посещений отсутствует в одном из периодов.')
    if b['sources']!=a['sources']:warn.append('Источники посещений различаются между периодами.')
    if b['demo'] or a['demo']:warn.append('Демонстрационные данные не подтверждают коммерческий эффект.')
    if row['source_mode']=='all' and (len(b['sources'])>1 or len(a['sources'])>1):warn.append('Возможен двойной подсчёт при смешивании источников.')
    delta=round(a['value']-b['value'],4) if b['value'] is not None and a['value'] is not None else None
    reference=None;difference_in_differences=None
    if row['control_store_id']:
        other=db.execute('SELECT * FROM stores WHERE id=?',(row['control_store_id'],)).fetchone()
        cb=metric_window(db,other,*before,row['source_mode'],row['metric'])
        ca=metric_window(db,other,*after,row['source_mode'],row['metric'])
        cdelta=round(ca['value']-cb['value'],4) if cb['value'] is not None and ca['value'] is not None else None
        if min(cb['entries'],ca['entries'])<100:warn.append('Контрольный филиал: меньше 100 входов в одном из периодов.')
        if cb['sources']!=ca['sources']:warn.append('Контрольный филиал: источники посещений различаются.')
        if cb['demo'] or ca['demo']:warn.append('Контрольный филиал содержит демонстрационные данные.')
        reference={'before':cb,'after':ca,'delta':cdelta}
        if delta is not None and cdelta is not None:difference_in_differences=round(delta-cdelta,4)
    return {'before':b,'after':a,'delta':delta,'reference':reference,
            'difference_in_differences':difference_in_differences,
            'warnings':warn,'verdict':'insufficient_evidence' if warn or delta is None else 'descriptive_change',
            'disclaimer':'Изменение показателя не доказывает причинно-следственную связь. Данные не являются прогнозом прибыли.'}


class RecoveryNew(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=120)
    demand_id:int=Field(gt=0)
    action:Literal['stock_check','supplier_order','fitting_fix','service_fix']

class RecoveryUpdate(BaseModel):
    status:Literal['working','resolved','discarded']
    outcome:Literal['confirmed_sale','operational_fix','none']='none'
    sale_id:int|None=Field(default=None,gt=0)
    evidence:str=Field(default='',max_length=1200)

class ProtocolNew(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=120)
    title:str=Field(min_length=5,max_length=150)
    hypothesis:str=Field(min_length=12,max_length=700)
    metric:Literal['check_rate','receipt_per_entry']
    source_mode:Literal['sensor','manual','all']='sensor'
    before_start:date;before_end:date;after_start:date;after_end:date
    control_slug:str|None=Field(default=None,max_length=80)

    @model_validator(mode='after')
    def dates(self):
        left=daterange(self.before_start,self.before_end,60)
        right=daterange(self.after_start,self.after_end,60)
        if left!=right or self.before_end>=self.after_start or (self.after_end-self.before_start).days>180:
            raise ValueError('Выберите равные непересекающиеся периоды общей длительностью до 180 дней')
        return self

class FinishProtocol(BaseModel):
    evidence:str=Field(min_length=20,max_length=1500)

class DossierNew(BaseModel):
    slug:str=Field(default='central',min_length=1,max_length=80)
    request_id:str=Field(min_length=8,max_length=120)
    start:date;end:date

    @model_validator(mode='after')
    def dates(self):daterange(self.start,self.end,30);return self


def build_router(admin_dep,db_dep):
    router=APIRouter(prefix='/api/admin/r09',tags=['R0.9: Evidence Lab'])

    @router.get('/radar')
    def radar(slug:str='central',days:int=14,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return demand_radar(db,visible_store(db,slug,principal),days)

    @router.get('/recoveries')
    def recoveries(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        s=visible_store(db,slug,principal)
        rows=db.execute('''SELECT r.*,d.product,d.size,d.color FROM recovery_playbooks_r09 r
          JOIN demand d ON d.id=r.demand_id WHERE r.store_id=? ORDER BY r.id DESC LIMIT 200''',(s['id'],)).fetchall()
        candidates=db.execute('''SELECT d.id,d.product,d.size,d.color FROM demand d
          LEFT JOIN recovery_playbooks_r09 r ON r.demand_id=d.id
          WHERE d.store_id=? AND r.id IS NULL AND d.status IN ('open','located','notified') ORDER BY d.id DESC LIMIT 100''',(s['id'],)).fetchall()
        return {'items':[dict(x) for x in rows],'candidates':[dict(x) for x in candidates]}

    @router.post('/recoveries',status_code=201)
    def new_recovery(value:RecoveryNew,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        s=visible_store(db,value.slug,principal)
        fingerprint=sha({'store':s['id'],'demand':value.demand_id,'action':value.action})
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT * FROM recovery_playbooks_r09 WHERE organization_id=? AND request_id=?',(principal.organization_id,value.request_id)).fetchone()
            if old:
                if old['payload_sha']!=fingerprint:raise HTTPException(409,'Повторный ключ с другим содержимым')
                db.commit();return {'id':old['id'],'duplicate':True,'status':old['status']}
            d,sku=sku_for_demand(db,s['id'],value.demand_id)
            if d['status'] in ('converted','closed'):raise HTTPException(409,'Запрос уже закрыт')
            when=now_iso()
            row=db.execute('''INSERT INTO recovery_playbooks_r09(organization_id,store_id,demand_id,request_id,payload_sha,sku,action,status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',(principal.organization_id,s['id'],value.demand_id,value.request_id,fingerprint,sku,value.action,'planned',when,when))
            audit(db,principal,'r09.recovery.create',str(row.lastrowid));db.commit()
            return {'id':row.lastrowid,'duplicate':False,'status':'planned','sku':sku}
        except sqlite3.IntegrityError as exc:
            db.rollback();raise HTTPException(409,'Для этого запроса уже есть план восстановления') from exc
        except Exception:db.rollback();raise

    @router.patch('/recoveries/{recovery_id}')
    def update_recovery(recovery_id:int,value:RecoveryUpdate,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        try:
            row=get_scoped(db,'recovery_playbooks_r09',recovery_id,principal)
            if row['status'] in ('resolved','discarded'):raise HTTPException(409,'Завершённый план не изменяется')
            if value.status=='resolved':
                if len(value.evidence.strip())<15 or value.outcome=='none':raise HTTPException(422,'Укажите фактическое действие и проверяемое подтверждение')
                if value.outcome=='confirmed_sale':
                    if not value.sale_id:raise HTTPException(422,'Требуется номер подтверждённого чека')
                    receipt=db.execute('SELECT id FROM sales WHERE id=? AND store_id=?',(value.sale_id,row['store_id'])).fetchone()
                    item=db.execute('SELECT id FROM sale_items WHERE sale_id=? AND store_id=? AND sku=? AND quantity>0',
                                    (value.sale_id,row['store_id'],row['sku'])).fetchone()
                    if not receipt or not item:raise HTTPException(422,'Нет товарной строки с нужным SKU в чеке этого магазина')
                    linked=db.execute('SELECT id FROM recovery_playbooks_r09 WHERE sale_id=? AND id<>?',(value.sale_id,recovery_id)).fetchone()
                    if linked:raise HTTPException(409,'Этот чек уже подтверждает другой кейс')
                elif value.sale_id:raise HTTPException(422,'Для операционного исправления чек не указывается')
            elif value.outcome!='none' or value.sale_id:raise HTTPException(422,'Исход можно фиксировать только при завершении')
            db.execute('''UPDATE recovery_playbooks_r09 SET status=?,outcome=?,sale_id=?,evidence=?,updated_at=? WHERE id=?''',
               (value.status,value.outcome,value.sale_id,value.evidence.strip(),now_iso(),recovery_id))
            if value.status=='resolved' and value.outcome=='confirmed_sale':
                demand=db.execute('SELECT status FROM demand WHERE id=?',(row['demand_id'],)).fetchone()
                db.execute("UPDATE demand SET status='converted',sale_id=?,updated_at=? WHERE id=?",
                           (value.sale_id,now_iso(),row['demand_id']))
                db.execute('''INSERT INTO demand_history(demand_id,previous_status,next_status,note,occurred_at)
                  VALUES(?,?,?,?,?)''',(row['demand_id'],demand['status'],'converted','Подтверждён товарной строкой чека; кейс R09 '+str(recovery_id),now_iso()))
            audit(db,principal,'r09.recovery.update',str(recovery_id));db.commit()
            return {'id':recovery_id,'status':value.status,'outcome':value.outcome}
        except sqlite3.IntegrityError as exc:
            db.rollback();raise HTTPException(409,'Конфликт связывания чека или запроса') from exc
        except Exception:db.rollback();raise

    @router.get('/finance')
    def finance(slug:str='central',start:date|None=None,end:date|None=None,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        s=visible_store(db,slug,principal)
        e=end or datetime.now(timezone.utc).astimezone(tz(s)).date()
        b=start or e-timedelta(days=6)
        return margin_integrity(db,s,b,e)

    @router.get('/protocols')
    def protocols(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        s=visible_store(db,slug,principal)
        records=[]
        for r in db.execute('SELECT * FROM experiment_protocols_r09 WHERE store_id=? ORDER BY id DESC LIMIT 100',(s['id'],)):
            obj=dict(r);obj['result']=json.loads(obj.pop('result_json')) if obj['result_json'] else None
            records.append(obj)
        return {'items':records}

    @router.post('/protocols',status_code=201)
    def create_protocol(value:ProtocolNew,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        s=visible_store(db,value.slug,principal)
        control=visible_store(db,value.control_slug,principal) if value.control_slug else None
        if control and control['id']==s['id']:raise HTTPException(422,'Контрольный филиал должен отличаться')
        fingerprint=sha({'store':s['id'],'control':control['id'] if control else None,
                          'title':value.title,'hypothesis':value.hypothesis,'metric':value.metric,'source':value.source_mode,
                          'before':[str(value.before_start),str(value.before_end)],'after':[str(value.after_start),str(value.after_end)]})
        db.execute('BEGIN IMMEDIATE')
        try:
            old=db.execute('SELECT * FROM experiment_protocols_r09 WHERE organization_id=? AND request_id=?',(principal.organization_id,value.request_id)).fetchone()
            if old:
                if old['payload_sha']!=fingerprint:raise HTTPException(409,'Ключ эксперимента уже используется')
                db.commit();return {'id':old['id'],'duplicate':True,'status':old['status']}
            iid=db.execute('''INSERT INTO experiment_protocols_r09(organization_id,store_id,control_store_id,request_id,payload_sha,
              title,hypothesis,metric,source_mode,before_start,before_end,after_start,after_end,status,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,s['id'],control['id'] if control else None,value.request_id,fingerprint,
               value.title.strip(),value.hypothesis.strip(),value.metric,value.source_mode,str(value.before_start),str(value.before_end),
               str(value.after_start),str(value.after_end),'planned',now_iso())).lastrowid
            audit(db,principal,'r09.protocol.create',str(iid));db.commit()
            return {'id':iid,'duplicate':False,'status':'planned'}
        except Exception:db.rollback();raise

    @router.get('/protocols/{protocol_id}/preview')
    def protocol_preview(protocol_id:int,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        item=get_scoped(db,'experiment_protocols_r09',protocol_id,principal)
        if item['control_store_id']:check_store_access(db,item['control_store_id'],principal)
        return evaluate_protocol(db,item)

    @router.post('/protocols/{protocol_id}/evaluate')
    def finalize_protocol(protocol_id:int,value:FinishProtocol,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        db.execute('BEGIN IMMEDIATE')
        try:
            item=get_scoped(db,'experiment_protocols_r09',protocol_id,principal)
            if item['status']=='evaluated':raise HTTPException(409,'Результат уже зафиксирован и неизменяем')
            if item['control_store_id']:check_store_access(db,item['control_store_id'],principal)
            result=evaluate_protocol(db,item)
            snapshot={'result':result,'evidence':value.evidence.strip(),'protocol_id':protocol_id,'captured_at':now_iso()}
            db.execute('''UPDATE experiment_protocols_r09 SET status='evaluated',evidence=?,result_json=?,result_sha=?,evaluated_at=? WHERE id=?''',
                  (value.evidence.strip(),canonical(snapshot),sha(snapshot),now_iso(),protocol_id))
            audit(db,principal,'r09.protocol.evaluate',str(protocol_id));db.commit()
            return {'id':protocol_id,'status':'evaluated','result':result,'sha256':sha(snapshot)}
        except Exception:db.rollback();raise

    @router.get('/dossiers')
    def dossiers(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        s=visible_store(db,slug,principal)
        return {'items':[{'id':r['id'],'start':r['start_day'],'end':r['end_day'],'sha256':r['payload_sha'],'created_at':r['created_at']}
                 for r in db.execute('SELECT * FROM executive_dossiers_r09 WHERE store_id=? ORDER BY id DESC LIMIT 100',(s['id'],))]}

    @router.post('/dossiers',status_code=201)
    def new_dossier(value:DossierNew,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        s=visible_store(db,value.slug,principal)
        fingerprint=sha([s['id'],str(value.start),str(value.end)])
        db.execute('BEGIN IMMEDIATE')
        try:
            previous=db.execute('SELECT * FROM executive_dossiers_r09 WHERE organization_id=? AND request_id=?',(principal.organization_id,value.request_id)).fetchone()
            if previous:
                if fingerprint!=previous['params_sha']:raise HTTPException(409,'Повторный ключ с другим отчётным периодом')
                db.commit();return {'id':previous['id'],'duplicate':True,'sha256':previous['payload_sha']}
            financial=margin_integrity(db,s,value.start,value.end)
            radar=demand_radar(db,s,14)
            recovered=db.execute('''SELECT status,outcome,COUNT(*) n FROM recovery_playbooks_r09 WHERE store_id=? GROUP BY status,outcome''',(s['id'],)).fetchall()
            protocols=db.execute('''SELECT id,title,status,result_sha FROM experiment_protocols_r09 WHERE store_id=? ORDER BY id DESC LIMIT 20''',(s['id'],)).fetchall()
            payload={'version':'R0.9','store':s['slug'],'period':[str(value.start),str(value.end)],
                     'captured_at':now_iso(),'financial_integrity':financial,
                     'radar_window_days':14,'radar':{'items':radar['items'][:20],'current_requests':radar['current_requests'],
                                                   'ambiguous_sku_records':radar['ambiguous_sku_records']},
                     'recoveries':[dict(r) for r in recovered],'protocols':[dict(r) for r in protocols],
                     'limitations':['Радар оценивает последние 14 дней, независимо от периода финансового отчёта.',
                                    'Без полной себестоимости нет подтверждённой валовой прибыли.',
                                    'Опросы и сравнения до/после не устанавливают причинно-следственную связь.']}
            content=canonical(payload)
            iid=db.execute('''INSERT INTO executive_dossiers_r09(organization_id,store_id,request_id,params_sha,start_day,end_day,payload_json,payload_sha,created_at)
              VALUES(?,?,?,?,?,?,?,?,?)''',(principal.organization_id,s['id'],value.request_id,fingerprint,str(value.start),str(value.end),content,sha(payload),now_iso())).lastrowid
            audit(db,principal,'r09.dossier.create',str(iid));db.commit()
            return {'id':iid,'duplicate':False,'sha256':sha(payload),'warnings':financial['warnings']}
        except Exception:db.rollback();raise

    @router.get('/dossiers/{dossier_id}')
    def dossier(dossier_id:int,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        row=get_scoped(db,'executive_dossiers_r09',dossier_id,principal)
        return {'id':row['id'],'payload':json.loads(row['payload_json']),'sha256':row['payload_sha']}

    @router.get('/dossiers/{dossier_id}/export.csv')
    def dossier_csv(dossier_id:int,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        row=get_scoped(db,'executive_dossiers_r09',dossier_id,principal)
        pack=json.loads(row['payload_json'])
        out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['Metric','Value','Evidence/limitations'])
        f=pack['financial_integrity']
        rows=[('store',pack['store'],''),('period',' / '.join(pack['period']),''),
              ('receipts',f['receipts'],''),('gross_receipts_rub',Decimal(f['gross_receipts_kopeks'])/100,'Registered receipts only'),
              ('margin_coverage_pct',f['cost_coverage_percent'],'Unreconciled amounts excluded'),
              ('gross_contribution_rub',Decimal(f['gross_contribution_kopeks'])/100 if f['gross_contribution_kopeks'] is not None else 'unavailable','Only if 100% reconciled'),
              ('open_demand_radar',pack['radar']['current_requests'],'Interest not guaranteed sales'),
              ('sha256',row['payload_sha'],'Immutable snapshot')]
        for entry in rows:writer.writerow([safe_spreadsheet_cell(str(value)) for value in entry])
        for warning in f['warnings']:writer.writerow(['warning','',safe_spreadsheet_cell(warning)])
        return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={
          'Content-Disposition':f'attachment; filename="osmanx-evidence-{dossier_id}.csv"','Cache-Control':'no-store'})

    return router
