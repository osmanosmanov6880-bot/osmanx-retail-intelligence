"""End-to-end FastAPI/SQLite tests with temporary isolated databases."""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture

def demo_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OSMANX_DEMO_MODE","1")
    monkeypatch.setenv("OSMANX_DATA_DIR",str(tmp_path))
    import backend.database as database
    import backend.app as api_module
    importlib.reload(database)
    importlib.reload(api_module)
    with TestClient(api_module.app) as client:
        yield client


@pytest.fixture

def secure_client(tmp_path,monkeypatch):
    monkeypatch.setenv("OSMANX_DEMO_MODE","0")
    monkeypatch.setenv("OSMANX_DATA_DIR",str(tmp_path))
    monkeypatch.setenv("OSMANX_ADMIN_PASSWORD","top-secret-password-12345")
    monkeypatch.setenv("OSMANX_SESSION_SECRET","a-long-and-unpredictable-signing-secret-for-test-2026")
    monkeypatch.setenv("OSMANX_INGEST_KEY","sensor-test-key")
    import backend.database as database
    import backend.app as api_module
    importlib.reload(database)
    importlib.reload(api_module)
    with TestClient(api_module.app) as client:
        yield client


def test_demo_dashboard_contains_explicitly_seeded_data(demo_client):
    r=demo_client.get('/api/admin/dashboard?days=30')
    assert r.status_code==200
    data=r.json()
    assert data['visitors']>1000
    assert data['purchases']>100
    assert data['revenue']>0
    assert 0<data['conversion']<100
    assert len(data['hourly'])==13
    assert len(data['recommendations'])>=1
    assert demo_client.get('/api/config').json()['demo'] is True


def test_public_survey_is_persistent_and_bounded(demo_client):
    before=demo_client.get('/api/admin/dashboard').json()['surveys_count']
    payload={"rating":5,"purchased":False,"reason":"size","liked":"Вежливость","suggestion":"Больше XL"}
    assert demo_client.post('/api/public/survey/central',json=payload).status_code==201
    after=demo_client.get('/api/admin/dashboard').json()
    assert after['surveys_count']==before+1
    assert after['latest_surveys'][0]['suggestion']=='Больше XL'
    assert demo_client.post('/api/public/survey/central',json={**payload,'rating':9}).status_code==422
    assert demo_client.post('/api/public/survey/central',json={**payload,'purchased':True}).status_code==422


def test_manual_events_and_demand_work(demo_client):
    before=demo_client.get('/api/admin/dashboard').json()
    assert demo_client.post('/api/admin/events',json={'slug':'central','kind':'entry','quantity':7,'amount_rub':0}).status_code==201
    assert demo_client.post('/api/admin/events',json={'slug':'central','kind':'sale','quantity':1,'amount_rub':2990}).status_code==201
    after=demo_client.get('/api/admin/dashboard').json()
    assert after['visitors']==before['visitors']+7
    assert after['purchases']==before['purchases']+1
    assert after['revenue']==before['revenue']+2990
    new=demo_client.post('/api/admin/demand',json={'slug':'central','product':'Куртка мембранная','size':'XXL','color':'серый'})
    assert new.status_code==201
    did=new.json()['id']
    assert demo_client.patch(f'/api/admin/demand/{did}',json={'status':'located'}).status_code==200
    updated=demo_client.get('/api/admin/dashboard').json()['latest_demand']
    assert any(item['id']==did and item['status']=='located' for item in updated)
    assert demo_client.patch('/api/admin/demand/99999999',json={'status':'closed'}).status_code==404
    assert demo_client.post('/api/admin/events',json={'slug':'central','kind':'sale','quantity':5}).status_code==422


def test_pos_import_is_idempotent(demo_client):
    payload={'slug':'central','sales':[{'external_id':'receipt-100','amount_rub':4350,'occurred_at':'2026-11-08T12:00:00Z'},
                {'external_id':'receipt-101','amount_rub':5950,'occurred_at':'2026-11-08T12:05:00Z'}]}
    first=demo_client.post('/api/admin/import/pos',json=payload)
    second=demo_client.post('/api/admin/import/pos',json=payload)
    assert first.status_code==200 and first.json()['imported']==2
    assert second.status_code==200 and second.json()['imported']==0 and second.json()['duplicates']==2


def test_auth_session_is_required_in_real_mode(secure_client):
    assert secure_client.get('/api/admin/dashboard').status_code==401
    assert secure_client.post('/api/auth/login',json={'password':'wrong'}).status_code==401
    result=secure_client.post('/api/auth/login',json={'password':'top-secret-password-12345'})
    assert result.status_code==200
    token=result.json()['token']
    headers={'Authorization':'Bearer '+token}
    assert secure_client.get('/api/admin/dashboard',headers=headers).status_code==200
    assert secure_client.get('/api/admin/dashboard',headers={'Authorization':'Bearer fake.token'}).status_code==401
    public=secure_client.post('/api/public/survey/central',json={'rating':4,'purchased':True})
    assert public.status_code==201
    assert secure_client.get('/api/admin/dashboard',headers=headers).json()['surveys_count']==1


def test_sensor_key_and_idempotence(secure_client):
    record={'slug':'central','quantity':5,'external_id':'sensor-001','occurred_at':'2026-11-08T12:00:00Z'}
    assert secure_client.post('/api/ingest/traffic',json=record).status_code==401
    first=secure_client.post('/api/ingest/traffic',json=record,headers={'X-OSMANX-Ingest-Key':'sensor-test-key'})
    second=secure_client.post('/api/ingest/traffic',json=record,headers={'X-OSMANX-Ingest-Key':'sensor-test-key'})
    assert first.status_code==201 and first.json()['saved']
    assert second.status_code==201 and second.json()['duplicate']


def test_static_frontend_and_kiosk_route(demo_client):
    assert 'OSMANX' in demo_client.get('/').text
    assert 'OSMANX' in demo_client.get('/kiosk/central').text
    assert 'data-kiosk' in demo_client.get('/static/app.js').text
    assert demo_client.get('/api/public/store/unknown').status_code==404
