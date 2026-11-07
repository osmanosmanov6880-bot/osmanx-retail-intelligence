"""Paired public survey terminals: optional per-store access tokens.

Tokens are 256-bit random values. Only hashes are stored, and the browser
receives them through a URL fragment (which is not sent in HTTP requests).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import HTTPException

from backend.database import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS kiosk_policies (
 store_id INTEGER PRIMARY KEY REFERENCES stores(id) ON DELETE CASCADE,
 token_hash TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 generation INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL
);
"""


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)


def policy(db: sqlite3.Connection, store_id: int) -> dict:
    row = db.execute('SELECT enabled,generation,updated_at FROM kiosk_policies WHERE store_id=?',
                     (store_id,)).fetchone()
    return dict(row) if row else {'enabled': 0, 'generation': 0, 'updated_at': None}


def rotate(db: sqlite3.Connection, store_id: int) -> tuple[str,int]:
    token = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    db.execute('''INSERT INTO kiosk_policies(store_id,token_hash,enabled,generation,updated_at)
        VALUES(?,?,1,1,?) ON CONFLICT(store_id) DO UPDATE SET token_hash=excluded.token_hash,
        enabled=1,generation=kiosk_policies.generation+1,updated_at=excluded.updated_at''',
        (store_id, hashed, now_iso()))
    return token, policy(db, store_id)['generation']


def disable(db: sqlite3.Connection, store_id: int) -> None:
    db.execute('DELETE FROM kiosk_policies WHERE store_id=?', (store_id,))


def verify(db: sqlite3.Connection, store_id: int, presented: str | None) -> None:
    row = db.execute('SELECT token_hash,enabled FROM kiosk_policies WHERE store_id=?',
                     (store_id,)).fetchone()
    if row is None or not row['enabled']:
        return
    if not presented or len(presented) > 256:
        raise HTTPException(401, 'Terminal access token required')
    hashed = hashlib.sha256(presented.encode()).hexdigest()
    if not hmac.compare_digest(hashed, row['token_hash']):
        raise HTTPException(401, 'Terminal access token invalid')
