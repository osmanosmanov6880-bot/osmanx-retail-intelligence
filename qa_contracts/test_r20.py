"""Executable R2.0 contract tests against isolated SQLite and FastAPI.

Fakes are limited to the four pre-existing auth/database helper imports, so these
checks are local module tests, not a claim of full legacy-app CI acceptance.
"""
import importlib
import pathlib
import sqlite3
import sys
import types
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

# Existing modules are represented by minimal typed shims in this isolated delta.
security=types.ModuleType('backend.security')
@dataclass(frozen=True)
class Principal:
    user_id:int
    organization_id:int
    email:str
    role:str


def require_role(p,*roles):
    if p.role not in roles:raise HTTPException(403,'No permission')

def visible_store(db,slug,p):
    r=db.execute('SELECT * FROM stores WHERE slug=? AND organization_id=?',(slug,p.organization_id)).fetchone()
    if not r:raise HTTPException(404,'Not found')
    return r

def check_store_access(db,store_id,p):
    if not db.execute('SELECT id FROM stores WHERE id=? AND organization_id=?',(store_id,p.organization_id)).fetchone():raise HTTPException(404,'Not found')

def audit(db,p,action,subject):
    db.execute('INSERT INTO audit_r20(actor,action,subject) VALUES(?,?,?)',(p.user_id,action,subject))

security.Principal=Principal
security.require_role=require_role
security.visible_store=visible_store
security.check_store_access=check_store_access
security.audit=audit
sys.modules['backend.security']=security

database=types.ModuleType('backend.database')
database.now_iso=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(timespec='seconds')
sys.modules['backend.database']=database
retail=types.ModuleType('backend.retail')
retail.safe_spreadsheet_cell=lambda x: "'"+str(x) if str(x).lstrip().startswith(('=','+','-','@')) else str(x)
sys.modules['backend.retail']=retail

from backend.r20 import CHECKS,ensure_schema,build_router,sha

@pytest.fixture
def site(tmp_path):
    path=tmp_path/'test.sqlite'
    def connect():
        con=sqlite3.connect(path)
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        return con
    with connect() as db:
        db.executescript('''
        CREATE TABLE organizations (id INTEGER PRIMARY KEY);
        CREATE TABLE stores(id INTEGER PRIMARY KEY,organization_id INTEGER NOT NULL REFERENCES organizations(id),slug TEXT UNIQUE,timezone TEXT);
        CREATE TABLE visits(id INTEGER PRIMARY KEY,store_id INTEGER,quantity INTEGER,source TEXT,occurred_at TEXT);
        CREATE TABLE sales(id INTEGER PRIMARY KEY,store_id INTEGER,occurred_at TEXT);
        CREATE TABLE voice_placements_r17(id INTEGER PRIMARY KEY,store_id INTEGER);
        CREATE TABLE voice_opens_r17(id INTEGER PRIMARY KEY,placement_id INTEGER,opened_at TEXT);
        CREATE TABLE voice_responses_r17(id INTEGER PRIMARY KEY,placement_id INTEGER,submitted_at TEXT);
        CREATE TABLE audit_r20(id INTEGER PRIMARY KEY,actor INTEGER,action TEXT,subject TEXT);
        INSERT INTO organizations VALUES(1);INSERT INTO organizations VALUES(2);
        INSERT INTO stores VALUES(1,1,'central','UTC');
        INSERT INTO stores VALUES(2,2,'other','UTC');
        INSERT INTO voice_placements_r17 VALUES(1,1);
        ''')
        ensure_schema(db);db.commit()
    acting={'user':Principal(1,1,'owner@test','owner')}
    def admin():return acting['user']
    def db_conn():
        with connect() as c:yield c
    app=FastAPI()
    app.include_router(build_router(admin,db_conn))
    with TestClient(app) as client:yield client,acting,connect


def start(site):
    client,actor,_=site
    r=client.post('/api/admin/r20/days',json={'slug':'central','business_day':str(date.today())})
    assert r.status_code==201,r.text
    return r.json()['id']


def fill(site,day_id):
    c,a,con=site
    for name in CHECKS:
        r=c.put(f'/api/admin/r20/days/{day_id}/checks',json={'key':name,'outcome':'pass','note':'Подтверждено на открытии смены'})
        assert r.status_code==200,r.text
    for i,(reference,counter) in enumerate([(100,98),(30,29)]):
        r=c.post(f'/api/admin/r20/days/{day_id}/calibrations',json={
            'request_id':f'calibration-id-000{i}','reference_count':reference,'counter_count':counter,
            'method':'Ручной подсчёт против показаний датчика'})
        assert r.status_code==201,r.text
    with con() as db:
        stamp=str(date.today())+'T12:00:00+00:00'
        db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at) VALUES(?,?,?,?)',(1,100,'manual',stamp))
        db.execute('INSERT INTO sales(store_id,occurred_at) VALUES(?,?)',(1,stamp))
        db.execute('INSERT INTO voice_opens_r17(placement_id,opened_at) VALUES(?,?)',(1,stamp))
        db.execute('INSERT INTO voice_responses_r17(placement_id,submitted_at) VALUES(?,?)',(1,stamp))
        db.commit()
    r=c.post(f'/api/admin/r20/days/{day_id}/reconcile',json={'note':'Сверили зарегистрированные посещения, чеки и ответы'})
    assert r.status_code==201,r.text
    assert r.json()['counts']=={'visits':100,'receipts':1,'voice_opens':1,'voice_responses':1}
    handover=c.post(f'/api/admin/r20/days/{day_id}/handovers',json={
        'request_id':'handover-request-00001','shift':'day','issues':'Нет незакрытых технических отказов',
        'actions':'Продолжить наблюдение в следующей смене'})
    assert handover.status_code==201,handover.text
    return handover.json()['id']


def test_day_and_scope(site):
    c,actor,_=site
    day=start(site)
    assert c.post('/api/admin/r20/days',json={'slug':'central','business_day':str(date.today())}).json()['duplicate']
    assert c.get(f'/api/admin/r20/days/{day}').status_code==200
    actor['user']=Principal(3,2,'other@test','owner')
    assert c.get(f'/api/admin/r20/days/{day}').status_code==404
    assert c.get('/api/admin/r20/days?slug=central').status_code==404


def test_calibration_and_idempotency(site):
    c,actor,_=site;day=start(site)
    data={'request_id':'calibration-id-12345','reference_count':100,'counter_count':109,
          'method':'Сотрудник посчитал вручную за двадцать минут'}
    r=c.post(f'/api/admin/r20/days/{day}/calibrations',json=data)
    assert r.status_code==201 and r.json()['within_tolerance']
    assert r.json()['error_pct']==9
    assert c.post(f'/api/admin/r20/days/{day}/calibrations',json=data).json()['duplicate']
    assert c.post(f'/api/admin/r20/days/{day}/calibrations',json={**data,'counter_count':85}).status_code==409
    assert c.post(f'/api/admin/r20/days/{day}/calibrations',json={**data,'request_id':'another-calibration-01',
          'reference_count':0,'counter_count':0}).json()['within_tolerance'] is False


def test_gate_requires_checks_two_calibrations_and_handover(site):
    c,actor,_=site;day=start(site)
    assert c.post(f'/api/admin/r20/days/{day}/review-request').status_code==409
    handover=fill(site,day)
    assert c.post(f'/api/admin/r20/days/{day}/review-request').status_code==409
    assert c.post(f'/api/admin/r20/handovers/{handover}/ack',json={'note':'Другой сотрудник подтвердил смену'}).status_code==409
    actor['user']=Principal(2,1,'manager@test','manager')
    assert c.post(f'/api/admin/r20/handovers/{handover}/ack',json={'note':'Подтверждаю передачу смены и журнал'}).status_code==200
    assert c.post(f'/api/admin/r20/days/{day}/review-request').status_code==200
    assert c.put(f'/api/admin/r20/days/{day}/checks',json={'key':'tablet','outcome':'fail','note':'Экран перестал работать'}).status_code==409
    assert c.post(f'/api/admin/r20/days/{day}/review',json={'decision':'reviewed','note':'Проверка успешно завершена'}).status_code==403
    actor['user']=Principal(1,1,'owner@test','owner')
    assert c.post(f'/api/admin/r20/days/{day}/review',json={'decision':'reviewed','note':'Другой сотрудник проверил смену'}).status_code==200
    snapshot=c.get(f'/api/admin/r20/days/{day}/snapshot')
    assert snapshot.status_code==200 and len(snapshot.json()['sha256'])==64
    with site[2]() as db:
        db.execute('UPDATE readiness_reviews_r20 SET payload_json=? WHERE readiness_id=?',('tampered',day));db.commit()
    assert c.get(f'/api/admin/r20/days/{day}/snapshot').status_code==409


def test_csv_protected_records_and_permissions(site):
    c,actor,_=site;day=start(site)
    c.put(f'/api/admin/r20/days/{day}/checks',json={'key':'tablet','outcome':'pass',
        'note':'=HYPERLINK("https://evil.example")'})
    csv=c.get(f'/api/admin/r20/days/{day}/report.csv')
    assert csv.status_code==200 and "'=HYPERLINK" in csv.text
    actor['user']=Principal(2,1,'viewer@test','viewer')
    assert c.put(f'/api/admin/r20/days/{day}/checks',json={'key':'privacy','outcome':'pass',
          'note':'Прочитана политика хранения'}).status_code==403
    assert c.get(f'/api/admin/r20/days/{day}').status_code==200


def test_quality_gate_catches_failed_items(site):
    c,actor,_=site;day=start(site)
    for name in CHECKS:
        outcome='fail' if name=='notice' else 'pass'
        c.put(f'/api/admin/r20/days/{day}/checks',json={'key':name,'outcome':outcome,'note':'Результат проверки задокументирован'})
    report=c.get(f'/api/admin/r20/days/{day}').json()
    assert any('Проблема' in x for x in report['issues'])
    assert not report['reviewable']
