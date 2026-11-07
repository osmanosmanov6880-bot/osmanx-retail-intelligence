"""Organizational isolation, role permissions and least-privilege device identities.

Authentication is server-side verified on every request. No public route may
trust a client-supplied organization or store identifier for authorization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException

from backend.database import now_iso

ROLES = ("owner", "manager", "analyst", "viewer")
AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
 id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 email TEXT NOT NULL UNIQUE COLLATE NOCASE, full_name TEXT NOT NULL DEFAULT '',
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner','manager','analyst','viewer')),
 active INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_store_access (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 store_id INTEGER NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,store_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
 actor_user_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 subject TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_org_date ON audit_events(organization_id,created_at);
CREATE TABLE IF NOT EXISTS devices (
 id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE,
 organization_id INTEGER NOT NULL REFERENCES organizations(id),
 store_id INTEGER NOT NULL REFERENCES stores(id),
 name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('traffic','zones')),
 generation INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_store ON devices(store_id);
CREATE TABLE IF NOT EXISTS device_events (
 id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id),
 kind TEXT NOT NULL, external_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 received_at TEXT NOT NULL, UNIQUE(device_id,kind,external_id)
);
"""

@dataclass(frozen=True)
class Principal:
    user_id: int
    organization_id: int
    email: str
    role: Literal['owner','manager','analyst','viewer']
    demo: bool = False


def ensure_security_schema(db: sqlite3.Connection, *, demo: bool, bootstrap_password: str,
                           bootstrap_email: str) -> None:
    """Idempotent R0.3 migration: all existing R0.2 stores join the legacy org."""
    db.executescript(AUTH_SCHEMA)
    columns = {row['name'] for row in db.execute('PRAGMA table_info(stores)')}
    if 'organization_id' not in columns:
        db.execute('ALTER TABLE stores ADD COLUMN organization_id INTEGER REFERENCES organizations(id)')
    if 'traffic_mode' not in columns:
        db.execute("ALTER TABLE stores ADD COLUMN traffic_mode TEXT NOT NULL DEFAULT 'combined'")
    if 'reward_daily_limit' not in columns:
        db.execute('ALTER TABLE stores ADD COLUMN reward_daily_limit INTEGER NOT NULL DEFAULT 20')
    if 'survey_retention_days' not in columns:
        db.execute('ALTER TABLE stores ADD COLUMN survey_retention_days INTEGER NOT NULL DEFAULT 90')
    db.execute('INSERT OR IGNORE INTO organizations(id,slug,name,created_at) VALUES(1,?,?,?)',
               ('legacy', 'OSMANX · основной аккаунт', now_iso()))
    db.execute('UPDATE stores SET organization_id=1 WHERE organization_id IS NULL')
    if not demo and bootstrap_password:
        email = bootstrap_email.strip().lower()
        if not db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
            db.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                       (1, email, 'Владелец', hash_password(bootstrap_password), 'owner', now_iso()))
    db.commit()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError('Password must have at least 12 characters')
    salt = secrets.token_bytes(16)
    iterations = 220_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'


def check_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt, digest = encoded.split('$')
        if scheme != 'pbkdf2_sha256' or not 100_000 <= int(iterations) <= 1_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def issue_session(user: sqlite3.Row, secret: str) -> str:
    data = {'uid': user['id'], 'ver': user['session_version'], 'exp': int(time.time()) + 8*3600,
            'nonce': secrets.token_hex(8)}
    encoded = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip('=')
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def verify_session(token: str, secret: str, db: sqlite3.Connection) -> Principal:
    try:
        encoded, signature = token.split('.', 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError('signature')
        data = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if not isinstance(data.get('uid'), int) or not isinstance(data.get('exp'), int) or data['exp'] <= time.time():
            raise ValueError('expired')
        user = db.execute('SELECT * FROM users WHERE id=? AND active=1', (data['uid'],)).fetchone()
        if user is None or data.get('ver') != user['session_version']:
            raise ValueError('revoked')
        return Principal(user['id'], user['organization_id'], user['email'], user['role'])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, 'Сессия недействительна или истекла') from None


def visible_store(db: sqlite3.Connection, slug: str, principal: Principal) -> sqlite3.Row:
    store = db.execute('SELECT * FROM stores WHERE slug=? AND organization_id=?',
                       (slug, principal.organization_id)).fetchone()
    if not store:
        raise HTTPException(404, 'Магазин не найден')
    check_store_access(db, store['id'], principal)
    return store


def check_store_access(db: sqlite3.Connection, store_id: int, principal: Principal) -> None:
    if principal.role == 'owner' or principal.demo:
        return
    if not db.execute('SELECT 1 FROM user_store_access WHERE store_id=? AND user_id=?',
                      (store_id, principal.user_id)).fetchone():
        raise HTTPException(404, 'Магазин не найден')


def visible_object(db: sqlite3.Connection, table: str, object_id: int, principal: Principal) -> sqlite3.Row:
    if table not in ('demand', 'experiments'):
        raise ValueError('unsupported resource')
    row = db.execute(f'''SELECT t.* FROM {table} t JOIN stores s ON s.id=t.store_id
         WHERE t.id=? AND s.organization_id=?''', (object_id, principal.organization_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Запись не найдена')
    check_store_access(db, row['store_id'], principal)
    return row


def require_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(403, 'Недостаточно прав для этой операции')


def audit(db: sqlite3.Connection, principal: Principal, action: str, subject: str) -> None:
    db.execute('INSERT INTO audit_events(organization_id,actor_user_id,action,subject,created_at) VALUES(?,?,?,?,?)',
               (principal.organization_id, None if principal.demo else principal.user_id, action, subject[:200], now_iso()))


def device_secret(public_id: str, generation: int, store_id: int, master: str) -> str:
    if len(master) < 32:
        raise HTTPException(503, 'Не настроен OSMANX_DEVICE_MASTER_SECRET')
    message = f'osmanx-device-v1:{public_id}:{generation}:{store_id}'.encode()
    return hmac.new(master.encode(), message, hashlib.sha256).hexdigest()


def verify_device_signature(db: sqlite3.Connection, *, public_id: str, signature: str,
                            signed_timestamp: str, raw_body: bytes, kind: str, master: str) -> sqlite3.Row:
    device = db.execute('SELECT * FROM devices WHERE public_id=? AND active=1 AND kind=?', (public_id,kind)).fetchone()
    if device is None:
        raise HTTPException(401, 'Неизвестное устройство')
    try:
        stamp = int(signed_timestamp)
    except (ValueError, TypeError):
        raise HTTPException(401, 'Недействительная временная метка') from None
    if abs(time.time()-stamp) > 300:
        raise HTTPException(401, 'Подпись устарела или часы устройства не синхронизированы')
    secret = device_secret(device['public_id'], device['generation'], device['store_id'], master)
    message = signed_timestamp.encode()+b'\n'+public_id.encode()+b'\n'+raw_body
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, 'Неверная подпись устройства')
    return device


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise HTTPException(422, 'Передайте дату с часовым поясом')
    return value.astimezone(timezone.utc).isoformat(timespec='seconds')
