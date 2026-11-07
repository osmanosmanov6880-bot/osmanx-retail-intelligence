"""R0.3 executable cross-org, permission, device-signature and import acceptance."""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from datetime import datetime,timedelta,timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def secure(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','super-secure-password-2026!')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','secure-session-secret-for-tests-more-than-32-chars')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','separate-device-master-secret-very-long-for-tests')
    import backend.database as db
    import backend.app as module
    importlib.reload(db)
    importlib.reload(module)
    with TestClient(module.app) as client:
        login=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'super-secure-password-2026!'})
        assert login.status_code==200
        headers={'Authorization':'Bearer '+login.json()['token']}
        yield client, headers, db, module


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def request_device(client,device_id,secret,data,kind='traffic',timestamp=None):
    stamp=str(int(time.time()) if timestamp is None else timestamp)
    raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    signature=hmac.new(secret.encode(),stamp.encode()+b'\n'+device_id.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    return client.post(f'/api/ingest/v2/{kind}',content=raw,
             headers={'X-OSMANX-Device':device_id,'X-OSMANX-Timestamp':stamp,'X-OSMANX-Signature':signature,'Content-Type':'application/json'})


def test_organizations_roles_and_cross_tenant_isolation(secure):
    client,root,db_module,_=secure
    from scripts.provision_tenant import provision
    with db_module.connect() as db:
        result=provision(db,slug='atelier',name='Atelier 1',store_slug='atelier-main',
                         email='tenant@example.com',password='tenant-strong-password-2026')
    assert result['store']=='atelier-main'
    guest=client.post('/api/auth/login',json={'email':'tenant@example.com','password':'tenant-strong-password-2026'})
    assert guest.status_code==200
    other={'Authorization':'Bearer '+guest.json()['token']}
    assert [r['slug'] for r in client.get('/api/admin/stores',headers=other).json()]==['atelier-main']
    assert client.get('/api/admin/dashboard?slug=central',headers=other).status_code==404
    assert client.get('/api/admin/stock?slug=central',headers=other).status_code==404
    assert client.get('/api/admin/experiments?slug=central',headers=other).status_code==404
    assert client.get('/api/admin/export/surveys.csv?slug=central',headers=other).status_code==404
    assert client.post('/api/admin/events',json={'slug':'central','kind':'sale','quantity':1,'amount_rub':5000},headers=other).status_code==404
    assert client.get('/api/admin/dashboard?slug=atelier-main',headers=root).status_code==404
    # Demand in org A must be inaccessible by ID in org B, including stock search/convert.
    d=client.post('/api/admin/demand',json={'slug':'central','product':'Coat','size':'M'},headers=root).json()['id']
    assert client.get(f'/api/admin/demand/{d}/matches',headers=other).status_code==404
    assert client.post(f'/api/admin/demand/{d}/convert',json={'sale_id':1234},headers=other).status_code==404
    e=client.post('/api/admin/experiments',json={'slug':'central','title':'Test conversion','hypothesis':'Increase fit to close demand','metric':'conversion'},headers=root).json()['id']
    assert client.patch(f'/api/admin/experiments/{e}',json={'status':'cancelled'},headers=other).status_code==404
    # Stock matches never leak another tenant's inventory.
    client.post('/api/admin/stock/import',json={'slug':'atelier-main','items':[{'sku':'COAT-OTHER','product':'Coat','size':'M','quantity':7}]},headers=other)
    assert client.get(f'/api/admin/demand/{d}/matches',headers=root).json()['matches']==[]


def test_user_roles_assigned_stores_and_revocation(secure):
    client,root,_,_=secure
    assert client.post('/api/admin/stores',json={'slug':'second-unit','name':'Second unit'},headers=root).status_code==201
    resp=client.post('/api/admin/team',json={'email':'manager@example.com','name':'Manager','password':'manager-pass-2026!',
        'role':'manager','stores':['central']},headers=root)
    assert resp.status_code==201,resp.text
    manager_id=resp.json()['id']
    login=client.post('/api/auth/login',json={'email':'manager@example.com','password':'manager-pass-2026!'}).json()['token']
    manager={'Authorization':'Bearer '+login}
    assert {x['slug'] for x in client.get('/api/admin/stores',headers=manager).json()}=={'central'}
    assert client.get('/api/admin/dashboard?slug=second-unit',headers=manager).status_code==404
    assert client.post('/api/admin/events',json={'slug':'central','kind':'interest','quantity':4},headers=manager).status_code==201
    assert client.post('/api/admin/stores',json={'slug':'evil-new','name':'Evil'},headers=manager).status_code==403
    assert client.get('/api/admin/team',headers=manager).status_code==403
    view=client.post('/api/admin/team',json={'email':'view@example.com','name':'Viewer','password':'viewer-password-123',
        'role':'viewer','stores':['second-unit']},headers=root)
    assert view.status_code==201
    token=client.post('/api/auth/login',json={'email':'view@example.com','password':'viewer-password-123'}).json()['token']
    readonly={'Authorization':'Bearer '+token}
    assert client.get('/api/admin/dashboard?slug=second-unit',headers=readonly).status_code==200
    assert client.post('/api/admin/demand',json={'slug':'second-unit','product':'Blazer'},headers=readonly).status_code==403
    assert client.get('/api/admin/export/surveys.csv?slug=second-unit',headers=readonly).status_code==403
    assert client.get('/api/admin/dashboard?slug=central',headers=readonly).status_code==404
    disabled=client.patch(f'/api/admin/team/{manager_id}',json={'active':False,'stores':['central']},headers=root)
    assert disabled.status_code==200
    assert client.get('/api/admin/dashboard?slug=central',headers=manager).status_code==401


def test_signed_sensor_replay_conflicts_rotation_and_zone_ownership(secure):
    client,root,_,_=secure
    assert client.post('/api/ingest/traffic',json={'slug':'central','quantity':1,'external_id':'legacy-test-0001','occurred_at':now()}).status_code==410
    created=client.post('/api/admin/devices',json={'slug':'central','name':'Entrance sensor','kind':'traffic'},headers=root)
    assert created.status_code==201,created.text
    dev=created.json()
    record={'quantity':5,'external_id':'entry-0001','occurred_at':now()}
    assert request_device(client,dev['device_id'],dev['secret'],record).json()=={'saved':True,'duplicate':False}
    assert request_device(client,dev['device_id'],dev['secret'],record).json()=={'saved':False,'duplicate':True}
    assert request_device(client,dev['device_id'],dev['secret'],{**record,'quantity':99}).status_code==409
    assert request_device(client,dev['device_id'],'wrong-secret',record).status_code==401
    assert request_device(client,dev['device_id'],dev['secret'],record,timestamp=int(time.time())-1000).status_code==401
    assert request_device(client,dev['device_id'],dev['secret'],{**record,'external_id':'new-2','zone_code':'entrance'}).status_code==422
    rotate=client.post(f"/api/admin/devices/{dev['device_id']}/rotate",headers=root).json()
    assert request_device(client,dev['device_id'],dev['secret'],{**record,'external_id':'new-3'}).status_code==401
    assert request_device(client,dev['device_id'],rotate['secret'],{**record,'external_id':'new-3'}).status_code==201
    zone=client.post('/api/admin/devices',json={'slug':'central','name':'Fitting zone','kind':'zones'},headers=root).json()
    client.post('/api/admin/zones',json={'slug':'central','code':'fitting','name':'Fitting room','x':50,'y':50},headers=root)
    assert request_device(client,zone['device_id'],zone['secret'],{'quantity':3,'external_id':'z-0001','occurred_at':now(),'zone_code':'fitting'},'zones').status_code==201
    assert request_device(client,zone['device_id'],zone['secret'],{'quantity':3,'external_id':'z-0002','occurred_at':now(),'zone_code':'unknown'},'zones').status_code==404
    assert client.delete(f"/api/admin/devices/{dev['device_id']}",headers=root).status_code==200
    assert request_device(client,dev['device_id'],rotate['secret'],{**record,'external_id':'new-4'}).status_code==401


def test_import_preview_apply_transaction_and_duplicate_conflicts(secure):
    client,root,_,_=secure
    body={'slug':'central','kind':'pos','rows':[{'external_id':'a100','amount_rub':1250.99,'occurred_at':now()},
                                              {'external_id':'a101','amount_rub':2500,'occurred_at':now()}]}
    first=client.post('/api/admin/imports/preview',json=body,headers=root)
    assert first.status_code==201,first.text
    batch=first.json()
    assert batch['preview']['added']==2
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']==0
    applied=client.post('/api/admin/imports/apply',json={'batch_key':batch['batch_key']},headers=root)
    assert applied.status_code==200,applied.text
    assert applied.json()['summary']['added']==2
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']==2
    assert client.post('/api/admin/imports/apply',json={'batch_key':batch['batch_key']},headers=root).json()['already_applied'] is True
    repeated=client.post('/api/admin/imports/preview',json=body,headers=root).json()
    assert repeated['preview']['unchanged']==2
    changed=client.post('/api/admin/imports/preview',json={**body,'rows':[{**body['rows'][0],'amount_rub':1500}]},headers=root).json()
    assert changed['preview']['valid'] is False
    assert client.post('/api/admin/imports/apply',json={'batch_key':changed['batch_key']},headers=root).status_code==409
    # Snapshot invalidation: no partial changes if store changed since review.
    new={'slug':'central','kind':'inventory','rows':[{'sku':'BRAND-01','product':'Coat','size':'M','quantity':3}]}
    staged=client.post('/api/admin/imports/preview',json=new,headers=root).json()
    client.post('/api/admin/stock/import',json={'slug':'central','items':[{'sku':'BRAND-01','product':'Coat','size':'M','quantity':8}]},headers=root)
    assert client.post('/api/admin/imports/apply',json={'batch_key':staged['batch_key']},headers=root).status_code==409
    stock=client.get('/api/admin/stock?slug=central',headers=root).json()['items']
    assert stock[0]['quantity']==8


def test_surveys_idempotency_budget_atomic_redemption_and_retention(secure):
    client,root,db_module,_=secure
    store=client.get('/api/admin/stores',headers=root).json()[0]
    payload={**{k:store[k] for k in ('name','subtitle','incentive','timezone')},
             'reward_enabled':True,'reward_label':'Тестовый подарок','reward_daily_limit':2,
             'survey_retention_days':7,'traffic_mode':'auto'}
    assert client.put('/api/admin/store/central',json=payload,headers=root).status_code==200
    base={'rating':5,'purchased':False,'reason':'size','request_id':'survey-unique-request-1111'}
    a=client.post('/api/public/survey/central',json=base)
    assert a.status_code==201 and a.json()['reward']['code']
    assert client.post('/api/public/survey/central',json=base).json()['duplicate']
    assert client.post('/api/public/survey/central',json={**base,'rating':2}).status_code==409
    b=client.post('/api/public/survey/central',json={**base,'request_id':'survey-unique-request-2222'})
    c=client.post('/api/public/survey/central',json={**base,'request_id':'survey-unique-request-3333'})
    assert b.json()['reward'] is not None and c.json()['reward'] is None and c.json()['reward_unavailable']
    assert client.post('/api/admin/rewards/redeem',json={'slug':'central','code':a.json()['reward']['code']},headers=root).status_code==200
    assert client.post('/api/admin/rewards/redeem',json={'slug':'central','code':a.json()['reward']['code']},headers=root).status_code==409
    from backend.privacy import purge_expired_feedback
    with db_module.connect() as db:
        db.execute("UPDATE surveys SET created_at=? WHERE request_id='survey-unique-request-1111'",
                   ((datetime.now(timezone.utc)-timedelta(days=9)).isoformat(timespec='seconds'),))
        db.commit()
        assert purge_expired_feedback(db,dry_run=True)['stores'][0]['eligible']==1
        assert purge_expired_feedback(db,dry_run=False)['purged']==1
    assert client.get('/api/admin/dashboard',headers=root).json()['surveys_count']==2


def test_traffic_source_policy_does_not_mix_manual_with_sensor(secure):
    client,root,_,_=secure
    settings=client.get('/api/admin/stores',headers=root).json()[0]
    def update(mode):
        return client.put('/api/admin/store/central',json={**{k:settings[k] for k in ('name','subtitle','incentive','timezone','reward_enabled','reward_label')},
                   'traffic_mode':mode},headers=root)
    client.post('/api/admin/events',json={'slug':'central','kind':'entry','quantity':20},headers=root)
    d=client.post('/api/admin/devices',json={'slug':'central','name':'New counter','kind':'traffic'},headers=root).json()
    request_device(client,d['device_id'],d['secret'],{'quantity':4,'external_id':'counter-policy','occurred_at':now()})
    update('combined')
    assert client.get('/api/admin/dashboard',headers=root).json()['visitors']==24
    update('auto')
    result=client.get('/api/admin/dashboard',headers=root).json()
    assert result['visitors']==4 and result['sources']['traffic_mode']=='auto'
    update('manual')
    assert client.get('/api/admin/dashboard',headers=root).json()['visitors']==20
