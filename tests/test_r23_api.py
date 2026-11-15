"""Integration tests run against the real R2.3 FastAPI app and existing migrations."""
import importlib
from datetime import date,timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r23-test-bootstrap-super-secret')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r23-session-secret-with-enough-entropy-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r23-device-secret-with-enough-entropy-123456789')
    import backend.database as database
    import backend.app as api
    importlib.reload(database)
    importlib.reload(api)
    with TestClient(api.app) as c:
        login=c.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r23-test-bootstrap-super-secret'})
        assert login.status_code==200,login.text
        yield c,{'Authorization':'Bearer '+login.json()['token']},database,tmp_path


def make_pilot(site):
    c,headers,db,_=site
    today=date.today()
    payload={'slug':'central','request_id':'r23-test-pilot-idempotency',
        'title':'Проверка критической защиты запуска',
        'hypothesis':'Должен быть обязательный предзапусковой отчёт готовности по филиалу.',
        'metric':'receipts_per_100_entries','source_mode':'manual','budget_kopeks':0,
        'before_start':str(today-timedelta(days=14)),
        'before_end':str(today-timedelta(days=8)),
        'after_start':str(today-timedelta(days=7)),
        'after_end':str(today-timedelta(days=1))}
    response=c.post('/api/admin/r15/pilots',json=payload,headers=headers)
    assert response.status_code==201,response.text
    return response.json()['id']


def test_non_demo_legacy_start_is_closed_and_safe_start_is_the_only_allowed_path(site):
    c,h,db,_=site;pid=make_pilot(site)
    rejected=c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h)
    assert rejected.status_code==409,rejected.text
    assert 'R2.1' in rejected.json()['detail']
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM pilots_r15 WHERE id=?',(pid,)).fetchone()[0]=='draft'
        assert conn.execute('SELECT COUNT(*) FROM assurance_pilot_starts_r21 WHERE pilot_id=?',(pid,)).fetchone()[0]==0
    assert c.post(f'/api/admin/r21/pilots/{pid}/safe-start',headers=h,json={'readiness_id':999999}).status_code in (404,409)


def test_security_owner_only_and_org_isolation(site):
    c,h,db,_=site
    for url in ('/api/admin/r23/integrity','/api/admin/r23/authorization','/api/admin/r23/recovery','/api/admin/r23/release-gate'):
        assert c.get(url).status_code==401
        assert c.get(url,headers=h).status_code==200
    from backend.security import hash_password
    with db.connect() as conn:
        owner=conn.execute("SELECT organization_id FROM users WHERE email='owner@osmanx.local'").fetchone()['organization_id']
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (owner,'r23viewer@osmanx.local',hash_password('r23-test-viewer-super-secret'),'viewer',db.now_iso()))
        uid=conn.execute("SELECT id FROM users WHERE email='r23viewer@osmanx.local'").fetchone()['id']
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,sid));conn.commit()
    auth=c.post('/api/auth/login',json={'email':'r23viewer@osmanx.local','password':'r23-test-viewer-super-secret'})
    assert auth.status_code==200,auth.text
    viewer={'Authorization':'Bearer '+auth.json()['token']}
    assert c.get('/api/admin/r23/integrity',headers=viewer).status_code==403
    assert c.get('/api/admin/r23/recovery',headers=viewer).status_code==403


def test_old_running_pilot_is_flagged_and_incident_requires_independent_closure(site):
    c,h,db,_=site;pid=make_pilot(site)
    with db.connect() as conn:
        conn.execute("UPDATE pilots_r15 SET status='running' WHERE id=?",(pid,));conn.commit()
    report=c.get('/api/admin/r23/integrity',headers=h).json()
    finding=next(x for x in report['findings'] if x['code']=='pilot_missing_start_proof')
    data={'slug':'central','request_id':'r23-security-incident-12345',
          'code':finding['code'],'subject':finding['subject'],
          'owner':'Директор магазина','due_date':str(date.today()+timedelta(days=1))}
    created=c.post('/api/admin/r23/incidents',headers=h,json=data)
    assert created.status_code==201,created.text
    tid=created.json()['id']
    assert c.post('/api/admin/r23/incidents',headers=h,json=data).json()['duplicate'] is True
    assert c.post('/api/admin/r23/incidents',headers=h,json={**data,'owner':'Другой менеджер'}).status_code==409
    assert c.patch(f'/api/admin/r23/incidents/{tid}',headers=h,json={'status':'working','note':'Проверяем причину запуска без заключения'}).status_code==200
    assert c.patch(f'/api/admin/r23/incidents/{tid}',headers=h,json={'status':'verified','note':'Независимо проверили устранение ошибки'}).status_code==409
    from backend.security import hash_password
    with db.connect() as conn:
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (1,'r23second@osmanx.local',hash_password('r23-second-owner-strong-password'),'owner',db.now_iso()))
        conn.execute("UPDATE pilots_r15 SET status='draft' WHERE id=?",(pid,))  # synthetic test cleanup only
        conn.commit()
    login=c.post('/api/auth/login',json={'email':'r23second@osmanx.local','password':'r23-second-owner-strong-password'})
    assert login.status_code==200,login.text
    other={'Authorization':'Bearer '+login.json()['token']}
    approved=c.patch(f'/api/admin/r23/incidents/{tid}',headers=other,json={'status':'verified','note':'Повторная независимая проверка базы выполнена'})
    assert approved.status_code==200,approved.text
    history=c.get(f'/api/admin/r23/incidents/{tid}/history',headers=h).json()['items']
    assert [x['next_status'] for x in history]==['working','verified']


def test_database_backup_and_offline_recovery_rehearsal(site,monkeypatch):
    c,h,db,tmp=site
    from scripts.backup_db import make_backup
    from scripts.r23_recovery_drill import run_drill
    from backend.r23 import recovery_report
    import backend.database as live_db
    folder=tmp/'backups'
    source=live_db.DB_PATH
    saved=make_backup(source,folder,keep=2)
    monkeypatch.setenv('OSMANX_BACKUP_DIR',str(folder))
    before=recovery_report();assert before['backup_status']=='verified' and before['drill_status']=='missing'
    proof=run_drill(saved,record=True)
    assert proof['ok'] and proof['logical_matches'] and proof['table_count']>10
    after=recovery_report()
    assert after['backup_status']=='verified' and after['drill_status']=='verified',after
    assert after['status']=='ready_for_human_review'
    assert c.get('/api/admin/r23/recovery',headers=h).json()['status']=='ready_for_human_review'
    assert source.exists()


def test_csv_export_and_no_false_full_release_approval(site):
    c,h,db,_=site
    resp=c.get('/api/admin/r23/report.csv',headers=h)
    assert resp.status_code==200 and 'text/csv' in resp.headers.get('content-type','')
    result=c.get('/api/admin/r23/release-gate',headers=h).json()
    assert result['status']=='blocked'
    assert any('Резервная копия' in x for x in result['blocking'])
