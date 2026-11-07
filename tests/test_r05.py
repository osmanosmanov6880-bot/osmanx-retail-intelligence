"""R0.5 acceptance: reservations, fittings, returns, pricing and decisions."""
from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as db
    import backend.app as api
    importlib.reload(db)
    importlib.reload(api)
    with TestClient(api.app) as client:
        signed=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert signed.status_code==200,signed.text
        yield client,{'Authorization':'Bearer '+signed.json()['token']},db


def prepare_stock_and_demand(site,qty=2):
    client,root,db=site
    added=client.post('/api/admin/stores',headers=root,json={'name':'Северный филиал','slug':'north'})
    assert added.status_code in (201,409),added.text
    item=client.post('/api/admin/stock/import',headers=root,json={'slug':'north',
      'items':[{'sku':'COAT-XL-001','product':'Куртка тестовая','size':'XL','color':'чёрный','quantity':qty}]})
    assert item.status_code==200,item.text
    request=client.post('/api/admin/demand',headers=root,json={'slug':'central','product':'Куртка тестовая','size':'XL','color':'чёрный'})
    assert request.status_code==201,request.text
    stock=client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]
    return request.json()['id'],stock['id']


def sale(site,amount=5000):
    client,root,db=site
    r=client.post('/api/admin/events',headers=root,json={'slug':'central','kind':'sale','quantity':1,'amount_rub':amount})
    assert r.status_code==201,r.text
    with db.connect() as conn:
        return conn.execute("SELECT id FROM sales WHERE store_id=(SELECT id FROM stores WHERE slug='central') ORDER BY id DESC LIMIT 1").fetchone()['id']


def test_new_r05_routes_require_login(site):
    client,_,_=site
    for route in ('reservations','fittings','returns','pricing','decisions'):
        assert client.get('/api/admin/'+route).status_code==401
        if route!='decisions':
            assert client.post('/api/admin/'+route,json={}).status_code==401


def test_exact_match_reservation_idempotency_conflicts_and_cancel(site):
    client,root,_=site
    demand_id,item_id=prepare_stock_and_demand(site,qty=1)
    matches=client.get(f'/api/admin/demand/{demand_id}/matches',headers=root).json()['matches']
    assert matches[0]['id']==item_id and matches[0]['available']==1
    payload={'demand_id':demand_id,'inventory_id':item_id,'request_id':'reserve-client-id-00001','quantity':1,'hours':24}
    first=client.post('/api/admin/reservations',json=payload,headers=root)
    assert first.status_code==201,first.text
    assert first.json()['status']=='held'
    assert client.post('/api/admin/reservations',json=payload,headers=root).json()['duplicate']
    assert client.post('/api/admin/reservations',json={**payload,'quantity':2},headers=root).status_code==409
    assert client.get(f'/api/admin/demand/{demand_id}/matches',headers=root).json()['matches']==[]
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['available']==0
    assert client.post('/api/admin/stock/import',json={'slug':'north','items':[
        {'sku':'COAT-XL-001','product':'Куртка тестовая','size':'XL','color':'чёрный','quantity':0}]},headers=root).status_code==409
    cancelled=client.post(f"/api/admin/reservations/{first.json()['id']}/action",json={'action':'cancel'},headers=root)
    assert cancelled.status_code==200
    assert client.post(f"/api/admin/reservations/{first.json()['id']}/action",json={'action':'cancel'},headers=root).status_code==409
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['available']==1
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['latest_demand'][0]['status']=='open'


def test_collected_reservation_decrements_stock_but_not_sales(site):
    client,root,_=site
    demand_id,item_id=prepare_stock_and_demand(site,qty=2)
    before=client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']
    r=client.post('/api/admin/reservations',json={'demand_id':demand_id,'inventory_id':item_id,
                   'request_id':'reserve-collected-id-0002'},headers=root).json()
    changed=client.post(f"/api/admin/reservations/{r['id']}/action",json={'action':'collect'},headers=root)
    assert changed.status_code==200 and changed.json()['not_a_sale']
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['quantity']==1
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['purchases']==before


def test_reservation_concurrent_claims_never_oversell(site):
    client,root,_=site
    first,item=prepare_stock_and_demand(site,qty=1)
    second=client.post('/api/admin/demand',json={'slug':'central','product':'Куртка тестовая','size':'XL','color':'чёрный'},headers=root).json()['id']
    def claim(demand,n):
        return client.post('/api/admin/reservations',json={'demand_id':demand,'inventory_id':item,
                 'request_id':f'concurrency-reservation-{n:04d}'},headers=root).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(lambda pair:claim(*pair),[(first,1),(second,2)]))
    assert sorted(statuses)==[201,409]
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['reserved']==1


def test_reservation_expiry_releases_quantity(site):
    client,root,db=site
    demand,item=prepare_stock_and_demand(site,qty=1)
    held=client.post('/api/admin/reservations',json={'demand_id':demand,'inventory_id':item,
                  'request_id':'reserve-expiring-id-0004'},headers=root).json()
    with db.connect() as conn:
        conn.execute('UPDATE reservations SET expires_at=? WHERE id=?',
           ((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(timespec='seconds'),held['id']))
        conn.commit()
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['available']==1
    assert client.post(f"/api/admin/reservations/{held['id']}/action",json={'action':'collect'},headers=root).status_code==409
    again=client.post('/api/admin/reservations',json={'demand_id':demand,'inventory_id':item,
             'request_id':'reserve-after-expire-0005'},headers=root)
    assert again.status_code==201,again.text


def test_fitting_observations_aggregated_not_individual(site):
    client,root,_=site
    for _ in range(2):
        r=client.post('/api/admin/fittings',headers=root,json={'slug':'central','product':'Жакет','size':'M',
           'trials':5,'purchases':1,'reason':'fit'})
        assert r.status_code==201,r.text
    assert client.post('/api/admin/fittings',headers=root,json={'slug':'central','product':'Жакет',
      'size':'M','trials':2,'purchases':3,'reason':'fit'}).status_code==422
    result=client.get('/api/admin/fittings?slug=central',headers=root).json()
    assert result['products'][0]['trials']==10
    assert result['products'][0]['purchase_rate']==20.0
    assert result['reasons'][0]['count']==2
    assert client.get('/api/admin/decisions?slug=central',headers=root).json()['items'][0]['kind']=='fitting'


def test_returns_receipt_integrity_idempotence_and_cap(site):
    client,root,_=site
    receipt=sale(site,amount=5000)
    payload={'slug':'central','sale_id':receipt,'external_id':'refunded-item-00000001',
      'item':'Куртка','amount_kopeks':250000,'reason':'size'}
    first=client.post('/api/admin/returns',json=payload,headers=root)
    assert first.status_code==201,first.text
    assert client.post('/api/admin/returns',json=payload,headers=root).json()['duplicate']
    assert client.post('/api/admin/returns',json={**payload,'amount_kopeks':250001},headers=root).status_code==409
    assert client.post('/api/admin/returns',json={**payload,'external_id':'refund-other-ref-00002',
      'amount_kopeks':250001},headers=root).status_code==409
    report=client.get('/api/admin/returns',headers=root).json()
    assert report['total']['amount_kopeks']==250000
    assert client.get('/api/admin/dashboard?slug=central',headers=root).json()['revenue']==5000.0


def test_return_cannot_cross_receipt_store(site):
    client,root,_=site
    receipt=sale(site)
    client.post('/api/admin/stores',json={'slug':'second','name':'Second'},headers=root)
    assert client.post('/api/admin/returns',json={'slug':'second','sale_id':receipt,
      'external_id':'wrong-store-return-0001','item':'Some coat','reason':'fit','amount_kopeks':100},headers=root).status_code==422


def test_discount_planner_exact_kopeks_and_break_even(site):
    client,root,_=site
    payload={'slug':'central','title':'Сценарий куртка','sku':'COAT-BLK-M',
      'price_kopeks':1000000,'cost_kopeks':600000,'discount_bps':2000,
      'baseline_units':10,'planned_units':20}
    r=client.post('/api/admin/pricing',headers=root,json=payload)
    assert r.status_code==201,r.text
    scenario=r.json()['analysis']
    assert scenario['unit_profit_before_kopeks']==400000
    assert scenario['unit_profit_after_kopeks']==200000
    assert scenario['break_even_units']==20
    assert scenario['delta_kopeks']==0
    discounted=client.post('/api/admin/pricing',headers=root,json={**payload,
      'title':'Опасная скидка','discount_bps':6000}).json()['analysis']
    assert discounted['unit_profit_after_kopeks']==-200000
    assert discounted['break_even_units'] is None
    assert 'себестоимость' in discounted['warning']
    assert len(client.get('/api/admin/pricing',headers=root).json())==2


def test_decision_status_persists_without_fabricated_profit(site):
    client,root,_=site
    for _ in range(3):
        client.post('/api/admin/demand',headers=root,json={'slug':'central','product':'Пальто','size':'L'})
    items=client.get('/api/admin/decisions?slug=central',headers=root).json()['items']
    finding=next(r for r in items if r['kind']=='demand')
    assert 'выруч' not in finding['evidence'].lower()
    changed=client.patch(f"/api/admin/decisions/{finding['key']}?slug=central",headers=root,
                        json={'status':'testing','note':'Проверяем наличие 7 дней'})
    assert changed.status_code==200,changed.text
    again=client.get('/api/admin/decisions?slug=central',headers=root).json()['items']
    assert next(r for r in again if r['key']==finding['key'])['status']=='testing'
    assert client.patch('/api/admin/decisions/nonexistent?slug=central',headers=root,
                  json={'status':'done'}).status_code==404


def test_r05_isolation_and_roles(site):
    client,root,db=site
    from scripts.provision_tenant import provision
    with db.connect() as connection:
        provision(connection,slug='independent',name='Another owner',store_slug='independent-main',
                  email='another@example.com',password='independent-account-password-123')
    token=client.post('/api/auth/login',json={'email':'another@example.com',
       'password':'independent-account-password-123'}).json()['token']
    other={'Authorization':'Bearer '+token}
    first,item=prepare_stock_and_demand(site)
    for route in ('reservations','fittings','returns','pricing','decisions'):
        assert client.get('/api/admin/'+route+'?slug=central',headers=other).status_code==404
    assert client.post('/api/admin/reservations',headers=other,json={'demand_id':first,
       'inventory_id':item,'request_id':'illegal-hold-000000001'}).status_code==404
    assert client.post('/api/admin/returns',headers=other,json={'slug':'central','sale_id':999,
       'external_id':'illegal-return-0000001','item':'Coat','reason':'fit','amount_kopeks':100}).status_code==404
    assert client.post('/api/admin/pricing',headers=other,json={'slug':'central','title':'Bad request','sku':'COAT',
       'price_kopeks':1000,'cost_kopeks':500,'discount_bps':10,'baseline_units':1,'planned_units':2}).status_code==404
    view=client.post('/api/admin/team',headers=root,json={'email':'readonly@example.com','name':'Read only',
      'password':'read-only-password-1234','role':'viewer','stores':['central']}).json()
    viewer_token=client.post('/api/auth/login',json={'email':'readonly@example.com','password':'read-only-password-1234'}).json()['token']
    viewer={'Authorization':'Bearer '+viewer_token}
    assert client.get('/api/admin/fittings?slug=central',headers=viewer).status_code==200
    assert client.post('/api/admin/fittings',headers=viewer,json={'slug':'central','product':'Coat','trials':1,'purchases':0}).status_code==403
    assert client.patch('/api/admin/decisions/measurement-start?slug=central',headers=viewer,
                       json={'status':'done'}).status_code==403


def test_staged_import_does_not_erase_held_stock(site):
    client,root,_=site
    demand,item=prepare_stock_and_demand(site,qty=2)
    payload={'slug':'north','kind':'inventory','rows':[{'sku':'COAT-XL-001',
      'product':'Куртка тестовая','size':'XL','color':'чёрный','quantity':0}]}
    preview=client.post('/api/admin/imports/preview',headers=root,json=payload)
    assert preview.status_code==201,preview.text
    assert client.post('/api/admin/reservations',headers=root,json={'demand_id':demand,'inventory_id':item,
       'request_id':'protect-held-in-import-id'}).status_code==201
    assert client.post('/api/admin/imports/apply',headers=root,json={'batch_key':preview.json()['batch_key']}).status_code==409
    assert client.get('/api/admin/stock?slug=north',headers=root).json()['items'][0]['quantity']==2


def test_reservation_expiry_cleanup_is_organization_scoped(site):
    client,root,db=site
    first,inventory_id=prepare_stock_and_demand(site,qty=2)
    from scripts.provision_tenant import provision
    from backend.database import now_iso
    with db.connect() as connection:
        provision(connection,slug='separate-expiry',name='Independent tenant',
                  store_slug='separate-expiry-store',email='expiry@example.com',
                  password='independent-expiry-password-123')
        tenant=connection.execute("SELECT id FROM organizations WHERE slug='separate-expiry'").fetchone()['id']
        store=connection.execute("SELECT id FROM stores WHERE slug='separate-expiry-store'").fetchone()['id']
        inventory=connection.execute("INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (store,'OTHER-XL','Independent Coat','XL','Black',1,'manual',now_iso())).lastrowid
        demand=connection.execute("INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (store,'Independent Coat','XL','Black','located',now_iso(),now_iso())).lastrowid
        expiry=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(timespec='seconds')
        held=connection.execute("""INSERT INTO reservations(organization_id,request_id,demand_id,source_inventory_id,source_store_id,destination_store_id,quantity,status,expires_at,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(tenant,'expired-other-tenant-0001',demand,inventory,store,store,1,'held',expiry,now_iso(),now_iso())).lastrowid
        connection.commit()
    created=client.post('/api/admin/reservations',json={'demand_id':first,'inventory_id':inventory_id,
            'request_id':'primary-org-active-0001'},headers=root)
    # The primary tenant reservation should succeed and must not update any other tenant rows.
    assert created.status_code==201,created.text
    with db.connect() as connection:
        other=connection.execute('SELECT status FROM reservations WHERE id=?',(held,)).fetchone()['status']
        assert other=='held'


def test_commerce_schema_upgrade_is_repeatable_and_preserves_previous_records(site):
    client,root,db=site
    from backend.commerce import ensure_commerce_schema
    import sqlite3
    purchase=sale(site,amount=4275)
    demand,_=prepare_stock_and_demand(site,qty=3)
    with db.connect() as conn:
        before=(conn.execute('SELECT COUNT(*) FROM sales').fetchone()[0],
                conn.execute('SELECT COUNT(*) FROM demand').fetchone()[0],
                conn.execute('SELECT COUNT(*) FROM organizations').fetchone()[0])
        ensure_commerce_schema(conn)
        ensure_commerce_schema(conn)
        conn.commit()
        after=(conn.execute('SELECT COUNT(*) FROM sales').fetchone()[0],
               conn.execute('SELECT COUNT(*) FROM demand').fetchone()[0],
               conn.execute('SELECT COUNT(*) FROM organizations').fetchone()[0])
        assert before==after
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute('SELECT id FROM sales WHERE id=?',(purchase,)).fetchone()
        assert conn.execute('SELECT id FROM demand WHERE id=?',(demand,)).fetchone()


def test_first_r05_startup_upgrades_r04_database_without_erasing_sales(tmp_path,monkeypatch):
    import importlib
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as db
    import backend.app as api
    from backend.imports import ensure_import_schema
    from backend.kiosk import ensure_schema as ensure_kiosk_schema
    from backend.pos_webhook import ensure_schema as ensure_pos_schema
    importlib.reload(db)
    db.initialize_db(demo=False)
    with db.connect() as conn:
        ensure_import_schema(conn)
        ensure_kiosk_schema(conn)
        ensure_pos_schema(conn)
        store_id=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        sale_id=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
           (store_id,742500,'r04-import',db.now_iso(),'r04-original-receipt')).lastrowid
        conn.commit()
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reservations'").fetchone() is None
    importlib.reload(api)
    with TestClient(api.app) as client:
        signed=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert signed.status_code==200,signed.text
        headers={'Authorization':'Bearer '+signed.json()['token']}
        assert client.get('/api/admin/reservations?slug=central',headers=headers).status_code==200
        assert client.get('/api/admin/receipts?slug=central',headers=headers).json()[0]['id']==sale_id
        assert client.get('/api/admin/pricing?slug=central',headers=headers).json()==[]
    with db.connect() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert conn.execute("SELECT amount_kopeks FROM sales WHERE external_id='r04-original-receipt'").fetchone()[0]==742500
