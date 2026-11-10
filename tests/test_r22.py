"""R2.2 standalone API acceptance using actual R2.0 schema and isolated SQLite.

Prior auth/database primitives are stubbed exactly as in tests/test_r20.py.
Production app CI must independently test the complete checkout.
"""
import hashlib
import importlib
import json
import pathlib
import sys
from datetime import datetime,timezone,timedelta

import pytest
from fastapi import HTTPException

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'qa_contracts'))
from test_r20 import site as base_site, Principal, sha as readiness_sha
from backend.r22 import build_router, ensure_schema, _readiness

@pytest.fixture
def site(base_site):
    c,actor,connect=base_site
    with connect() as db:
        db.execute("ALTER TABLE stores ADD COLUMN name TEXT DEFAULT 'Магазин'")
        db.execute("INSERT INTO stores(id,organization_id,slug,timezone,name) VALUES(3,1,'north','UTC','Северный магазин')")
        db.execute("CREATE TABLE field_incidents_r19(id INTEGER PRIMARY KEY,store_id INTEGER,signal TEXT,status TEXT)")
        ensure_schema(db)
        db.commit()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from test_r20 import require_role
    def adm():return actor['user']
    def dep():
        with connect() as db:yield db
    app=FastAPI();app.include_router(build_router(adm,dep))
    with TestClient(app) as cli:yield cli,actor,connect


def approve_day(site,store=1,age_days=0,tamper=False):
    _,_,connect=site
    with connect() as db:
        stamp=(datetime.now(timezone.utc)-timedelta(days=age_days)).isoformat(timespec='seconds')
        day=(datetime.now(timezone.utc)-timedelta(days=age_days)).date().isoformat()
        rid=db.execute('''INSERT INTO readiness_days_r20(organization_id,store_id,business_day,status,created_at,updated_at)
          VALUES(?,?,?,?,?,?)''',(1,store,day,'reviewed',stamp,stamp)).lastrowid
        db.execute('UPDATE readiness_days_r20 SET requested_by=1,reviewed_by=2 WHERE id=?',(rid,))
        payload=json.dumps({'day':{'id':rid},'issues':[],'decision':'reviewed'},ensure_ascii=False,sort_keys=True)
        digest=hashlib.sha256(payload.encode()).hexdigest()
        db.execute('INSERT INTO readiness_reviews_r20(readiness_id,payload_json,payload_sha,reviewer_id,reviewed_at) VALUES(?,?,?,?,?)',
                   (rid,'corrupted' if tamper else payload,digest,2,stamp))
        db.commit();return rid


def wave(c,req='wave-request-abc0001'):
    result=c.post('/api/admin/r22/waves',json={'request_id':req,'title':'Поэтапное подключение филиалов',
       'objective':'Проверить готовность опросов в двух филиалах, без автоматического запуска',
       'budget_kopeks':250000})
    assert result.status_code==201,result.text
    return result.json()['id']


def add(c,w,slug='central',phase=1):
    return c.post(f'/api/admin/r22/waves/{w}/sites',json={'slug':slug,'phase':phase,'notes':'Проверенный филиал'})


def approve(c,actor,w):
    assert c.post(f'/api/admin/r22/waves/{w}/request-review').status_code==200
    actor['user']=Principal(2,1,'second@org.test','owner')
    return c.post(f'/api/admin/r22/waves/{w}/approve',json={'note':'Разрешаю только документальную первую волну'})


def test_create_idempotency_conflict_and_org(site):
    c,actor,con=site;w=wave(c)
    again=c.post('/api/admin/r22/waves',json={'request_id':'wave-request-abc0001','title':'Поэтапное подключение филиалов',
       'objective':'Проверить готовность опросов в двух филиалах, без автоматического запуска','budget_kopeks':250000})
    assert again.status_code==201 and again.json()['duplicate']
    assert c.post('/api/admin/r22/waves',json={'request_id':'wave-request-abc0001','title':'Другой смысл волны','objective':'Совсем иной согласованный проект, без автоматического запуска','budget_kopeks':1}).status_code==409
    actor['user']=Principal(8,2,'other@org.test','owner')
    assert c.get(f'/api/admin/r22/waves/{w}').status_code==404
    assert c.get('/api/admin/r22/portfolio').json()['total']==0


def test_no_ready_site_cannot_approve_and_second_reviewer_required(site):
    c,actor,con=site;w=wave(c);assert add(c,w).status_code==201
    assert c.post(f'/api/admin/r22/waves/{w}/request-review').status_code==200
    assert c.post(f'/api/admin/r22/waves/{w}/approve',json={'note':'Нельзя самому утверждать запуск'}).status_code==409
    actor['user']=Principal(2,1,'other@org.test','owner')
    assert c.post(f'/api/admin/r22/waves/{w}/approve',json={'note':'Проверка не завершена физически'}).status_code==409
    assert c.get(f'/api/admin/r22/waves/{w}').json()['blocking']


def test_successful_review_stage_transition_and_immutable_proof(site):
    c,actor,con=site;approve_day(site,1);approve_day(site,3)
    w=wave(c);assert add(c,w).status_code==201;assert add(c,w,'north',2).status_code==201
    result=approve(c,actor,w)
    assert result.status_code==200,result.text
    assert result.json()['state']=='active'
    step=c.post(f'/api/admin/r22/waves/{w}/advance',json={'note':'Контроль первой точки завершён документально'})
    assert step.status_code==200,step.text
    assert step.json()['stage']==2
    final=c.post(f'/api/admin/r22/waves/{w}/advance',json={'note':'Проверены филиалы второй волны, разрешение оформлено'})
    assert final.status_code==200,final.text
    assert final.json()['state']=='completed'
    details=c.get(f'/api/admin/r22/waves/{w}').json()
    assert len(details['stage_proofs'])==2 and all(x['intact'] for x in details['stage_proofs'])
    assert c.post(f'/api/admin/r22/waves/{w}/advance',json={'note':'Повторить не получится'}).status_code==409


def test_evidence_digest_tamper_and_expired_readiness_block(site):
    c,actor,con=site;rid=approve_day(site,1,tamper=True)
    w=wave(c);assert add(c,w).status_code==201
    failed=approve(c,actor,w)
    assert failed.status_code==409
    with con() as db:
        db.execute('UPDATE readiness_reviews_r20 SET payload_json=? WHERE readiness_id=?',
                   (json.dumps({'day':{'id':rid},'decision':'reviewed','issues':[]},sort_keys=True),rid));db.commit()
    # Late or old review remains blocked even with valid SHA.
    actor['user']=Principal(2,1,'other@org.test','owner')
    with con() as db:
        db.execute('UPDATE readiness_reviews_r20 SET reviewed_at=? WHERE readiness_id=?',
                   ((datetime.now(timezone.utc)-timedelta(days=10)).isoformat(),rid));db.commit()
    assert c.post(f'/api/admin/r22/waves/{w}/approve',json={'note':'Просроченное подтверждение нельзя принять'}).status_code==409


def test_incident_blocks_and_pause_resume(site):
    c,actor,con=site;approve_day(site,1);w=wave(c);add(c,w)
    assert approve(c,actor,w).status_code==200
    with con() as db:
        db.execute("INSERT INTO field_incidents_r19(store_id,signal,status) VALUES(1,'offline','open')");db.commit()
    assert c.post(f'/api/admin/r22/waves/{w}/advance',json={'note':'Пропустить открытый инцидент нельзя'}).status_code==409
    assert c.post(f'/api/admin/r22/waves/{w}/pause',json={'note':'Остановлено до устранения сбоев терминала'}).status_code==200
    assert c.post(f'/api/admin/r22/waves/{w}/resume',json={'note':'Нельзя игнорировать инцидент'}).status_code==409
    with con() as db:
        db.execute("UPDATE field_incidents_r19 SET status='resolved'");db.commit()
    assert c.post(f'/api/admin/r22/waves/{w}/resume',json={'note':'Инцидент документально закрыт'}).status_code==200


def test_csv_protection_and_role_permissions(site):
    c,actor,con=site;w=wave(c,req='second-wave-00000001')
    with con() as db:
        db.execute('UPDATE rollout_waves_r22 SET title=? WHERE id=?',('=HYPERLINK("bad")',w));db.commit()
    csv=c.get('/api/admin/r22/portfolio.csv')
    assert csv.status_code==200 and "'=HYPERLINK" in csv.text
    actor['user']=Principal(3,1,'viewer@org.test','viewer')
    assert c.get('/api/admin/r22/waves').status_code==200
    assert c.post('/api/admin/r22/waves',json={'request_id':'denied-request-000001','title':'Недопустимое создание','objective':'Проверка, что viewer не может создавать волны','budget_kopeks':0}).status_code==403
    assert c.post(f'/api/admin/r22/waves/{w}/pause',json={'note':'Не разрешаем менять без доступа'}).status_code==403
