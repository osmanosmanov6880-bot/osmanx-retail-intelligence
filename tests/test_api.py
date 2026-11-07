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


def test_legacy_sensor_key_is_retired_in_real_mode(secure_client):
    record={'slug':'central','quantity':5,'external_id':'sensor-001','occurred_at':'2026-11-08T12:00:00Z'}
    assert secure_client.post('/api/ingest/traffic',json=record).status_code==410
    assert secure_client.post('/api/ingest/traffic',json=record,headers={'X-OSMANX-Ingest-Key':'sensor-test-key'}).status_code==410


def test_static_frontend_and_kiosk_route(demo_client):
    assert 'OSMANX' in demo_client.get('/').text
    assert 'OSMANX' in demo_client.get('/kiosk/central').text
    assert 'data-kiosk' in demo_client.get('/static/app.js').text
    assert demo_client.get('/api/public/store/unknown').status_code==404


def test_store_timezone_and_stock_import(demo_client):
    stores=demo_client.get('/api/admin/stores').json()
    assert {s['slug'] for s in stores}>={'central','north'}
    before=demo_client.get('/api/admin/stock?slug=central').json()['items']
    result=demo_client.post('/api/admin/stock/import',json={'slug':'central','source':'manual','items':[
      {'sku':'JACKET-XL','product':'Куртка демисезонная','size':'XL','color':'чёрный','quantity':1}]})
    assert result.status_code==200
    assert result.json()['imported']==1
    same=demo_client.post('/api/admin/stock/import',json={'slug':'central','items':[
      {'sku':'JACKET-XL','product':'Куртка демисезонная','size':'XL','color':'чёрный','quantity':3}]})
    assert same.status_code==200
    after=demo_client.get('/api/admin/stock?slug=central').json()['items']
    assert len(after)==len(before)+1
    assert next(item for item in after if item['sku']=='JACKET-XL')['quantity']==3
    assert demo_client.post('/api/admin/stock/import',json={'slug':'central','items':[
      {'sku':'DUP','product':'Пальто','quantity':1},
      {'sku':'dup','product':'Пальто','quantity':3}]}).status_code==422


def test_matching_across_stores_is_conservative(demo_client):
    demand=demo_client.post('/api/admin/demand',json={'slug':'central','product':'Куртка демисезонная','size':'XL','color':'чёрный'})
    did=demand.json()['id']
    matches=demo_client.get(f'/api/admin/demand/{did}/matches')
    assert matches.status_code==200
    assert any(m['slug']=='north' and m['quantity']>=1 for m in matches.json()['matches'])
    zero=demo_client.post('/api/admin/demand',json={'slug':'central','product':'Товар без наличия','size':'XXL'})
    assert demo_client.get(f"/api/admin/demand/{zero.json()['id']}/matches").json()['matches']==[]
    assert demo_client.get('/api/admin/demand/987656/matches').status_code==404


def test_survey_idempotence_and_reward_redemption(demo_client):
    initial=demo_client.get('/api/admin/stores').json()[0]
    settings={**{k:initial[k] for k in ('name','subtitle','incentive','timezone')},
              'reward_enabled':True,'reward_label':'Подарок после опроса'}
    assert demo_client.put('/api/admin/store/central',json=settings).status_code==200
    payload={'rating':5,'purchased':False,'reason':'size','request_id':'survey-request-unique-0001',
             'liked_tags':['quality','service'],'improve_tags':['size','assortment'],
             'liked':'Примерка','suggestion':'Больше размеров'}
    count=demo_client.get('/api/admin/dashboard').json()['surveys_count']
    r1=demo_client.post('/api/public/survey/central',json=payload)
    r2=demo_client.post('/api/public/survey/central',json=payload)
    assert r1.status_code==201 and r2.status_code==201
    assert r2.json()['duplicate'] is True
    code=r1.json()['reward']['code']
    assert code==r2.json()['reward']['code']
    assert demo_client.get('/api/admin/dashboard').json()['surveys_count']==count+1
    assert demo_client.get('/api/admin/dashboard').json()['latest_surveys'][0]['improve_tags']=='["size", "assortment"]'
    redeemed=demo_client.post('/api/admin/rewards/redeem',json={'slug':'central','code':code.lower()})
    assert redeemed.status_code==200 and redeemed.json()['redeemed']
    assert demo_client.post('/api/admin/rewards/redeem',json={'slug':'central','code':code}).status_code==409
    assert demo_client.post('/api/admin/rewards/redeem',json={'slug':'north','code':code}).status_code==404
    assert demo_client.post('/api/public/survey/central',json={**payload,'liked_tags':['hacked']}).status_code==422


def test_confirmed_demand_requires_receipt_from_same_store(demo_client):
    new=demo_client.post('/api/admin/demand',json={'slug':'central','product':'Худи','size':'XL'}).json()['id']
    assert demo_client.patch(f'/api/admin/demand/{new}',json={'status':'converted'}).status_code==422
    assert demo_client.post(f'/api/admin/demand/{new}/convert',json={'sale_id':10000000}).status_code==422
    assert demo_client.post('/api/admin/events',json={'slug':'central','kind':'sale','quantity':1,'amount_rub':5990}).status_code==201
    with __import__('backend.database',fromlist=['connect']).connect() as db:
        sale=db.execute('SELECT MAX(id) FROM sales WHERE store_id=(SELECT id FROM stores WHERE slug=?)',('central',)).fetchone()[0]
    assert demo_client.post(f'/api/admin/demand/{new}/convert',json={'sale_id':sale}).status_code==200
    assert demo_client.patch(f'/api/admin/demand/{new}',json={'status':'converted'}).status_code==200
    second=demo_client.post('/api/admin/demand',json={'slug':'central','product':'Пальто'}).json()['id']
    assert demo_client.post(f'/api/admin/demand/{second}/convert',json={'sale_id':sale}).status_code==409
    assert any(r['id']==new and r['sale_id']==sale for r in demo_client.get('/api/admin/dashboard').json()['latest_demand'])


def test_experiment_lifecycle_and_daily_report(demo_client):
    record={'slug':'central','title':'Размеры XL','hypothesis':'Перевозка товаров между магазинами даст дополнительные продажи',
            'metric':'confirmed_sales','baseline':4}
    result=demo_client.post('/api/admin/experiments',json=record)
    assert result.status_code==201
    eid=result.json()['id']
    assert demo_client.patch(f'/api/admin/experiments/{eid}',json={'status':'finished','notes':'No result'}).status_code==422
    assert demo_client.patch(f'/api/admin/experiments/{eid}',json={'status':'running','notes':'Start'}).status_code==200
    assert demo_client.patch(f'/api/admin/experiments/{eid}',json={'status':'finished','result':6,'notes':'Confirmed sale links'}).status_code==200
    assert next(x for x in demo_client.get('/api/admin/experiments').json() if x['id']==eid)['result']==6
    data=demo_client.get('/api/admin/report/daily?slug=central&days=7').json()
    assert data['timezone']=='Europe/Moscow'
    assert len(data['days'])==7
    assert all('conversion' in x and 'date' in x for x in data['days'])
    assert demo_client.get('/api/admin/report/daily?days=8').status_code==422


def test_reports_escape_spreadsheet_formulas(demo_client):
    new=demo_client.post('/api/admin/demand',json={'slug':'central','product':'=FORMULA(INJECTION)','size':'S'})
    assert new.status_code==201
    csv=demo_client.get('/api/admin/export/demand.csv').text
    assert "'=FORMULA(INJECTION)" in csv
    assert csv.startswith('\ufeff')
    assert demo_client.get('/api/admin/export/invalid.csv').status_code==404


def test_new_endpoints_require_auth(secure_client):
    assert secure_client.get('/api/admin/export/surveys.csv').status_code==401
    assert secure_client.get('/api/admin/stock').status_code==401


def test_store_creation_and_isolation(demo_client):
    result=demo_client.post('/api/admin/stores',json={'slug':'boutique-3','name':'Бутик №3','timezone':'Europe/Stockholm'})
    assert result.status_code==201
    assert demo_client.post('/api/admin/stores',json={'slug':'boutique-3','name':'Дубль'}).status_code==409
    assert demo_client.post('/api/admin/stores',json={'slug':'../../foo','name':'Bad'}).status_code==422
    assert demo_client.post('/api/admin/stores',json={'slug':'other','name':'Good','timezone':'Mars/Galaxy'}).status_code==422
    assert demo_client.get('/api/admin/dashboard?slug=boutique-3').json()['visitors']==0
    assert demo_client.post('/api/admin/events',json={'slug':'boutique-3','kind':'entry','quantity':5}).status_code==201
    assert demo_client.get('/api/admin/dashboard?slug=boutique-3').json()['visitors']==5


def test_privacy_headers_and_no_real_camera_claim(demo_client):
    config=demo_client.get('/api/config').json()
    assert config['features']['camera']=='not_connected'
    assert config['features']['rewards']=='optional_manual_validation'
    r=demo_client.get('/api/admin/dashboard')
    assert r.headers['x-content-type-options']=='nosniff'
    assert 'object-src' in r.headers['content-security-policy']
    assert r.headers['cache-control']=='no-store'
    quality=r.json()['sources']
    assert isinstance(quality['warnings'],list)
    assert any(x['source']=='demo_sensor' for x in quality['visits'])


def test_zone_heatmap_and_new_zone(demo_client):
    initial=demo_client.get('/api/admin/dashboard').json()
    assert len(initial['zones'])>=4
    assert any(item['count']>0 for item in initial['zones'])
    new=demo_client.post('/api/admin/zones',json={'slug':'central','code':'vip-zone','name':'VIP-примерочная','x':60,'y':20})
    assert new.status_code==201
    assert any(z['code']=='vip-zone' and z['x']==60 for z in demo_client.get('/api/admin/dashboard').json()['zones'])
    assert demo_client.post('/api/admin/zones',json={'slug':'central','code':'vip-zone','name':'VIP-комната','x':999,'y':50}).status_code==422
    assert demo_client.get('/api/admin/zones?slug=central').status_code==200


def test_legacy_zone_key_is_retired_in_real_mode(secure_client):
    payload={'slug':'central','zone_code':'fitting','quantity':7,'external_id':'zone-test-010','occurred_at':'2026-11-08T12:00:00Z'}
    assert secure_client.post('/api/ingest/zones',json=payload).status_code==410
    assert secure_client.post('/api/ingest/zones',json=payload,headers={'X-OSMANX-Ingest-Key':'sensor-test-key'}).status_code==410


def test_non_destructive_upgrade_from_r01(tmp_path,monkeypatch):
    import sqlite3
    import importlib
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    import backend.database as database
    importlib.reload(database)
    with sqlite3.connect(tmp_path/'retail.sqlite3') as db:
        db.executescript(database.SCHEMA)
        db.execute("INSERT INTO stores(slug,name,created_at) VALUES('original','Old store','2026-11-01T00:00:00+00:00')")
        db.commit()
    database.initialize_db(demo=False)
    database.initialize_db(demo=False)
    with database.connect() as db:
        row=db.execute("SELECT name,timezone,reward_enabled FROM stores WHERE slug='original'").fetchone()
        assert row['name']=='Old store'
        assert row['timezone']=='Europe/Moscow'
        assert row['reward_enabled']==0
        assert db.execute("SELECT COUNT(*) FROM zones").fetchone()[0]==0
