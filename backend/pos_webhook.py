"""Signed point-of-sale ingestion with atomic, idempotent receipt batches.

This is a documented vendor-neutral webhook contract, not a direct 1C driver.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from backend.database import now_iso
from backend.security import utc_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS pos_sources (
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 name TEXT NOT NULL,
 generation INTEGER NOT NULL DEFAULT 1,
 active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pos_sources_store ON pos_sources(store_id);
CREATE TABLE IF NOT EXISTS pos_events (
 id INTEGER PRIMARY KEY,
 source_id INTEGER NOT NULL REFERENCES pos_sources(id),
 external_id TEXT NOT NULL,
 content_hash TEXT NOT NULL,
 received_at TEXT NOT NULL,
 UNIQUE(source_id,external_id)
);
CREATE INDEX IF NOT EXISTS idx_pos_events_source_date ON pos_events(source_id,received_at);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def derive_secret(source: sqlite3.Row, master: str) -> str:
    if len(master) < 32:
        raise HTTPException(503, 'POS master signing secret is not configured')
    tag = f"osmanx-pos-v1:{source['public_id']}:{source['generation']}:{source['store_id']}"
    return hmac.new(master.encode(),tag.encode(),hashlib.sha256).hexdigest()


def new_source(db: sqlite3.Connection, org_id: int, store_id: int, name: str, master: str) -> dict:
    public_id = 'pos_' + secrets.token_hex(12)
    db.execute('INSERT INTO pos_sources(public_id,organization_id,store_id,name,created_at) VALUES(?,?,?,?,?)',
               (public_id, org_id, store_id, name.strip(), now_iso()))
    row=db.execute('SELECT * FROM pos_sources WHERE public_id=?', (public_id,)).fetchone()
    return {'source_id':public_id,'secret':derive_secret(row,master),'generation':1}


def verify_source(db: sqlite3.Connection, public_id: str | None, signed_timestamp: str | None,
                  signature: str | None, raw: bytes, master: str) -> sqlite3.Row:
    if not public_id or not signed_timestamp or not signature:
        raise HTTPException(401, 'Signed POS credentials required')
    row=db.execute('SELECT * FROM pos_sources WHERE public_id=? AND active=1',(public_id,)).fetchone()
    if not row:
        raise HTTPException(401, 'Unknown POS source')
    try:stamp=int(signed_timestamp)
    except (ValueError,TypeError):raise HTTPException(401,'Bad signed timestamp') from None
    if abs(time.time()-stamp)>300:
        raise HTTPException(401, 'Expired POS signature')
    message=signed_timestamp.encode()+b'\n'+public_id.encode()+b'\n'+raw
    expected=hmac.new(derive_secret(row,master).encode(),message,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):
        raise HTTPException(401, 'Invalid POS signature')
    return row


def normalize_receipt(receipt: dict) -> dict:
    if not isinstance(receipt,dict) or set(receipt) != {'external_id','amount_rub','occurred_at'}:
        raise HTTPException(422,'Receipt needs external_id, amount_rub and occurred_at')
    external_id=receipt['external_id']
    if not isinstance(external_id,str) or not 4<=len(external_id)<=120:
        raise HTTPException(422,'Invalid receipt external_id')
    try:
        number=Decimal(str(receipt['amount_rub']))
        if not number.is_finite() or number<0 or number>Decimal('20000000'):
            raise InvalidOperation()
        if number.as_tuple().exponent < -2:
            raise HTTPException(422,'Receipt amount must use at most 2 decimal places')
    except (InvalidOperation,ValueError):
        raise HTTPException(422,'Invalid receipt amount') from None
    try:when=datetime.fromisoformat(receipt['occurred_at'].replace('Z','+00:00'))
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(422,'Invalid receipt timestamp') from None
    occurred_at=utc_iso(when)
    if abs((datetime.now(timezone.utc)-datetime.fromisoformat(occurred_at)).total_seconds())>86400*31:
        raise HTTPException(422,'Receipt timestamp is outside 31-day range')
    return {'external_id':external_id,'amount_kopeks':int(number*100),'occurred_at':occurred_at}


def apply_receipts(db: sqlite3.Connection, source: sqlite3.Row, raw: bytes) -> dict:
    try: payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError):raise HTTPException(422,'Invalid POS JSON') from None
    if not isinstance(payload,dict) or set(payload) != {'receipts'} or not isinstance(payload['receipts'],list) or not 1<=len(payload['receipts'])<=200:
        raise HTTPException(422,'POS batch needs 1 to 200 receipts')
    records=[normalize_receipt(item) for item in payload['receipts']]
    if len({item['external_id'] for item in records}) != len(records):
        raise HTTPException(422,'Duplicate receipt ids within batch')
    planned=[]; duplicates=0
    db.execute('BEGIN IMMEDIATE')
    try:
        for item in records:
            fingerprint=hashlib.sha256(json.dumps(item,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            old=db.execute('SELECT content_hash FROM pos_events WHERE source_id=? AND external_id=?',
                           (source['id'],item['external_id'])).fetchone()
            if old:
                if old['content_hash'] != fingerprint:
                    raise HTTPException(409,'Conflicting receipt id')
                duplicates+=1
            else:planned.append((item,fingerprint))
        for item,fingerprint in planned:
            db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                       (source['store_id'],item['amount_kopeks'],'signed_pos',item['occurred_at'],
                        source['public_id']+':'+item['external_id']))
            db.execute('INSERT INTO pos_events(source_id,external_id,content_hash,received_at) VALUES(?,?,?,?)',
                       (source['id'],item['external_id'],fingerprint,now_iso()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'added':len(planned),'duplicates':duplicates,'total':len(records)}
