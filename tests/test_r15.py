"""R1.5 Pilot Studio: business math, immutable snapshots, organization isolation.

The fixture deliberately uses a clean SQLite database; no sample data may be
passed off as a real store result. Unit tests create explicit synthetic records.
"""
import hashlib
import importlib
import json
from datetime import date, timedelta, datetime, timezone

import pytest
from fastapi.testclient import TestClient


def dates(days=7,offset=0):
    today=date.today()+timedelta(days=offset)
    return dict(before_start=str(today-timedelta(days=2*days)),
                before_end=str(today-timedelta(days=days+1)),
                after_start=str(today-timedelta(days=days)),
                after_end=str(today-timedelta(days=1)))


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as database
    import backend.app as module
    importlib.reload(database);importlib.reload(module)
    with TestClient(module.app) as client:
        login=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert login.status_code==200,login.text
        yield client, {'Authorization':'Bearer '+login.json()['token']},database


def pilot(client,headers,**override):
    p={'slug':'central','request_id':'pilot-request-123456','title':'Контроль отсутствующих размеров',
       'hypothesis':'Если учитывать отсутствующие размеры, число чеков на 100 входов может измениться.',
       'metric':'receipts_per_100_entries','source_mode':'manual','budget_kopeks':100000,**dates()}
    p.update(override)
    return client.post('/api/admin/r15/pilots',json=p,headers=headers),p


def insert_observations(db,day,visits=100,receipts=20,surveys=10,source='manual'):
    stamp=day.isoformat()+'T12:00:00+00:00'
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        if visits:conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                               (store,visits,source,stamp,f'qa-traffic-{day}-{source}'))
        for i in range(receipts):conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                 (store,500000,'qa-pos',stamp,f'qa-receipt-{day}-{i}'))
        for _ in range(surveys):conn.execute('INSERT INTO surveys(store_id,rating,purchased,reason,liked,suggestion,created_at) VALUES(?,?,?,?,?,?,?)',
                 (store,5,1,'','','',stamp))
        conn.commit()


def action(client,headers,pid,**kwargs):
    body={'request_id':'pilot-action-123456','category':'assortment',
          'description':'Изменили процесс записи отсутствующих размеров',
          'cost_kopeks':45000,'evidence':'act-001',**kwargs}
    return client.post(f'/api/admin/r15/pilots/{pid}/actions',json=body,headers=headers)


def test_new_routes_auth_and_scope(site):
    c,headers,_=site
    assert c.get('/api/admin/r15/pilots').status_code==401
    assert c.post('/api/admin/r15/pilots',json={}).status_code==401
    x,_=pilot(c,headers);assert x.status_code==201,x.text
    pid=x.json()['id']
    assert c.get(f'/api/admin/r15/pilots/{pid}').status_code==401
    assert c.get(f'/api/admin/r15/pilots/{pid}',headers=headers).status_code==200
    assert c.get('/api/admin/r15/pilots/984433',headers=headers).status_code==404
    assert c.get('/api/admin/r15/pilots?slug=no-such-store',headers=headers).status_code==404


def test_create_idempotency_and_frozen_spec(site):
    c,h,_=site;first,p=pilot(c,h);assert first.status_code==201,first.text
    second=c.post('/api/admin/r15/pilots',json=p,headers=h);assert second.json()=={'id':first.json()['id'],'duplicate':True}
    conflict=c.post('/api/admin/r15/pilots',json={**p,'title':'Совершенно другой эксперимент'},headers=h)
    assert conflict.status_code==409
    wrong=c.post('/api/admin/r15/pilots',json={**p,'request_id':'new-key-for-short-window','after_end':p['after_start']},headers=h)
    assert wrong.status_code==422
    overlap=c.post('/api/admin/r15/pilots',json={**p,'request_id':'new-key-for-overlap','after_start':p['before_end']},headers=h)
    assert overlap.status_code==422


def test_pilot_source_checks_and_started_transitions(site):
    c,h,_=site;x,_=pilot(c,h);pid=x.json()['id']
    assert action(c,h,pid).status_code==409
    saved=c.post(f'/api/admin/r15/pilots/{pid}/sources',json={'category':'traffic','status':'checked','note':'Ручная проверка в течение двух часов'},headers=h)
    assert saved.status_code==200,saved.text
    assert 'не равна независимому' in saved.json()['note']
    assert c.post(f'/api/admin/r15/pilots/{pid}/sources',json={'category':'pos','status':'checked','note':'коротко'},headers=h).status_code==422
    assert c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h).json()['status']=='running'
    assert c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h).status_code==409
    assert len(c.get(f'/api/admin/r15/pilots/{pid}',headers=h).json()['attestations'])==1


def test_daily_metrics_calculated_from_real_rows_and_correct_units(site):
    c,h,db=site;x,_=pilot(c,h);pid=x.json()['id']
    before=date.today()-timedelta(days=14);after=date.today()-timedelta(days=7)
    insert_observations(db,before,visits=100,receipts=20,surveys=6)
    insert_observations(db,after,visits=100,receipts=30,surveys=12)
    result=c.get(f'/api/admin/r15/pilots/{pid}/preview',headers=h);assert result.status_code==200,result.text
    data=result.json();assert data['baseline']['visits']==100 and data['baseline']['receipts']==20
    assert data['intervention']['visits']==100 and data['intervention']['receipts']==30
    assert data['baseline']['revenue_kopeks']==10000000
    assert data['baseline']['metric_value']==20 and data['intervention']['metric_value']==30
    assert data['delta']==10 and data['status']=='inconclusive'
    assert any('день' in w for w in data['warnings'])
    assert all('raw_id' not in line for line in data['daily'])


def test_missing_traffic_never_yields_fake_zero_conversions(site):
    c,h,db=site;response,_=pilot(c,h);pid=response.json()['id']
    insert_observations(db,date.today()-timedelta(days=6),visits=0,receipts=2,surveys=0)
    data=c.get(f'/api/admin/r15/pilots/{pid}/preview',headers=h).json()
    assert data['intervention']['metric_value'] is None
    assert data['delta'] is None
    assert any('не определена' in w for w in data['warnings'])


def test_source_mode_manual_not_counted_as_sensor(site):
    c,h,db=site;x,_=pilot(c,h,source_mode='sensor');pid=x.json()['id']
    d=date.today()-timedelta(days=6)
    insert_observations(db,d,visits=100,receipts=5,source='manual')
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                     (store,80,'calibrated_sensor',d.isoformat()+'T14:00:00+00:00','source-test-1'))
        conn.commit()
    data=c.get(f'/api/admin/r15/pilots/{pid}/preview',headers=h).json()
    assert data['intervention']['visits']==80
    assert data['intervention']['visit_sources']==['calibrated_sensor']


def test_action_idempotency_conflict_and_costs(site):
    c,h,_=site;x,_=pilot(c,h);pid=x.json()['id']
    c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h)
    first=action(c,h,pid);assert first.status_code==201,first.text
    assert action(c,h,pid).json()['duplicate']
    assert action(c,h,pid,cost_kopeks=60000).status_code==409
    data=c.get(f'/api/admin/r15/pilots/{pid}/preview',headers=h).json()
    assert data['actual_logged_cost_kopeks']==45000
    assert len(data['actions'])==1


def test_close_prevents_early_data_approval(site):
    c,h,_=site
    x,_=pilot(c,h,request_id='valid-future-window',**{
        'before_start':str(date.today()-timedelta(days=14)),
        'before_end':str(date.today()-timedelta(days=8)),
        'after_start':str(date.today()-timedelta(days=6)),
        'after_end':str(date.today())})
    assert x.status_code==201,x.text
    pid=x.json()['id'];c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h);action(c,h,pid)
    res=c.post(f'/api/admin/r15/pilots/{pid}/close',json={'decision':'completed','note':'Проверка закончена, результаты фиксируем'},headers=h)
    assert res.status_code==409
    assert 'не завершён' in res.json()['detail']


def test_close_snapshot_sha_and_csv_immutable(site):
    c,h,db=site;x,_=pilot(c,h);pid=x.json()['id'];c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h)
    assert c.post(f'/api/admin/r15/pilots/{pid}/close',json={'decision':'completed','note':'Записываю все результаты и ограничения'},headers=h).status_code==409
    assert action(c,h,pid,description='Добавили проверку размеров; =IMPORT("unsafe")').status_code==201
    closed=c.post(f'/api/admin/r15/pilots/{pid}/close',json={'decision':'completed','note':'Измерили данные и честно указали ограничения'},headers=h)
    assert closed.status_code==200,closed.text
    seal=closed.json()['sha256'];assert len(seal)==64
    payload=c.get(f'/api/admin/r15/pilots/{pid}/snapshot',headers=h).json()
    assert payload['sha256']==seal and payload['payload']['result']['status']=='inconclusive'
    csv=c.get(f'/api/admin/r15/pilots/{pid}/snapshot.csv',headers=h)
    assert csv.status_code==200 and 'text/csv' in csv.headers['content-type']
    assert 'Методика' in csv.content.decode('utf-8-sig')
    assert action(c,h,pid,request_id='different-after-close').status_code==409
    assert c.post(f'/api/admin/r15/pilots/{pid}/sources',headers=h,json={'category':'pos','status':'checked','note':'Проверка после завершения пилота'}).status_code==409
    assert c.post(f'/api/admin/r15/pilots/{pid}/close',json={'decision':'completed','note':'Повторное завершение не должно сработать'},headers=h).status_code==409
    with db.connect() as conn:
        conn.execute('UPDATE pilot_snapshots_r15 SET payload_json=? WHERE pilot_id=?',('tampered',pid));conn.commit()
    assert c.get(f'/api/admin/r15/pilots/{pid}/snapshot',headers=h).status_code==409


def test_cancel_even_if_followup_not_finished(site):
    c,h,_=site;x,_=pilot(c,h);pid=x.json()['id']
    c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h)
    result=c.post(f'/api/admin/r15/pilots/{pid}/close',json={'decision':'cancelled','note':'Пилот прекращён по решению руководителя'},headers=h)
    assert result.status_code==200 and result.json()['status']=='cancelled'


def test_company_isolation_for_pilots(site):
    c,h,db=site;x,_=pilot(c,h);pid=x.json()['id']
    # A second organization, explicit user session and store permission separation.
    from backend.security import hash_password, issue_session
    with db.connect() as conn:
        conn.execute("INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)",('other-org','Не наша организация',db.now_iso()))
        oid=conn.execute("SELECT id FROM organizations WHERE slug='other-org'").fetchone()['id']
        conn.execute("INSERT INTO stores(slug,name,created_at,organization_id) VALUES(?,?,?,?)",('other-store','Другой магазин',db.now_iso(),oid))
        conn.execute("INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                     (oid,'other@osmanx.local',hash_password('another-long-password-2026'),'owner',db.now_iso()))
        u=conn.execute("SELECT * FROM users WHERE email='other@osmanx.local'").fetchone();conn.commit()
        headers={'Authorization':'Bearer '+issue_session(u,'session-master-secret-super-long-123456789')}
    assert c.get(f'/api/admin/r15/pilots/{pid}',headers=headers).status_code==404
    assert c.get('/api/admin/r15/pilots?slug=central',headers=headers).status_code in (403,404)
    assert c.post(f'/api/admin/r15/pilots/{pid}/start',headers=headers).status_code==404
    good,_=pilot(c,headers,slug='other-store',request_id='other-org-pilot-77777')
    assert good.status_code==201,good.text


def test_read_only_role_cannot_change_pilot(site):
    c,h,db=site;x,_=pilot(c,h);pid=x.json()['id']
    from backend.security import hash_password, issue_session
    with db.connect() as conn:
        conn.execute("INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                     (1,'analyst@osmanx.local',hash_password('long-analyst-password-2026'),'analyst',db.now_iso()))
        user=conn.execute("SELECT * FROM users WHERE email='analyst@osmanx.local'").fetchone()
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(user['id'],store))
        conn.commit()
        analyst={'Authorization':'Bearer '+issue_session(user,'session-master-secret-super-long-123456789')}
    assert c.get(f'/api/admin/r15/pilots/{pid}',headers=analyst).status_code==200
    assert c.post(f'/api/admin/r15/pilots/{pid}/start',headers=analyst).status_code==403
    assert c.post(f'/api/admin/r15/pilots/{pid}/sources',json={'category':'pos','status':'checked','note':'Проверка кассы за прошлую неделю'},headers=analyst).status_code==403


def test_upgrade_schema_idempotent_and_keeps_sales(site):
    _,_,db=site
    from backend.r15 import ensure_schema
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                     (store,123000,'legacy',db.now_iso(),'legacy-preserve-001'));conn.commit()
        ensure_schema(conn);ensure_schema(conn)
        assert conn.execute("SELECT amount_kopeks FROM sales WHERE external_id='legacy-preserve-001'").fetchone()[0]==123000
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
