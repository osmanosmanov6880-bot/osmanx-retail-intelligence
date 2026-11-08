"""R1.4 Retail Integrity Center: verified-by-source workflows, no POS execution.

Five integrated modules: inbox, reconciliation, gift-cost evidence, incidents,
executive quality reporting. All mutations are tenant-scoped and audited.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.database import now_iso
from backend.retail import safe_spreadsheet_cell
from backend.security import Principal, audit, require_role, visible_store

DDL = """
CREATE TABLE IF NOT EXISTS r14_inbox (
 id INTEGER PRIMARY KEY,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 source TEXT NOT NULL, external_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('receipt','stock')),
 payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','reviewed','rejected')),
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, reviewed_at TEXT,
 UNIQUE(organization_id, source, external_id, kind)
);
CREATE INDEX IF NOT EXISTS r14_inbox_store_idx ON r14_inbox(store_id,status,created_at);
CREATE TABLE IF NOT EXISTS r14_gift_costs (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), reference TEXT NOT NULL,
 campaign TEXT NOT NULL, cost_kopeks INTEGER NOT NULL CHECK(cost_kopeks>=0),
 status TEXT NOT NULL CHECK(status IN ('confirmed','reversed')),
 note TEXT NOT NULL, recorded_at TEXT NOT NULL, reversed_at TEXT,
 UNIQUE(organization_id,reference)
);
CREATE TABLE IF NOT EXISTS r14_incidents (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id), fingerprint TEXT NOT NULL,
 severity TEXT NOT NULL CHECK(severity IN ('warning','critical')),
 title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','acknowledged','resolved')),
 note TEXT NOT NULL DEFAULT '', actor_id INTEGER, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, UNIQUE(store_id,fingerprint)
);
CREATE TABLE IF NOT EXISTS r14_incident_history (
 id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES r14_incidents(id),
 previous_status TEXT, next_status TEXT NOT NULL,
 actor_id INTEGER, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS r14_incident_history_idx ON r14_incident_history(incident_id,id);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)
    cols={r['name'] for r in db.execute('PRAGMA table_info(r14_gift_costs)')}
    if 'claim_id' not in cols:
        db.execute('ALTER TABLE r14_gift_costs ADD COLUMN claim_id INTEGER')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS r14_linked_coupon_unique ON r14_gift_costs(organization_id,claim_id) WHERE claim_id IS NOT NULL')


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def has_table(db: sqlite3.Connection, table: str) -> bool:
    return bool(db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone())


class InboxCreate(BaseModel):
    slug: str = Field(default='central', min_length=1, max_length=80)
    source: str = Field(min_length=2,max_length=60,pattern=r'^[a-zA-Z0-9_.:-]+$')
    external_id: str = Field(min_length=3,max_length=120)
    kind: Literal['receipt','stock']
    payload: dict

class Review(BaseModel):
    status: Literal['reviewed','rejected']
    note: str = Field(min_length=3,max_length=400)

class GiftCreate(BaseModel):
    slug: str = Field(default='central',min_length=1,max_length=80)
    reference: str = Field(min_length=3,max_length=120)
    campaign: str = Field(min_length=2,max_length=120)
    cost_kopeks: int = Field(ge=0,le=100_000_000)
    note: str = Field(min_length=3,max_length=400)
    coupon_claim_id: int | None = Field(default=None,gt=0)

class IncidentUpdate(BaseModel):
    status: Literal['acknowledged','resolved']
    note: str = Field(min_length=5,max_length=400)


def validate_event(kind: str, payload: dict) -> None:
    allowed={'receipt':{'amount_kopeks','occurred_at','sku','quantity'},
             'stock':{'sku','quantity','product','size','color'}}[kind]
    if set(payload)-allowed:
        raise HTTPException(422,'Допускаются только обезличенные служебные поля')
    if kind=='receipt':
        amount=payload.get('amount_kopeks')
        if type(amount) is not int or not 0<=amount<=1_000_000_000:
            raise HTTPException(422,'Сумма чека должна быть целым числом копеек')
        timestamp=payload.get('occurred_at')
        if not isinstance(timestamp,str) or len(timestamp)>45:
            raise HTTPException(422,'Укажите корректное время чека')
        try:
            when=datetime.fromisoformat(timestamp)
            if when.tzinfo is None or when.utcoffset() is None:raise ValueError('timezone')
        except (ValueError,TypeError,OverflowError):
            raise HTTPException(422,'Время чека должно быть ISO 8601 с часовым поясом') from None
    if kind=='stock':
        if 'sku' not in payload or 'quantity' not in payload:
            raise HTTPException(422,'Требуются SKU и количество')
        if type(payload['quantity']) is not int or not 0<=payload['quantity']<=100_000:
            raise HTTPException(422,'Неверное количество товара')
    for key,limit in [('sku',120),('product',120),('size',30),('color',50)]:
        if key in payload and (not isinstance(payload[key],str) or len(payload[key])>limit or (key=='sku' and not payload[key].strip())):
            raise HTTPException(422,f'Неверное значение {key}')
    if 'quantity' in payload and (type(payload['quantity']) is not int or not 1<=payload['quantity']<=100_000):
        if kind=='receipt':raise HTTPException(422,'Количество в чеке должно быть положительным')
        if kind=='stock' and payload['quantity']!=0:raise HTTPException(422,'Неверное количество на складе')
    if len(canonical(payload).encode('utf-8'))>8192:
        raise HTTPException(413,'Пакет превышает 8 КиБ')


def put_inbox(db,principal:Principal,data:InboxCreate) -> dict:
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    validate_event(data.kind,data.payload)
    fingerprint=digest(data.payload)
    db.execute('BEGIN IMMEDIATE')
    try:
        prior=db.execute('SELECT * FROM r14_inbox WHERE organization_id=? AND source=? AND external_id=? AND kind=?',
            (principal.organization_id,data.source,data.external_id,data.kind)).fetchone()
        if prior:
            if prior['fingerprint']!=fingerprint or prior['store_id']!=store['id']:
                raise HTTPException(409,'Конфликт внешнего идентификатора и содержимого')
            db.commit()
            return {'id':prior['id'],'duplicate':True,'status':prior['status']}
        cur=db.execute('''INSERT INTO r14_inbox(organization_id,store_id,source,external_id,kind,payload,fingerprint,created_at)
          VALUES(?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],data.source,data.external_id,
                              data.kind,canonical(data.payload),fingerprint,now_iso()))
        audit(db,principal,'r14.inbox.queue',str(cur.lastrowid))
        db.commit()
        return {'id':cur.lastrowid,'duplicate':False,'status':'pending'}
    except Exception:
        db.rollback();raise


def inbox_review(db,principal:Principal,item_id:int,data:Review) -> dict:
    require_role(principal,'owner','manager')
    db.execute('BEGIN IMMEDIATE')
    try:
        item=db.execute('SELECT * FROM r14_inbox WHERE id=? AND organization_id=?',(item_id,principal.organization_id)).fetchone()
        if item is None:raise HTTPException(404,'Событие не найдено')
        st=db.execute('SELECT slug FROM stores WHERE id=?',(item['store_id'],)).fetchone()
        visible_store(db,st['slug'],principal)
        if item['status']!='pending':raise HTTPException(409,'Событие уже рассмотрено')
        db.execute('UPDATE r14_inbox SET status=?,note=?,reviewed_at=? WHERE id=?',
                   (data.status,data.note.strip(),now_iso(),item_id))
        audit(db,principal,'r14.inbox.review',str(item_id))
        db.commit()
        return {'id':item_id,'status':data.status,'note':data.note,
                'warning':'Рассмотрение события не создаёт чек и не меняет остатки'}
    except Exception:
        db.rollback();raise


def reconciliation_items(db,store,days:int,limit:int=10000):
    if not 1<=days<=90:raise HTTPException(422,'Период должен составлять 1–90 дней')
    if not 1<=limit<=10000:raise HTTPException(422,'Допустимо от 1 до 10000 записей')
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    events=db.execute("""SELECT * FROM r14_inbox WHERE store_id=? AND kind='receipt' AND created_at>=?
       ORDER BY id DESC LIMIT 10001""",(store['id'],since)).fetchall()
    if len(events)>10000:raise HTTPException(413,'Слишком много событий для сверки')
    out=[]
    for event in events:
        receipt=db.execute('''SELECT id,amount_kopeks,occurred_at FROM sales WHERE store_id=? AND source=? AND external_id=?''',
            (store['id'],event['source'],event['external_id'])).fetchone()
        expected=json.loads(event['payload'])['amount_kopeks']
        status=('missing' if receipt is None else 'matched' if receipt['amount_kopeks']==expected else 'amount_conflict')
        out.append({'inbox_id':event['id'],'source':event['source'],'external_id':event['external_id'],
                    'queue_status':event['status'],'comparison':status,'expected_kopeks':expected,
                    'recorded_kopeks':receipt['amount_kopeks'] if receipt else None,
                    'sale_id':receipt['id'] if receipt else None,'created_at':event['created_at']})
    return out[:limit],len(events)


def reconcile(db,store,days:int):
    items,total=reconciliation_items(db,store,days)
    counts=Counter(r['comparison'] for r in items)
    return {'total':total,'matched':counts['matched'],'missing':counts['missing'],
            'amount_conflicts':counts['amount_conflict'],
            'quality':'verified' if total>0 and counts['missing']==0 and counts['amount_conflict']==0 else 'incomplete',
            'note':'Сверка служебных сообщений с локальными чеками. Не является банковским подтверждением оплаты.'}


def validate_claim_proof(db,principal:Principal,store,claim_id:int,ref:str,campaign:str,cost:int):
    if not (has_table(db,'campaign_claims_r11') and has_table(db,'coupon_fulfillments_r12')):
        raise HTTPException(422,'Модуль проверенных бонусов не установлен')
    row=db.execute('''SELECT cl.id,cl.status,cl.organization_id,ca.store_id,ca.title,ca.unit_cost_kopeks,
       f.proof_reference FROM campaign_claims_r11 cl
       JOIN campaigns_r11 ca ON ca.id=cl.campaign_id
       LEFT JOIN coupon_fulfillments_r12 f ON f.claim_id=cl.id
       WHERE cl.id=? AND cl.organization_id=?''',(claim_id,principal.organization_id)).fetchone()
    if row is None or row['store_id']!=store['id']:
        raise HTTPException(404,'Бонус не найден в этом филиале')
    if row['status']!='redeemed' or not row['proof_reference']:
        raise HTTPException(409,'Бонус не подтверждён чеком и актом выдачи')
    if row['proof_reference']!=ref or row['title']!=campaign or row['unit_cost_kopeks']!=cost:
        raise HTTPException(422,'Данные расхода не соответствуют документу бонуса')


def add_gift(db,principal:Principal,data:GiftCreate):
    require_role(principal,'owner','manager')
    store=visible_store(db,data.slug,principal)
    db.execute('BEGIN IMMEDIATE')
    try:
        if data.coupon_claim_id is not None:
            validate_claim_proof(db,principal,store,data.coupon_claim_id,data.reference,data.campaign,data.cost_kopeks)
        existing=db.execute('SELECT * FROM r14_gift_costs WHERE organization_id=? AND reference=?',
                            (principal.organization_id,data.reference)).fetchone()
        if existing:
            if (existing['store_id']!=store['id'] or existing['campaign']!=data.campaign or
                existing['cost_kopeks']!=data.cost_kopeks or existing['claim_id']!=data.coupon_claim_id):
                raise HTTPException(409,'Номер документа используется с другими данными')
            db.commit();return {'id':existing['id'],'duplicate':True,'status':existing['status']}
        cur=db.execute('''INSERT INTO r14_gift_costs(organization_id,store_id,reference,campaign,cost_kopeks,status,note,recorded_at,claim_id)
            VALUES(?,?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],data.reference,data.campaign,
                   data.cost_kopeks,'confirmed',data.note.strip(),now_iso(),data.coupon_claim_id))
        audit(db,principal,'r14.gift.confirm',str(cur.lastrowid))
        db.commit()
        return {'id':cur.lastrowid,'duplicate':False,'status':'confirmed',
                'evidence_level':'linked_coupon_proof' if data.coupon_claim_id else 'manual_entry'}
    except sqlite3.IntegrityError as exc:
        db.rollback();raise HTTPException(409,'Документ или бонус уже учтён') from exc
    except Exception:
        db.rollback();raise


def reverse_gift(db,principal:Principal,gift_id:int,reason:str):
    require_role(principal,'owner')
    if len(reason.strip())<5:raise HTTPException(422,'Требуется объяснение причины')
    db.execute('BEGIN IMMEDIATE')
    try:
        row=db.execute('SELECT * FROM r14_gift_costs WHERE id=? AND organization_id=?',
                       (gift_id,principal.organization_id)).fetchone()
        if row is None:raise HTTPException(404,'Расход не найден')
        st=db.execute('SELECT slug FROM stores WHERE id=?',(row['store_id'],)).fetchone()
        visible_store(db,st['slug'],principal)
        if row['status']!='confirmed':raise HTTPException(409,'Расход уже отменён')
        db.execute("UPDATE r14_gift_costs SET status='reversed',reversed_at=? WHERE id=?",(now_iso(),gift_id))
        audit(db,principal,'r14.gift.reverse',f'{gift_id}: {reason.strip()[:100]}')
        db.commit()
        return {'id':gift_id,'status':'reversed','note':'Отменён учёт расхода, но не POS-событие или акт выдачи'}
    except Exception:
        db.rollback();raise


def gift_summary(db,store_id:int,since:str):
    row=db.execute('''SELECT COALESCE(SUM(CASE WHEN status='confirmed' THEN cost_kopeks ELSE 0 END),0) AS cost,
       COUNT(CASE WHEN status='confirmed' AND claim_id IS NOT NULL THEN 1 END) AS linked,
       COUNT(CASE WHEN status='confirmed' AND claim_id IS NULL THEN 1 END) AS manual,
       COUNT(CASE WHEN status='reversed' THEN 1 END) AS reversed
       FROM r14_gift_costs WHERE store_id=? AND recorded_at>=?''',(store_id,since)).fetchone()
    return {k:int(row[k]) for k in ('cost','linked','manual','reversed')}


def quality(db,store,days:int=7):
    if not 1<=days<=90:raise HTTPException(422,'Период 1–90 дней')
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    receipts=db.execute('''SELECT COUNT(*) n,COALESCE(SUM(amount_kopeks),0) total FROM sales
       WHERE store_id=? AND occurred_at>=?''',(store['id'],since)).fetchone()
    surveys=db.execute('SELECT COUNT(*) n FROM surveys WHERE store_id=? AND created_at>=?',(store['id'],since)).fetchone()
    recon=reconcile(db,store,days)
    gifts=gift_summary(db,store['id'],since)
    pending=db.execute("SELECT COUNT(*) n FROM r14_inbox WHERE store_id=? AND status='pending'",(store['id'],)).fetchone()['n']
    incidents=db.execute("SELECT status,COUNT(*) n FROM r14_incidents WHERE store_id=? GROUP BY status",(store['id'],)).fetchall()
    open_counts={r['status']:r['n'] for r in incidents}
    warnings=[]
    if pending:warnings.append(f'{pending} пакетов ожидают проверки')
    if recon['missing']:warnings.append('Часть событий кассы отсутствует в реестре продаж')
    if recon['amount_conflicts']:warnings.append('Есть противоречия по суммам чеков')
    if gifts['manual']:warnings.append('Расходы на часть подарков внесены вручную без сверки с купоном')
    return {'days':days,'receipts':int(receipts['n']),'revenue_kopeks':int(receipts['total']),
      'surveys':int(surveys['n']),'gift_cost_kopeks':gifts['cost'],
      'gift_evidence':{'linked':gifts['linked'],'manual':gifts['manual'],'reversed':gifts['reversed']},
      'inbox_pending':int(pending),'reconciliation':recon,
      'incidents':{'open':open_counts.get('open',0),'acknowledged':open_counts.get('acknowledged',0),
                   'resolved':open_counts.get('resolved',0)},'warnings':warnings,
      'source_note':'Операционный журнал. Чеки берутся из локальной базы; подарки подтверждены актами или ручными записями. Это не аудит прибыли.'}


def active_signals(report):
    return [
      ('inbox_pending','warning','Пакеты ожидают рассмотрения') if report['inbox_pending'] else None,
      ('receipt_missing','critical','Кассовые события без зарегистрированного чека') if report['reconciliation']['missing'] else None,
      ('receipt_conflict','critical','Расхождения сумм кассовых чеков') if report['reconciliation']['amount_conflicts'] else None,
      ('manual_gifts','warning','Расходы на подарки без связанного купона') if report['gift_evidence']['manual'] else None,
    ]


def incident_transition(db,principal:Principal,item_id:int,data:IncidentUpdate):
    require_role(principal,'owner','manager')
    db.execute('BEGIN IMMEDIATE')
    try:
        row=db.execute('SELECT * FROM r14_incidents WHERE id=? AND organization_id=?',
                       (item_id,principal.organization_id)).fetchone()
        if row is None:raise HTTPException(404,'Инцидент не найден')
        st=db.execute('SELECT slug FROM stores WHERE id=?',(row['store_id'],)).fetchone()
        visible_store(db,st['slug'],principal)
        if row['status']=='resolved':raise HTTPException(409,'Инцидент уже закрыт')
        if row['status']=='open' and data.status=='resolved':raise HTTPException(409,'Сначала примите инцидент в работу')
        if row['status']==data.status:raise HTTPException(409,'Нет нового состояния')
        db.execute('UPDATE r14_incidents SET status=?,note=?,actor_id=?,updated_at=? WHERE id=?',
                   (data.status,data.note.strip(),principal.user_id or None,now_iso(),item_id))
        db.execute('''INSERT INTO r14_incident_history(incident_id,previous_status,next_status,actor_id,evidence,recorded_at)
           VALUES(?,?,?,?,?,?)''',(item_id,row['status'],data.status,principal.user_id or None,data.note.strip(),now_iso()))
        audit(db,principal,'r14.incident.update',str(item_id))
        db.commit()
        return {'id':item_id,'status':data.status}
    except Exception:
        db.rollback();raise


def sync_incidents(db,principal:Principal,store):
    require_role(principal,'owner','manager')
    report=quality(db,store)
    current=[s for s in active_signals(report) if s]
    db.execute('BEGIN IMMEDIATE')
    try:
        for code,severity,title in current:
            finger=digest({'store_id':store['id'],'signal':code})
            exists=db.execute('SELECT * FROM r14_incidents WHERE store_id=? AND fingerprint=?',(store['id'],finger)).fetchone()
            if exists:
                if exists['status']=='resolved':
                    db.execute("UPDATE r14_incidents SET status='open',severity=?,title=?,note='',updated_at=? WHERE id=?",
                               (severity,title,now_iso(),exists['id']))
                    db.execute('''INSERT INTO r14_incident_history(incident_id,previous_status,next_status,evidence,recorded_at)
                       VALUES(?,?,?,?,?)''',(exists['id'],'resolved','open','Сигнал возник повторно',now_iso()))
            else:
                cur=db.execute('''INSERT INTO r14_incidents(organization_id,store_id,fingerprint,severity,title,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)''',(principal.organization_id,store['id'],finger,severity,title,'open',now_iso(),now_iso()))
                db.execute('''INSERT INTO r14_incident_history(incident_id,previous_status,next_status,evidence,recorded_at)
                   VALUES(?,?,?,?,?)''',(cur.lastrowid,None,'open','Обнаружено системой',now_iso()))
        audit(db,principal,'r14.incidents.sync',store['slug'])
        db.commit()
    except Exception:
        db.rollback();raise
    return [dict(x) for x in db.execute('SELECT * FROM r14_incidents WHERE store_id=? ORDER BY id DESC LIMIT 150',(store['id'],))]


def export_rows(rows,fields):
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    writer.writerow(fields)
    for item in rows:
        writer.writerow([safe_spreadsheet_cell(item.get(x)) if isinstance(item.get(x),str) else item.get(x) for x in fields])
    return '\ufeff'+output.getvalue()


def install(app,admin,db_conn):
    router=APIRouter(prefix='/api/admin/r14',tags=['R1.4 Operations Integrity'])

    @router.post('/inbox',status_code=201)
    def queue(data:InboxCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return put_inbox(db,principal,data)

    @router.get('/inbox')
    def inbox(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(x) for x in db.execute('''SELECT id,source,external_id,kind,status,note,created_at
              FROM r14_inbox WHERE store_id=? ORDER BY id DESC LIMIT 150''',(store['id'],))]}

    @router.post('/inbox/{item_id}/review')
    def review(item_id:int,data:Review,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return inbox_review(db,principal,item_id,data)

    @router.get('/reconciliation')
    def reconciliation(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return reconcile(db,visible_store(db,slug,principal),days)

    @router.get('/reconciliation/items')
    def items(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        rows,total=reconciliation_items(db,visible_store(db,slug,principal),days)
        return {'items':rows[:200],'total':total,'truncated':len(rows)>200}

    @router.get('/reconciliation/export.csv')
    def export_reconciliation(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        rows,_=reconciliation_items(db,store,days)
        content=export_rows(rows,['source','external_id','comparison','expected_kopeks','recorded_kopeks','queue_status','created_at'])
        return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-reconciliation.csv"'})

    @router.post('/gifts',status_code=201)
    def gifts_create(data:GiftCreate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return add_gift(db,principal,data)

    @router.get('/gifts')
    def gifts(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM r14_gift_costs WHERE store_id=? ORDER BY id DESC LIMIT 150',(store['id'],))]}

    @router.post('/gifts/{gift_id}/reverse')
    def gifts_reverse(gift_id:int,reason:str,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return reverse_gift(db,principal,gift_id,reason)

    @router.get('/incidents')
    def incidents(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':[dict(x) for x in db.execute('SELECT * FROM r14_incidents WHERE store_id=? ORDER BY id DESC LIMIT 150',(store['id'],))]}

    @router.get('/incidents/{item_id}/history')
    def history(item_id:int,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        incident=db.execute('SELECT * FROM r14_incidents WHERE id=? AND organization_id=?',(item_id,principal.organization_id)).fetchone()
        if incident is None:raise HTTPException(404,'Инцидент не найден')
        st=db.execute('SELECT slug FROM stores WHERE id=?',(incident['store_id'],)).fetchone()
        visible_store(db,st['slug'],principal)
        return {'items':[dict(x) for x in db.execute('''SELECT previous_status,next_status,evidence,recorded_at
             FROM r14_incident_history WHERE incident_id=? ORDER BY id''',(item_id,))]}

    @router.post('/incidents/sync')
    def incidents_sync(slug:str='central',principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        return {'items':sync_incidents(db,principal,store)}

    @router.post('/incidents/{item_id}')
    def incidents_update(item_id:int,data:IncidentUpdate,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return incident_transition(db,principal,item_id,data)

    @router.get('/board')
    def board(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        return quality(db,visible_store(db,slug,principal),days)

    @router.get('/board/export.csv')
    def board_export(slug:str='central',days:int=7,principal:Principal=Depends(admin),db:sqlite3.Connection=Depends(db_conn)):
        store=visible_store(db,slug,principal)
        report=quality(db,store,days)
        keys=['days','receipts','revenue_kopeks','surveys','gift_cost_kopeks','inbox_pending']
        content=export_rows([{**report,'slug':slug}],['slug',*keys])
        return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="osmanx-integrity.csv"'})

    app.include_router(router)
