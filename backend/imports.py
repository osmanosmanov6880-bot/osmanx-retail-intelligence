"""Auditable, atomic preview -> apply for POS receipts and stock batches.

CSV/1C adapters can map exports to this strict JSON shape. No claim of a live
1C connection: operators review a staged batch before anything is written.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from backend.database import now_iso

IMPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS import_batches (
 id INTEGER PRIMARY KEY, batch_key TEXT NOT NULL UNIQUE,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 created_by INTEGER REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN ('pos','inventory')),
 rows_json TEXT NOT NULL, fingerprint TEXT NOT NULL, preview_json TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'preview' CHECK(status IN ('preview','applied')),
 created_at TEXT NOT NULL, applied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_import_org ON import_batches(organization_id,created_at);
"""

def ensure_import_schema(db: sqlite3.Connection) -> None:
    db.executescript(IMPORT_SCHEMA)


def _normalize(kind: str, rows: list[dict]) -> list[dict]:
    if kind not in ('pos','inventory') or not 1 <= len(rows) <= 2000:
        raise HTTPException(422, 'Неверный тип или размер пакета')
    normalized=[]
    seen=set()
    for index,row in enumerate(rows):
        try:
            if kind == 'pos':
                external_id=str(row['external_id']).strip()
                amount=Decimal(str(row['amount_rub']))
                occurred=datetime.fromisoformat(str(row['occurred_at']).replace('Z','+00:00'))
                if occurred.tzinfo is None:
                    raise ValueError('timestamp without timezone')
                if not 1 <= len(external_id) <= 120 or not amount.is_finite() or not 0 <= amount <= 20_000_000:
                    raise ValueError('invalid receipt')
                if not datetime.now(timezone.utc)-timedelta(days=365*5) <= occurred.astimezone(timezone.utc) <= datetime.now(timezone.utc)+timedelta(days=2):
                    raise ValueError('timestamp outside supported window')
                key=external_id
                result={'external_id':external_id,'amount_kopeks':int((amount*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)),
                        'occurred_at':occurred.astimezone(timezone.utc).isoformat(timespec='seconds')}
            else:
                sku=str(row['sku']).strip()
                product=str(row['product']).strip()
                size=str(row.get('size','')).strip()
                color=str(row.get('color','')).strip()
                quantity=row['quantity']
                if not isinstance(quantity,int) or isinstance(quantity,bool) or not 0 <= quantity <= 1_000_000:
                    raise ValueError('invalid quantity')
                if not 2 <= len(sku) <= 80 or not 2 <= len(product) <= 120 or len(size)>30 or len(color)>50:
                    raise ValueError('invalid item')
                key=sku.casefold()
                result={'sku':sku,'product':product,'size':size,'color':color,'quantity':quantity}
            if key in seen:
                raise ValueError('repeated identifier in batch')
            seen.add(key)
            normalized.append(result)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise HTTPException(422,f'Ошибка строки {index+1}: {str(exc)[:120]}') from None
    return normalized


def _plan(db:sqlite3.Connection,store_id:int,kind:str,rows:list[dict]) -> dict:
    added=updated=duplicate=0
    conflicts=[]
    for row in rows:
        if kind=='pos':
            old=db.execute('SELECT amount_kopeks,occurred_at FROM sales WHERE store_id=? AND source=? AND external_id=?',
                           (store_id,'pos_import',row['external_id'])).fetchone()
            if not old: added+=1
            elif old['amount_kopeks']==row['amount_kopeks'] and old['occurred_at']==row['occurred_at']: duplicate+=1
            else: conflicts.append(row['external_id'])
        else:
            old=db.execute('SELECT product,size,color,quantity FROM inventory WHERE store_id=? AND sku=? COLLATE NOCASE',
                           (store_id,row['sku'])).fetchone()
            if not old: added+=1
            elif all(old[col]==row[col] for col in ('product','size','color','quantity')): duplicate+=1
            else: updated+=1
    return {'added':added,'updated':updated,'unchanged':duplicate,'conflicts':conflicts[:20],'total':len(rows),
            'valid':not bool(conflicts)}


def preview_import(db:sqlite3.Connection,*,organization_id:int,store_id:int,user_id:int|None,
                   kind:str,rows:list[dict]) -> dict:
    records=_normalize(kind,rows)
    plan=_plan(db,store_id,kind,records)
    serialized=json.dumps(records,ensure_ascii=False,separators=(',',':'),sort_keys=True)
    fingerprint=hashlib.sha256(serialized.encode()).hexdigest()
    key='IMP-'+secrets.token_urlsafe(16)
    db.execute('INSERT INTO import_batches(batch_key,organization_id,store_id,created_by,kind,rows_json,fingerprint,preview_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
               (key,organization_id,store_id,user_id,kind,serialized,fingerprint,json.dumps(plan),now_iso()))
    db.commit()
    return {'batch_key':key,'kind':kind,'preview':plan,'expires_in_hours':24,'applied':False}


def apply_import(db:sqlite3.Connection,*,batch_key:str,organization_id:int,check_store) -> dict:
    # IMMEDIATE transaction holds writer lock across revalidation and all writes.
    db.execute('BEGIN IMMEDIATE')
    try:
        job=db.execute('SELECT * FROM import_batches WHERE batch_key=? AND organization_id=?',
                       (batch_key,organization_id)).fetchone()
        if job is None:
            raise HTTPException(404,'Пакет не найден')
        check_store(job['store_id'])
        if job['status']=='applied':
            db.commit()
            return {'applied':True,'already_applied':True,'batch_key':batch_key,'summary':json.loads(job['preview_json'])}
        created=datetime.fromisoformat(job['created_at'])
        if datetime.now(timezone.utc)-created > timedelta(hours=24):
            raise HTTPException(410,'Предварительный просмотр истёк, повторите проверку файла')
        rows=json.loads(job['rows_json'])
        if hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest()!=job['fingerprint']:
            raise HTTPException(409,'Контрольная сумма пакета не совпадает')
        current=_plan(db,job['store_id'],job['kind'],rows)
        if current!=json.loads(job['preview_json']):
            raise HTTPException(409,'Данные магазина изменились после предпросмотра; повторите импорт')
        if current['conflicts']:
            raise HTTPException(409,'Чеки с тем же ID имеют другие суммы или даты: '+', '.join(current['conflicts'][:3]))
        for row in rows:
            if job['kind']=='pos':
                db.execute('INSERT OR IGNORE INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                           (job['store_id'],row['amount_kopeks'],'pos_import',row['occurred_at'],row['external_id']))
            else:
                existing=db.execute('SELECT id FROM inventory WHERE store_id=? AND sku=? COLLATE NOCASE',
                                    (job['store_id'],row['sku'])).fetchone()
                if existing:
                    from backend.commerce import reserved_quantity
                    if row['quantity']<reserved_quantity(db,existing['id']):
                        raise HTTPException(409,'Остаток ниже действующих резервов: '+row['sku'])
                    db.execute('''UPDATE inventory SET sku=?,product=?,size=?,color=?,quantity=?,source=?,updated_at=? WHERE id=?''',
                               (row['sku'],row['product'],row['size'],row['color'],row['quantity'],'reviewed_import',now_iso(),existing['id']))
                else:
                    db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                               (job['store_id'],row['sku'],row['product'],row['size'],row['color'],row['quantity'],'reviewed_import',now_iso()))
        db.execute('UPDATE import_batches SET status=?,applied_at=? WHERE id=?',('applied',now_iso(),job['id']))
        db.commit()
        return {'applied':True,'already_applied':False,'batch_key':batch_key,'summary':current}
    except Exception:
        db.rollback()
        raise
