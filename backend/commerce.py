"""R0.5 commerce workflows.

Observations are anonymous aggregates; reservations are not transactions or sales.
No discount, transfer, refund, or customer notification is dispatched to a POS.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from backend.database import now_iso

DDL = """
CREATE TABLE IF NOT EXISTS reservations (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 request_id TEXT NOT NULL,
 demand_id INTEGER NOT NULL REFERENCES demand(id),
 source_inventory_id INTEGER NOT NULL REFERENCES inventory(id),
 source_store_id INTEGER NOT NULL REFERENCES stores(id),
 destination_store_id INTEGER NOT NULL REFERENCES stores(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 20),
 status TEXT NOT NULL CHECK(status IN ('held','collected','cancelled','expired')),
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(organization_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_reservations_available ON reservations(source_inventory_id,status,expires_at);
CREATE INDEX IF NOT EXISTS idx_reservations_destination ON reservations(destination_store_id,created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_active_demand ON reservations(demand_id) WHERE status='held';
CREATE TABLE IF NOT EXISTS fitting_observations (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '',
 trials INTEGER NOT NULL CHECK(trials BETWEEN 1 AND 500),
 purchases INTEGER NOT NULL CHECK(purchases>=0 AND purchases<=trials),
 reason TEXT NOT NULL CHECK(reason IN ('none','fit','price','size','quality','other')),
 observed_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fitting_store_date ON fitting_observations(store_id,observed_at);
CREATE TABLE IF NOT EXISTS merchandise_returns (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 sale_id INTEGER NOT NULL REFERENCES sales(id),
 external_id TEXT NOT NULL,
 item_description TEXT NOT NULL,
 amount_kopeks INTEGER NOT NULL CHECK(amount_kopeks>0),
 reason TEXT NOT NULL CHECK(reason IN ('size','fit','quality','different','other')),
 created_at TEXT NOT NULL,
 UNIQUE(store_id,external_id)
);
CREATE INDEX IF NOT EXISTS idx_returns_store_date ON merchandise_returns(store_id,created_at);
CREATE TABLE IF NOT EXISTS price_scenarios (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 title TEXT NOT NULL, sku TEXT NOT NULL,
 price_kopeks INTEGER NOT NULL CHECK(price_kopeks>0),
 cost_kopeks INTEGER NOT NULL CHECK(cost_kopeks>=0),
 discount_bps INTEGER NOT NULL CHECK(discount_bps BETWEEN 0 AND 9000),
 baseline_units INTEGER NOT NULL CHECK(baseline_units BETWEEN 0 AND 1000000),
 planned_units INTEGER NOT NULL CHECK(planned_units BETWEEN 0 AND 1000000),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_store_date ON price_scenarios(store_id,created_at);
CREATE TABLE IF NOT EXISTS decision_tasks (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 decision_key TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('new','testing','done','dismissed')),
 note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
 UNIQUE(store_id,decision_key)
);
"""


def ensure_commerce_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


def reserved_quantity(db: sqlite3.Connection, inventory_id: int, as_of: str | None = None) -> int:
    return int(db.execute("""SELECT COALESCE(SUM(quantity),0) AS n FROM reservations
        WHERE source_inventory_id=? AND status='held' AND expires_at>?""",
        (inventory_id, as_of or now_iso())).fetchone()['n'])


def inventory_with_availability(db: sqlite3.Connection, store_id: int) -> list[dict]:
    rows = db.execute('SELECT * FROM inventory WHERE store_id=? ORDER BY product,size LIMIT 500',(store_id,)).fetchall()
    result=[]
    for row in rows:
        held=reserved_quantity(db,row['id'])
        result.append({**dict(row),'reserved':held,'available':max(0,row['quantity']-held)})
    return result


def matching_available(db: sqlite3.Connection, origin_store_id: int, product: str, size: str, color: str) -> list[dict]:
    """Exact normalized match, only within the origin store's organization."""
    norm = lambda v: ' '.join(v.casefold().strip().split())
    rows=db.execute("""SELECT i.*,s.slug,s.name AS store_name FROM inventory i
      JOIN stores s ON s.id=i.store_id
      WHERE i.store_id<>? AND s.organization_id=(SELECT organization_id FROM stores WHERE id=?) AND i.quantity>0""",
      (origin_store_id,origin_store_id)).fetchall()
    results=[]
    for row in rows:
        if norm(row['product'])!=norm(product) or norm(row['size'])!=norm(size) or (color and norm(row['color'])!=norm(color)):
            continue
        available=max(0,row['quantity']-reserved_quantity(db,row['id']))
        if available: results.append({**dict(row),'reserved':row['quantity']-available,'available':available})
    return sorted(results,key=lambda x:-x['available'])[:30]


def reserve_stock(db: sqlite3.Connection, *, organization_id:int, demand_id:int, inventory_id:int,
                  request_id:str, hours:int=24, quantity:int=1) -> dict:
    timestamp=now_iso()
    try:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM reservations WHERE organization_id=? AND request_id=?',(organization_id,request_id)).fetchone()
        if existing:
            if existing['demand_id']!=demand_id or existing['source_inventory_id']!=inventory_id or existing['quantity']!=quantity:
                raise HTTPException(409,'Этот идентификатор уже использован для другого резерва')
            db.commit()
            return {'id':existing['id'],'status':existing['status'],'expires_at':existing['expires_at'],'duplicate':True}
        db.execute("UPDATE reservations SET status='expired',updated_at=? WHERE organization_id=? AND status='held' AND expires_at<=?",(timestamp,organization_id,timestamp))
        demand=db.execute('SELECT d.*,s.organization_id FROM demand d JOIN stores s ON s.id=d.store_id WHERE d.id=?',(demand_id,)).fetchone()
        item=db.execute('SELECT i.*,s.organization_id FROM inventory i JOIN stores s ON s.id=i.store_id WHERE i.id=?',(inventory_id,)).fetchone()
        if not demand or not item or demand['organization_id']!=organization_id or item['organization_id']!=organization_id:
            raise HTTPException(404,'Товар или запрос не найден')
        if demand['store_id']==item['store_id']:
            raise HTTPException(422,'Для резерва в другом филиале укажите другой магазин')
        if demand['status'] in ('converted','closed'):
            raise HTTPException(409,'Этот запрос уже закрыт')
        norm=lambda v:' '.join((v or '').casefold().split())
        if norm(demand['product'])!=norm(item['product']) or norm(demand['size'])!=norm(item['size']) or (demand['color'] and norm(demand['color'])!=norm(item['color'])):
            raise HTTPException(422,'Размер, цвет или модель не совпадают с запросом')
        if quantity>item['quantity']-reserved_quantity(db,item['id'],timestamp):
            raise HTTPException(409,'Свободных единиц товара недостаточно')
        expires=(datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat(timespec='seconds')
        cursor=db.execute('''INSERT INTO reservations(organization_id,request_id,demand_id,source_inventory_id,
          source_store_id,destination_store_id,quantity,status,expires_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(organization_id,request_id,demand_id,inventory_id,item['store_id'],demand['store_id'],quantity,'held',expires,timestamp,timestamp))
        db.execute("UPDATE demand SET status='located',updated_at=? WHERE id=?",(timestamp,demand_id))
        db.execute('INSERT INTO demand_history(demand_id,previous_status,next_status,note,occurred_at) VALUES(?,?,?,?,?)',
          (demand_id,demand['status'],'located',f'Резерв в филиале; №{cursor.lastrowid}',timestamp))
        db.commit()
        return {'id':cursor.lastrowid,'status':'held','expires_at':expires,'duplicate':False}
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,'Для этого запроса уже создан активный резерв') from exc
    except Exception:
        db.rollback()
        raise


def update_reservation(db:sqlite3.Connection, reservation_id:int, action:str) -> dict:
    timestamp=now_iso()
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM reservations WHERE id=?',(reservation_id,)).fetchone()
        if not row: raise HTTPException(404,'Резерв не найден')
        if row['status']!='held' or row['expires_at']<=timestamp:
            raise HTTPException(409,'Резерв уже завершён или истёк')
        if action=='collect':
            updated=db.execute('UPDATE inventory SET quantity=quantity-?,updated_at=? WHERE id=? AND quantity>=?',
               (row['quantity'],timestamp,row['source_inventory_id'],row['quantity']))
            if updated.rowcount!=1:
                raise HTTPException(409,'Недостаточно товара в текущих остатках. Сверьте склад.')
            status='collected'
        elif action=='cancel': status='cancelled'
        else: raise HTTPException(422,'Недопустимое действие')
        db.execute('UPDATE reservations SET status=?,updated_at=? WHERE id=?',(status,timestamp,reservation_id))
        if action=='cancel':
            demand=db.execute('SELECT * FROM demand WHERE id=?',(row['demand_id'],)).fetchone()
            if demand and demand['status']=='located':
                db.execute('UPDATE demand SET status=?,updated_at=? WHERE id=?',('open',timestamp,row['demand_id']))
                db.execute('INSERT INTO demand_history(demand_id,previous_status,next_status,note,occurred_at) VALUES(?,?,?,?,?)',
                           (row['demand_id'],'located','open','Резерв отменён',timestamp))
        db.commit()
        return {'id':reservation_id,'status':status,'not_a_sale':True}
    except Exception:
        db.rollback()
        raise


def fitting_report(db:sqlite3.Connection,store_id:int,days:int=30)->dict:
    start=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    recent=[dict(r) for r in db.execute('SELECT * FROM fitting_observations WHERE store_id=? ORDER BY id DESC LIMIT 50',(store_id,))]
    grouped=[dict(r) for r in db.execute('''SELECT product,size, SUM(trials) trials,SUM(purchases) purchases,
          COUNT(*) observations FROM fitting_observations WHERE store_id=? AND observed_at>=?
          GROUP BY product,size ORDER BY trials DESC LIMIT 30''',(store_id,start))]
    for r in grouped: r['purchase_rate']=round(r['purchases']*100/r['trials'],1) if r['trials'] else None
    reasons=[dict(r) for r in db.execute('''SELECT reason,COUNT(*) count FROM fitting_observations
       WHERE store_id=? AND observed_at>=? AND reason!='none' GROUP BY reason ORDER BY count DESC''',(store_id,start))]
    return {'products':grouped,'reasons':reasons,'recent':recent,
            'note':'Ручные агрегированные наблюдения без личностей. Причины сгруппированы по числу записей, а не по числу покупателей; не образуют сквозную воронку.'}


def return_report(db:sqlite3.Connection,store_id:int,days:int=30)->dict:
    start=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    recent=[dict(r) for r in db.execute('SELECT * FROM merchandise_returns WHERE store_id=? ORDER BY id DESC LIMIT 50',(store_id,))]
    totals=db.execute('''SELECT COUNT(*) quantity,COALESCE(SUM(amount_kopeks),0) amount_kopeks FROM merchandise_returns
       WHERE store_id=? AND created_at>=?''',(store_id,start)).fetchone()
    reasons=[dict(r) for r in db.execute('''SELECT reason,COUNT(*) quantity,COALESCE(SUM(amount_kopeks),0) amount_kopeks
       FROM merchandise_returns WHERE store_id=? AND created_at>=? GROUP BY reason ORDER BY quantity DESC''',(store_id,start))]
    return {'total':dict(totals),'reasons':reasons,'recent':recent,'note':'Возвраты учитываются отдельно от выручки и не отправляются автоматически в кассу. Состав конкретного чека не проверяется без построчной интеграции.'}


def record_return(db:sqlite3.Connection,*,store_id:int,sale_id:int,external_id:str,
                  item:str,reason:str,amount_kopeks:int)->dict:
    try:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM merchandise_returns WHERE store_id=? AND external_id=?',(store_id,external_id)).fetchone()
        if existing:
            if (existing['sale_id'],existing['item_description'],existing['reason'],existing['amount_kopeks'])!=(sale_id,item,reason,amount_kopeks):
                raise HTTPException(409,'Идентификатор возврата уже занят другим событием')
            db.commit()
            return {'id':existing['id'],'duplicate':True}
        sale=db.execute('SELECT * FROM sales WHERE id=? AND store_id=?',(sale_id,store_id)).fetchone()
        if not sale:raise HTTPException(422,'Чек не принадлежит выбранному магазину')
        previous=db.execute('SELECT COALESCE(SUM(amount_kopeks),0) n FROM merchandise_returns WHERE sale_id=?',(sale_id,)).fetchone()['n']
        if previous+amount_kopeks>sale['amount_kopeks']:
            raise HTTPException(409,'Общая сумма возвратов превышает сумму чека')
        cursor=db.execute('''INSERT INTO merchandise_returns(store_id,sale_id,external_id,item_description,amount_kopeks,reason,created_at)
          VALUES(?,?,?,?,?,?,?)''',(store_id,sale_id,external_id,item,amount_kopeks,reason,now_iso()))
        db.commit()
        return {'id':cursor.lastrowid,'duplicate':False}
    except Exception:
        db.rollback()
        raise


def price_analysis(row: dict) ->dict:
    discounted=int((Decimal(row['price_kopeks'])*(Decimal(10000-row['discount_bps'])/Decimal(10000))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    unit_before=row['price_kopeks']-row['cost_kopeks']
    unit_after=discounted-row['cost_kopeks']
    baseline_profit=unit_before*row['baseline_units']
    planned_profit=unit_after*row['planned_units']
    break_even=(baseline_profit+unit_after-1)//unit_after if unit_after>0 and baseline_profit>=0 else None
    return {**row,'discounted_price_kopeks':discounted,'unit_profit_before_kopeks':unit_before,
        'unit_profit_after_kopeks':unit_after,'baseline_gross_profit_kopeks':baseline_profit,
        'scenario_gross_profit_kopeks':planned_profit,'delta_kopeks':planned_profit-baseline_profit,
        'break_even_units':break_even,'warning':('Цена со скидкой не покрывает себестоимость.' if unit_after<=0 else
          'Эффект зависит от предположения о числе продаж; это не прогноз.')}


def price_report(db:sqlite3.Connection,store_id:int)->list[dict]:
    return [price_analysis(dict(r)) for r in db.execute('SELECT * FROM price_scenarios WHERE store_id=? ORDER BY id DESC LIMIT 50',(store_id,))]


def decision_report(db:sqlite3.Connection,store_id:int)->list[dict]:
    """Only observable evidence; actionable but not a claim of causality or future profit."""
    proposals=[]
    last_30=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(timespec='seconds')
    unresolved=db.execute('''SELECT product,size,COUNT(*) n FROM demand WHERE store_id=? AND status IN ('open','located','notified')
      AND created_at>=? GROUP BY product,size HAVING COUNT(*)>=3 ORDER BY n DESC LIMIT 4''',(store_id,last_30)).fetchall()
    for r in unresolved:
        key=hashlib.sha256(f"demand|{r['product']}|{r['size']}".encode()).hexdigest()[:20]
        proposals.append({'key':'demand-'+key,'kind':'demand','priority':'high','title':'Повторяющийся неудовлетворённый спрос',
          'evidence':f"{r['n']} открытых запросов: {r['product']} · {r['size']}",
          'suggestion':'Проверить фактический остаток, поставку или возможность бронирования в другом филиале.', 'count':r['n']})
    fitting=fitting_report(db,store_id)
    for r in fitting['products']:
        if r['trials']>=8 and r['purchases']/r['trials']<0.25:
            key=hashlib.sha256(f"fit|{r['product']}|{r['size']}".encode()).hexdigest()[:20]
            proposals.append({'key':'fitting-'+key,'kind':'fitting','priority':'medium','title':'Низкая доля покупок после примерок',
              'evidence':f"{r['purchases']} покупок после {r['trials']} примерок: {r['product']} · {r['size']}",
              'suggestion':'Сверить посадку и причины добровольных отказов на этой модели.', 'count':r['trials']})
    ret=return_report(db,store_id)
    for r in ret['reasons']:
        if r['quantity']>=3:
            proposals.append({'key':'returns-'+r['reason'],'kind':'returns','priority':'medium','title':'Повторяющаяся причина возврата',
              'evidence':f"{r['quantity']} возвратов, причина: {r['reason']}",
              'suggestion':'Проверить описание товара, посадку и качество партии до новой закупки.', 'count':r['quantity']})
    for r in price_report(db,store_id):
        if r['unit_profit_after_kopeks']<=0:
            proposals.append({'key':f"pricing-{r['id']}",'kind':'pricing','priority':'high','title':'Сценарий скидки с отрицательной маржой',
              'evidence':f"{r['title']}: маржа после скидки {r['unit_profit_after_kopeks']/100:,.2f} ₽/ед.",
              'suggestion':'Пересмотреть скидку или себестоимость перед запуском акции.', 'count':1})
    if not proposals:
        proposals.append({'key':'measurement-start','kind':'setup','priority':'info','title':'Соберите исходные данные',
          'evidence':'Недостаточно наблюдений для автоматических сигналов.',
          'suggestion':'Проведите ограниченный пилот с проверкой качества данных.', 'count':0})
    previous={r['decision_key']:dict(r) for r in db.execute('SELECT * FROM decision_tasks WHERE store_id=?',(store_id,))}
    rank={'high':0,'medium':1,'info':2}
    for item in proposals:
        state=previous.get(item['key'])
        item['status']=state['status'] if state else 'new'
        item['note']=state['note'] if state else ''
    return sorted(proposals,key=lambda r:(rank[r['priority']],-r['count']))
