"""OSMANX Retail Intelligence R1.3 — Merchant Control Room.

Five integrated business workflows: CSV adapter, source quality, size-demand matrix,
stock inactivity diagnostics, evidence-bound owner actions. No connection to 1C is
claimed; an operator explicitly previews and confirms CSV import into the existing
atomic import service. Never infer missed revenue from an unanswered request.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.imports import apply_import, preview_import
from backend.r07 import held_quantity
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, check_store_access, require_role, visible_store

DDL = """
CREATE TABLE IF NOT EXISTS control_actions_r13 (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 request_id TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('quality','demand','stock')),
 signal_key TEXT NOT NULL,
 title TEXT NOT NULL,
 evidence_json TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','testing','resolved','dismissed')),
 result_note TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(organization_id,request_id)
);
CREATE INDEX IF NOT EXISTS ix_r13_actions_store ON control_actions_r13(store_id,updated_at);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def digest(data) -> str:
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def normalize(value) -> str:
    return ' '.join(str(value or '').casefold().strip().split())


def column_key(value):
    value=unicodedata.normalize('NFKC',str(value or '')).casefold().replace('\ufeff','')
    return re.sub(r'[^\w]+','',value)


CSV_ALIASES = {
 'inventory': {
  'sku': ('артикул','кодтовара','код','sku','vendorcode','номенклатуракод'),
  'product': ('наименование','номенклатура','товар','product','названиетовара'),
  'size': ('размер','size'),
  'color': ('цвет','color'),
  'quantity': ('остаток','остатокшт','количество','количествоостаток','quantity','stock'),
 },
 'pos': {
  'external_id': ('номерчека','чек','idчека','externalid','receiptid','номердокумента','номер'),
  'amount_rub': ('сумма','суммаруб','суммачека','amount','amountrub','итого'),
  'occurred_at': ('датавремя','датаивремя','датачека','датапродажи','дата','datetime','occurredat'),
 }
}


def _decimal_string(raw: str) -> str:
    s=str(raw).strip().replace('\u00a0','').replace('\u202f','').replace(' ','').replace('\u2009','')
    if not s or not re.fullmatch(r'\d+(?:[.,]\d{1,2})?',s):
        raise ValueError('неверная сумма, укажите рубли с двумя знаками после запятой')
    val=Decimal(s.replace(',','.'))
    if not val.is_finite() or not 0 <= val <= 20_000_000:raise ValueError('недопустимая сумма')
    return str(val)


def _local_time(raw: str, store) -> str:
    s=str(raw).strip()
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
    except ValueError:
        dt=None
    if dt is None:
        for fmt in ('%d.%m.%Y %H:%M:%S','%d.%m.%Y %H:%M'):
            try:dt=datetime.strptime(s,fmt);break
            except ValueError:pass
    if dt is None:raise ValueError('неверная дата чека, укажите дату и время')
    if dt.tzinfo is None:
        try:local_tz=ZoneInfo(store['timezone'] or 'Europe/Moscow')
        except (ZoneInfoNotFoundError,KeyError):raise ValueError('часовой пояс магазина не настроен') from None
        # Round-trip detects nonexistent wall clock times in DST transitions.
        local=dt.replace(tzinfo=local_tz)
        if local.astimezone(timezone.utc).astimezone(local_tz).replace(tzinfo=None)!=dt:
            raise ValueError('такого локального времени не существует в выбранном часовом поясе')
        dt=local
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def parse_merchant_csv(csv_text: str, kind: str, store) -> dict:
    """Convert an operator-supplied 1C-like export into existing import staging rows."""
    if kind not in CSV_ALIASES:raise HTTPException(422,'Неверный тип CSV')
    if not csv_text or len(csv_text.encode('utf-8'))>300_000:
        raise HTTPException(413,'CSV должен быть не больше 300 КБ')
    text=csv_text.lstrip('\ufeff')
    first=text.splitlines()[0] if text.splitlines() else ''
    delimiter=';' if first.count(';')>=first.count(',') else ','
    try:matrix=csv.reader(io.StringIO(text,newline=''),delimiter=delimiter,strict=True)
    except csv.Error:raise HTTPException(422,'CSV не распознан') from None
    try:header=next(matrix)
    except StopIteration:raise HTTPException(422,'Файл пуст') from None
    if len(header)>45 or len(header)<2:raise HTTPException(422,'Ожидалось от 2 до 45 столбцов')
    keys=[column_key(col) for col in header]
    if len(keys)!=len(set(keys)):raise HTTPException(422,'Заголовки столбцов повторяются')
    mapping={}
    for field,aliases in CSV_ALIASES[kind].items():
        candidates=[i for i,k in enumerate(keys) if k in aliases]
        if len(candidates)>1:raise HTTPException(422,f'Неоднозначный столбец {field}')
        if candidates:mapping[field]=candidates[0]
    required={'inventory':('sku','product','quantity'),'pos':('external_id','amount_rub','occurred_at')}[kind]
    missing=[field for field in required if field not in mapping]
    if missing:raise HTTPException(422,'Не хватает столбцов: '+', '.join(missing))
    rows=[]; errors=[]
    try:
        for line_no,row in enumerate(matrix,2):
            if not any(x.strip() for x in row):continue
            if len(rows)>=2000:raise HTTPException(413,'Не больше 2000 строк на пакет')
            if len(row)!=len(header):
                errors.append({'line':line_no,'error':'Число колонок не совпадает с заголовком'});continue
            raw={field:row[index].strip() for field,index in mapping.items()}
            try:
                if kind=='inventory':
                    count=raw['quantity']
                    if not re.fullmatch(r'\d+',count):raise ValueError('остаток должен быть целым неотрицательным числом')
                    item={'sku':raw['sku'],'product':raw['product'],'size':raw.get('size',''),
                          'color':raw.get('color',''),'quantity':int(count)}
                else:
                    item={'external_id':raw['external_id'], 'amount_rub':_decimal_string(raw['amount_rub']),
                          'occurred_at':_local_time(raw['occurred_at'],store)}
                rows.append(item)
            except (ValueError,InvalidOperation) as exc:
                errors.append({'line':line_no,'error':str(exc)[:150]})
    except csv.Error:raise HTTPException(422,'В CSV есть некорректные кавычки') from None
    if errors:raise HTTPException(422,{'message':'CSV содержит ошибки','errors':errors[:15],'total_errors':len(errors)})
    if not rows:raise HTTPException(422,'CSV не содержит строк данных')
    # Stage validator (_normalize) will validate duplicate SKUs/receipt IDs.
    return {'rows':rows,'columns':{field:header[index] for field,index in mapping.items()},'count':len(rows),
            'note':'Локальные даты без пояса интерпретированы во времени магазина. Ничего ещё не записано в продажи или остатки.'}


def source_quality(db,store,days:int=14) -> dict:
    if not 7<=days<=90:raise HTTPException(422,'Выберите 7–90 дней')
    start=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    store_id=store['id']
    traffic=[dict(x) for x in db.execute('SELECT source,COUNT(*) AS events, SUM(quantity) AS visits,MAX(occurred_at) AS last_event FROM visits WHERE store_id=? AND occurred_at>=? GROUP BY source',(store_id,start))]
    receipts=[dict(x) for x in db.execute('SELECT source,COUNT(*) AS receipts,SUM(amount_kopeks) AS amount_kopeks,MAX(occurred_at) AS last_event FROM sales WHERE store_id=? AND occurred_at>=? GROUP BY source',(store_id,start))]
    sale_rows=db.execute('SELECT id,amount_kopeks FROM sales WHERE store_id=? AND occurred_at>=? ORDER BY id DESC LIMIT 20001',(store_id,start)).fetchall()
    if len(sale_rows)>20000:raise HTTPException(413,'Слишком много чеков для экспресс-сверки')
    id_list=[x['id'] for x in sale_rows]
    sums={}
    # SQL aggregate filters by store and period; no N+1 queries.
    for r in db.execute('''SELECT s.id, COUNT(i.id) lines, COALESCE(SUM(i.quantity*i.unit_revenue_kopeks),0) total,
          COALESCE(SUM(CASE WHEN i.unit_cost_kopeks<=0 THEN 1 ELSE 0 END),0) zero_cost
      FROM sales s LEFT JOIN sale_items i ON i.sale_id=s.id AND i.store_id=s.store_id
      WHERE s.store_id=? AND s.occurred_at>=? GROUP BY s.id''',(store_id,start)):
        sums[r['id']]=r
    missing=unequal=zero_cost=covered=0
    for s in sale_rows:
        stats=sums[s['id']]
        if stats['lines']==0:missing+=1;continue
        covered+=1
        if stats['total']!=s['amount_kopeks']:unequal+=1
        if stats['zero_cost']:zero_cost+=1
    import_rows=[dict(x) for x in db.execute('''SELECT kind,status,COUNT(*) as total FROM import_batches
            WHERE store_id=? AND created_at>=? GROUP BY kind,status''',(store_id,start))]
    flags=[]
    def warn(code,level,message):flags.append({'key':code,'severity':level,'title':message})
    if not traffic:warn('no_traffic','warning','Нет посещений за выбранный период')
    if not receipts:warn('no_receipts','warning','Нет чеков за выбранный период')
    if len(traffic)>1 and store['traffic_mode']=='combined':warn('mixed_sources','warning','Несколько источников посещений могут давать двойной учёт')
    if missing:warn('no_item_rows','warning',f'Чеки без товарных строк: {missing}')
    if unequal:warn('item_mismatch','critical',f'Не совпадают суммы товарных строк и чеков: {unequal}')
    if zero_cost:warn('missing_cost','warning',f'Отсутствует себестоимость хотя бы одной позиции: {zero_cost} чеков')
    if not flags:warn('review_data','info','Критичных признаков ошибок не найдено; это не аудит всех данных')
    return {'days':days,'traffic_sources':traffic,'receipt_sources':receipts,'import_batches':import_rows,
            'receipt_coverage':{'total':len(sale_rows),'with_items':covered,'missing_items':missing,'mismatched':unequal,'zero_cost':zero_cost},
            'flags':flags,'warnings':['Не складывайте конкурирующие счётчики в единый показатель без проверки источников.',
                                    'Отсутствие ошибки в текущем отчёте не подтверждает достоверность всех внешних данных.']}


def demand_matrix(db,store,days:int=30) -> dict:
    if not 7<=days<=90:raise HTTPException(422,'Выберите 7–90 дней')
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    org=store['organization_id']; sid=store['id']
    inv=db.execute('''SELECT i.* FROM inventory i JOIN stores s ON s.id=i.store_id
      WHERE s.organization_id=? LIMIT 20001''',(org,)).fetchall()
    if len(inv)>20000:raise HTTPException(413,'Слишком большой каталог')
    stock_by_key=defaultdict(list)
    for item in inv:stock_by_key[(normalize(item['product']),normalize(item['size']),normalize(item['color']))].append(item)
    demands=db.execute('''SELECT d.*,c.sku AS explicit_sku FROM demand d LEFT JOIN demand_cases c ON c.demand_id=d.id
       WHERE d.store_id=? AND d.created_at>=? AND d.status IN ('open','located','notified') ORDER BY d.id DESC LIMIT 10001''',(sid,since)).fetchall()
    if len(demands)>10000:raise HTTPException(413,'Слишком много запросов')
    groups={}
    for d in demands:
        key=(normalize(d['product']),normalize(d['size']),normalize(d['color']))
        group=groups.setdefault(key,{'product':d['product'],'size':d['size'],'color':d['color'],
                                      'requests':0,'sku':None,'ambiguous':False,'possible_skus':set()})
        group['requests']+=1
        linked=stock_by_key.get(key,[])
        skus={s['sku'] for s in linked}
        if d['explicit_sku']:skus.add(d['explicit_sku'])
        group['possible_skus'].update(skus)
        group['ambiguous']=len(group['possible_skus'])>1
        group['sku']=next(iter(group['possible_skus'])) if len(group['possible_skus'])==1 else None
    results=[]
    for key,item in groups.items():
        del item['possible_skus']
        local=network=0;matched=[]
        if item['sku']:
            matched=[x for x in stock_by_key.get(key,[]) if x['sku']==item['sku']]
            for row in matched:
                qty=max(0,int(row['quantity'])-held_quantity(db,row))
                network+=qty
                if row['store_id']==sid:local+=qty
        item['available_local']=local;item['available_network']=network
        item['unresolved_sku']=item['sku'] is None
        item['signal']='verify_sku' if not item['sku'] else 'available' if local else 'transfer' if network else 'investigate_supply'
        item['key']=digest({'store':sid,'kind':'demand','product':key[0],'size':key[1],'color':key[2]})[:20]
        results.append(item)
    results.sort(key=lambda x:(-x['requests'],x['product'],x['size']))
    return {'days':days,'items':results[:100],'request_count':len(demands),'warnings':[
        'Зафиксированный спрос не равен гарантированной продаже.',
        'При неоднозначных артикулах автоматические рекомендации о закупке блокируются.']}


def stock_health(db,store,days:int=30) -> dict:
    if days not in (30,60,90):raise HTTPException(422,'Допустимые окна: 30, 60, 90 дней')
    sid=store['id'];since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    inventory=db.execute('SELECT * FROM inventory WHERE store_id=? ORDER BY id LIMIT 10001',(sid,)).fetchall()
    if len(inventory)>10000:raise HTTPException(413,'Слишком большой каталог')
    sold={r['sku']:(r['units'] or 0) for r in db.execute('''SELECT i.sku,SUM(i.quantity) units FROM sale_items i
       JOIN sales s ON s.id=i.sale_id WHERE i.store_id=? AND s.store_id=? AND s.occurred_at>=?
       GROUP BY i.sku''',(sid,sid,since))}
    costs={}
    # Costs are derived only from recorded positive unit costs, never assumed.
    for r in db.execute('''SELECT i.sku,i.unit_cost_kopeks,i.recorded_at FROM sale_items i
       WHERE i.store_id=? AND i.unit_cost_kopeks>0 ORDER BY i.recorded_at DESC,i.id DESC''',(sid,)):
        costs.setdefault(r['sku'],int(r['unit_cost_kopeks']))
    demand=defaultdict(int)
    rows=db.execute("SELECT product,size,color FROM demand WHERE store_id=? AND created_at>=? AND status IN ('open','located','notified') LIMIT 20001",(sid,since)).fetchall()
    if len(rows)>20000:raise HTTPException(413,'Слишком много запросов')
    for request in rows:
        demand['|'.join(normalize(request[f]) for f in ('product','size','color'))]+=1
    items=[];covered_value=0;missing_cost=0
    for row in inventory:
        if row['quantity']<=0:continue
        held=held_quantity(db,row);available=max(0,row['quantity']-held)
        sold_units=int(sold.get(row['sku'],0))
        key='|'.join((normalize(row['product']),normalize(row['size']),normalize(row['color'])))
        requests=demand.get(key,0);unit_cost=costs.get(row['sku'])
        value=unit_cost*row['quantity'] if unit_cost is not None else None
        if value is None:missing_cost+=1
        else:covered_value+=value
        item={'sku':row['sku'],'product':row['product'],'size':row['size'],'quantity':row['quantity'],
              'available':available,'held':held,'sold_units':sold_units,'open_requests':requests,
              'estimated_stock_cost_kopeks':value,'unit_cost_source':'recorded_sale_item' if value is not None else 'missing',
              'signal':'requests_with_stock' if requests and available else 'no_recorded_sales' if not sold_units else 'observed_sales'}
        item['key']=digest({'store':sid,'kind':'stock','sku':row['sku']})[:20]
        items.append(item)
    items.sort(key=lambda x:(x['signal']!='no_recorded_sales',-x['quantity'],x['sku']))
    return {'days':days,'items':items[:150],'total_positions':len(items),'positions_without_known_cost':missing_cost,
            'valued_known_stock_kopeks':covered_value,'total_stock_cost_kopeks':covered_value if missing_cost==0 else None,
            'warnings':['Нет продаж за период означает отсутствие зарегистрированных товарных строк, а не доказанную неликвидность.',
                        'Оценка запасов использует последнюю известную себестоимость из товарной строки продажи, не фактическую закупочную себестоимость партии.',
                        'При неполной себестоимости общая стоимость склада не показывается.']}


def findings(db,store) -> list[dict]:
    quality=source_quality(db,store,14)
    demand=demand_matrix(db,store,30)
    stocks=stock_health(db,store,30)
    signals=[]
    for flag in quality['flags']:
        if flag['severity']=='info':continue
        signals.append({'source':'quality','key':flag['key'],'title':flag['title'],'evidence':flag,'priority':'high' if flag['severity']=='critical' else 'medium'})
    for item in demand['items']:
        if item['requests']<2 or item['signal']=='available':continue
        signals.append({'source':'demand','key':item['key'],'title':f"Проверить спрос: {item['product']} · {item['size']}",
                        'priority':'medium','evidence':item})
    for item in stocks['items']:
        if item['signal']=='no_recorded_sales' and item['quantity']>=2:
            title=f"Проверить остаток без зарегистрированных продаж: {item['sku']}"
        elif item['signal']=='requests_with_stock' and item['open_requests']>=2:
            title=f"Проверить доступность при повторяющихся запросах: {item['sku']}"
        else:continue
        signals.append({'source':'stock','key':item['key'],'title':title,
                        'priority':'medium','evidence':item})
    return signals[:200]


class CsvPreview(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    kind:Literal['inventory','pos']
    csv_text:str=Field(min_length=5,max_length=300_000)


class CsvCommit(BaseModel):
    batch_key:str=Field(min_length=8,max_length=100)


class NewAction(BaseModel):
    slug:str=Field(min_length=1,max_length=80)
    source:Literal['quality','demand','stock']
    signal_key:str=Field(min_length=2,max_length=100)
    request_id:str=Field(min_length=12,max_length=120)


class ActionUpdate(BaseModel):
    version:int=Field(ge=1)
    status:Literal['testing','resolved','dismissed']
    result_note:str=Field(default='',max_length=1500)


def build_router(admin_dep,db_dep):
    router=APIRouter(prefix='/api/admin/r13',tags=['Merchant Control Room'])

    @router.post('/csv/preview',status_code=201)
    def csv_preview(payload:CsvPreview,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,payload.slug,principal)
        parsed=parse_merchant_csv(payload.csv_text,payload.kind,store)
        result=preview_import(db,organization_id=principal.organization_id,store_id=store['id'],
                              user_id=None if principal.demo else principal.user_id,kind=payload.kind,rows=parsed['rows'])
        audit(db,principal,'r13.csv.preview',result['batch_key']);db.commit()
        return {**result,'csv':{'columns':parsed['columns'],'rows':parsed['count'],'sample':parsed['rows'][:5]},
                'note':parsed['note']}

    @router.post('/csv/commit')
    def csv_commit(payload:CsvCommit,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        result=apply_import(db,batch_key=payload.batch_key,organization_id=principal.organization_id,
                            check_store=lambda sid:check_store_access(db,sid,principal))
        audit(db,principal,'r13.csv.commit',payload.batch_key);db.commit()
        return result

    @router.get('/quality')
    def quality(slug:str='central',days:int=14,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return source_quality(db,visible_store(db,slug,principal),days)

    @router.get('/demand')
    def demand(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return demand_matrix(db,visible_store(db,slug,principal),days)

    @router.get('/stock')
    def stock(slug:str='central',days:int=30,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        return stock_health(db,visible_store(db,slug,principal),days)

    @router.get('/findings')
    def get_findings(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        return {'store':slug,'generated_at':now_iso(),'items':findings(db,store),
                'disclaimer':'Сигналы для проверки, не доказанная недополученная прибыль.'}

    @router.get('/actions')
    def list_actions(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        items=[dict(x) for x in db.execute('SELECT * FROM control_actions_r13 WHERE organization_id=? AND store_id=? ORDER BY id DESC LIMIT 100',(principal.organization_id,store['id']))]
        for item in items:item['evidence']=json.loads(item.pop('evidence_json'))
        return {'items':items}

    @router.post('/actions',status_code=201)
    def create_action(data:NewAction,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        store=visible_store(db,data.slug,principal)
        available=next((s for s in findings(db,store) if s['source']==data.source and s['key']==data.signal_key),None)
        if available is None:raise HTTPException(409,'Сигнал изменился или больше не доступен, обновите страницу')
        evidence={'source':available['source'],'signal_key':available['key'],'snapshot':available['evidence'],
                  'captured_at':now_iso(),'interpretation':'Проверить гипотезу; нет доказанного прироста прибыли'}
        fingerprint=digest(evidence)
        db.execute('BEGIN IMMEDIATE')
        try:
            previous=db.execute('SELECT * FROM control_actions_r13 WHERE organization_id=? AND request_id=?',(principal.organization_id,data.request_id)).fetchone()
            if previous:
                if previous['store_id']!=store['id'] or previous['signal_key']!=data.signal_key or previous['source']!=data.source:
                    raise HTTPException(409,'Идентификатор операции уже используется')
                db.commit();return {'id':previous['id'],'duplicate':True,'status':previous['status']}
            cur=db.execute('''INSERT INTO control_actions_r13(organization_id,store_id,request_id,source,signal_key,title,
              evidence_json,evidence_sha256,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (principal.organization_id,store['id'],data.request_id,data.source,data.signal_key,available['title'],
               json.dumps(evidence,ensure_ascii=False,sort_keys=True),fingerprint,now_iso(),now_iso()))
            audit(db,principal,'r13.action.create',str(cur.lastrowid));db.commit()
            return {'id':cur.lastrowid,'duplicate':False,'status':'open','evidence_sha256':fingerprint}
        except Exception:
            db.rollback();raise

    @router.patch('/actions/{action_id}')
    def update_action(action_id:int,data:ActionUpdate,principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        require_role(principal,'owner','manager')
        if data.status=='resolved' and len(data.result_note.strip())<15:
            raise HTTPException(422,'Опишите проверяемый результат не короче 15 символов')
        db.execute('BEGIN IMMEDIATE')
        try:
            row=db.execute('SELECT * FROM control_actions_r13 WHERE id=? AND organization_id=?',(action_id,principal.organization_id)).fetchone()
            if not row:raise HTTPException(404,'Задача не найдена')
            check_store_access(db,row['store_id'],principal)
            if row['status'] in ('resolved','dismissed'):raise HTTPException(409,'Закрытую задачу нельзя перезаписать')
            if row['version']!=data.version:raise HTTPException(409,'Задача уже изменена; обновите страницу')
            db.execute('UPDATE control_actions_r13 SET status=?,result_note=?,version=version+1,updated_at=? WHERE id=?',
                       (data.status,data.result_note.strip(),now_iso(),action_id))
            audit(db,principal,'r13.action.update',str(action_id));db.commit()
            return {'id':action_id,'status':data.status,'version':data.version+1}
        except Exception:
            db.rollback();raise

    @router.get('/actions.csv')
    def actions_csv(slug:str='central',principal:Principal=Depends(admin_dep),db:sqlite3.Connection=Depends(db_dep)):
        store=visible_store(db,slug,principal)
        output=io.StringIO();writer=csv.writer(output,delimiter=';')
        writer.writerow(['ID','Название','Источник','Статус','Результат','SHA256','Дата'])
        for r in db.execute('''SELECT id,title,source,status,result_note,evidence_sha256,created_at
                  FROM control_actions_r13 WHERE organization_id=? AND store_id=? ORDER BY id DESC LIMIT 1000''',(principal.organization_id,store['id'])):
            writer.writerow([safe_spreadsheet_cell(v) for v in r])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-actions-r13.csv"'})

    return router
