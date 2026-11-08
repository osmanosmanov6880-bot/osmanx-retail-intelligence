"""R0.6 E2E acceptance: five financially honest, tenant-scoped workflows."""
import importlib
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE', '0')
    monkeypatch.setenv('OSMANX_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD', 'very-secure-bootstrap-password')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL', 'owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET', 'this-is-a-sufficiently-long-master-session-secret')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET', 'this-is-a-sufficiently-long-master-device-secret')
    from backend import app, database
    importlib.reload(database)
    importlib.reload(app)
    with TestClient(app.app) as c:
        login = c.post('/api/auth/login', json={'email':'owner@osmanx.local', 'password':'very-secure-bootstrap-password'})
        assert login.status_code == 200, login.text
        auth = {'Authorization': 'Bearer ' + login.json()['token']}
        yield c, auth, database


def create_order(c,auth,ref='po-100',quantity=3,sku='XL-BLK'):
    return c.post('/api/admin/workflows/orders',headers=auth,json={
        'slug':'central','supplier':'Тестовый поставщик','reference':ref,
        'lines':[{'sku':sku,'product':'Куртка','size':'XL','color':'чёрный','quantity':quantity,'unit_cost_rub':'1200.50'}]
    })


def test_r06_schema_is_idempotent_and_preexisting_data_survives(site):
    c, auth, db = site
    with db.connect() as conn:
        from backend.workflows import ensure_schema
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                     (sid,'Куртка','XL','чёрный',db.now_iso(),db.now_iso()))
        count=conn.execute('SELECT COUNT(*) FROM demand WHERE store_id=?',(sid,)).fetchone()[0]
        ensure_schema(conn);ensure_schema(conn)
        assert conn.execute('SELECT COUNT(*) FROM demand WHERE store_id=?',(sid,)).fetchone()[0]==count
    assert c.get('/api/admin/workflows/overview?slug=central',headers=auth).status_code==200


def test_demand_case_tracks_verified_receipt_not_inferred_sale(site):
    c, auth, db=site
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        dem=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
              (sid,'Куртка','XL','чёрный',db.now_iso(),db.now_iso())).lastrowid
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
              (sid,650000,'test',db.now_iso(),'verified-001')).lastrowid
        conn.commit()
    r=c.post('/api/admin/workflows/cases',headers=auth,json={'slug':'central','demand_id':dem,'sku':'XL-BLK'})
    assert r.status_code==201,r.text
    cid=r.json()['id']
    assert c.post('/api/admin/workflows/cases',headers=auth,json={'slug':'central','demand_id':dem,'sku':'XL-BLK'}).status_code==409
    assert c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'convert','sale_id':sale}).status_code==422
    item=c.post('/api/admin/workflows/sale-items',headers=auth,json={'slug':'central','sale_id':sale,
        'sku':'XL-BLK','quantity':1,'unit_revenue_rub':'6500','unit_cost_rub':'3000', 'external_id':'sale-line-verify'})
    assert item.status_code==201,item.text
    confirmed=c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'convert','sale_id':sale})
    assert confirmed.status_code==200, confirmed.text
    with db.connect() as conn:
        row=conn.execute('SELECT status,sale_id FROM demand WHERE id=?',(dem,)).fetchone()
        assert dict(row)=={'status':'converted','sale_id':sale}
        history=conn.execute('SELECT previous_status,next_status FROM demand_history WHERE demand_id=? ORDER BY id DESC',(dem,)).fetchone()
        assert tuple(history)==('open','converted')
    overview=c.get('/api/admin/workflows/overview',headers=auth).json()
    assert overview['cases'][0]['status']=='converted'
    assert c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'convert','sale_id':sale}).status_code==409


def test_purchase_order_is_atomic_partial_idempotent_and_updates_real_stock(site):
    c, auth, db=site
    created=create_order(c,auth)
    assert created.status_code==201,created.text
    order_id=created.json()['id']
    assert create_order(c,auth).status_code==409
    overview=c.get('/api/admin/workflows/overview',headers=auth).json()
    line_id=overview['orders'][0]['lines'][0]['id']
    assert c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json={
           'external_id':'delivery-1','lines':[{'line_id':line_id,'quantity':1}]}).status_code==409
    assert c.patch(f'/api/admin/workflows/orders/{order_id}',headers=auth,json={'status':'ordered'}).status_code==200
    assert c.patch(f'/api/admin/workflows/orders/{order_id}',headers=auth,json={'status':'ordered'}).status_code==409
    data={'external_id':'delivery-1','lines':[{'line_id':line_id,'quantity':1}]}
    first=c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json=data)
    assert first.status_code==201,first.text
    assert first.json()['status']=='partial'
    again=c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json=data)
    assert again.status_code==201 and again.json()['duplicate'] is True
    assert c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json={
        **data,'lines':[{'line_id':line_id,'quantity':2}]}).status_code==409
    assert c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json={
        'external_id':'over-delivery','lines':[{'line_id':line_id,'quantity':3}]}).status_code==409
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        stock=conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(sid,'XL-BLK')).fetchone()['quantity']
        assert stock==1
    second=c.post(f'/api/admin/workflows/orders/{order_id}/receipts',headers=auth,json={
        'external_id':'delivery-2','lines':[{'line_id':line_id,'quantity':2}]})
    assert second.status_code==201 and second.json()['status']=='received'
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        assert conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(sid,'XL-BLK')).fetchone()['quantity']==3
        assert conn.execute('SELECT SUM(delta) FROM stock_movements WHERE store_id=?',(sid,)).fetchone()[0]==3
    assert c.patch(f'/api/admin/workflows/orders/{order_id}',headers=auth,json={'status':'cancelled'}).status_code==409


def test_case_can_link_to_order_then_verified_sale(site):
    c,auth,db=site
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        did=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                         (sid,'Куртка','XL','чёрный',db.now_iso(),db.now_iso())).lastrowid
        conn.commit()
    order=create_order(c,auth,ref='case-test').json()['id']
    assert c.patch(f'/api/admin/workflows/orders/{order}',headers=auth,json={'status':'ordered'}).status_code==200
    line=c.get('/api/admin/workflows/overview',headers=auth).json()['orders'][0]['lines'][0]['id']
    cid=c.post('/api/admin/workflows/cases',headers=auth,json={'slug':'central','demand_id':did,'sku':'XL-BLK'}).json()['id']
    assert c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'order','order_line_id':line}).status_code==200
    assert c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'convert','sale_id':999999}).status_code==422


def test_sale_item_requires_real_receipt_and_caps_amount_and_precision(site):
    c,auth,db=site
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
             (sid,100050,'test',db.now_iso(),'receipt-item-1')).lastrowid
        conn.commit()
    body={'slug':'central','sale_id':sale,'sku':'XL-BLK','quantity':2,'unit_revenue_rub':'500.25',
          'unit_cost_rub':'200.10','external_id':'sale-line-1'}
    created=c.post('/api/admin/workflows/sale-items',headers=auth,json=body)
    assert created.status_code==201,created.text
    assert created.json()['documented_margin_kopeks']==60030
    assert c.post('/api/admin/workflows/sale-items',headers=auth,json=body).status_code==409
    assert c.post('/api/admin/workflows/sale-items',headers=auth,json={**body,'external_id':'another-item'}).status_code==409
    overview=c.get('/api/admin/workflows/overview',headers=auth).json()
    assert overview['finance']['documented_revenue_kopeks']==100050
    assert overview['finance']['documented_gross_margin_kopeks']==60030
    assert 'before' not in overview['status'].lower()
    assert c.post('/api/admin/workflows/sale-items',headers=auth,json={**body,'sale_id':999999}).status_code==422


def test_comparison_uses_dates_sources_and_disclaims_causality(site):
    c,auth,db=site
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        did=conn.execute('INSERT INTO experiments(store_id,title,hypothesis,metric,created_at,updated_at) VALUES(?,?,?,?,?,?)',
          (sid,'Тест XL','Вещи XL вернут покупателей','conversion',db.now_iso(),db.now_iso())).lastrowid
        today=datetime.now(timezone.utc).date()
        dates=[today-timedelta(days=3),today-timedelta(days=2)]
        for day,counts,orders in [(dates[0],10,2),(dates[1],20,6)]:
            stamp=day.isoformat()+'T12:00:00+00:00'
            conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                         (sid,counts,'manual',stamp,'r06-'+day.isoformat()))
            for i in range(orders):
                conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                             (sid,200000,'test',stamp,'r06-sale-'+day.isoformat()+str(i)))
        conn.commit()
    body={'slug':'central','experiment_id':did,'metric':'conversion','source_mode':'manual',
          'before_start':dates[0].isoformat(),'before_end':dates[0].isoformat(),
          'after_start':dates[1].isoformat(),'after_end':dates[1].isoformat(),
          'notes':'No causal claim'}
    r=c.post('/api/admin/workflows/evaluations',headers=auth,json=body)
    assert r.status_code==201,r.text
    assert r.json()['before_value']==20.0 and r.json()['after_value']==30.0
    assert r.json()['delta']==10.0
    assert 'не доказывает' in r.json()['disclaimer']
    assert c.post('/api/admin/workflows/evaluations',headers=auth,json={**body,
           'after_start':dates[0].isoformat()}).status_code==422
    assert c.get('/api/admin/workflows/overview',headers=auth).json()['evaluations'][0]['metric']=='conversion'


def test_tenant_data_access_roles_and_csv_injection(site):
    c,auth,db=site
    from scripts.provision_tenant import provision
    with db.connect() as conn:
        provision(conn,slug='other-tenant',name='Another retailer',store_slug='outside',
                  email='outside@example.test',password='other-tenant-strong-password')
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        dem=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
              (sid,'=1+1','XL','black',db.now_iso(),db.now_iso())).lastrowid
        conn.commit()
    outside_token=c.post('/api/auth/login',json={'email':'outside@example.test','password':'other-tenant-strong-password'}).json()['token']
    outside={'Authorization':'Bearer '+outside_token}
    assert c.get('/api/admin/workflows/overview').status_code==401
    assert c.get('/api/admin/workflows/overview?slug=outside',headers=auth).status_code==404
    assert c.get('/api/admin/workflows/overview?slug=central',headers=outside).status_code==404
    assert c.post('/api/admin/workflows/cases',headers=outside,json={'slug':'outside','demand_id':dem,'sku':'XL-BLK'}).status_code==404
    order=create_order(c,auth,ref='legal-1')
    assert order.status_code==201
    oid=order.json()['id']
    assert c.patch(f'/api/admin/workflows/orders/{oid}',headers=outside,json={'status':'ordered'}).status_code==404
    resp=c.get('/api/admin/workflows/export?slug=central&dataset=orders',headers=auth)
    assert resp.status_code==200 and resp.headers['content-type'].startswith('text/csv')
    assert 'legal-1' in resp.text
    resp2=c.get('/api/admin/workflows/export?slug=outside&dataset=orders',headers=auth)
    assert resp2.status_code==404
    # CSV spreadsheet formula payload must be neutralized.
    r=c.post('/api/admin/workflows/cases',headers=auth,json={'slug':'central','demand_id':dem,'sku':'=HYPERLINK("x")'})
    assert r.status_code==201
    csv_text=c.get('/api/admin/workflows/export?dataset=cases',headers=auth).text
    assert "'=HYPERLINK" in csv_text


def test_receipt_race_is_idempotent(site):
    c,auth,db=site
    oid=create_order(c,auth,ref='race-test',quantity=2).json()['id']
    line=c.get('/api/admin/workflows/overview',headers=auth).json()['orders'][0]['lines'][0]['id']
    assert c.patch(f'/api/admin/workflows/orders/{oid}',headers=auth,json={'status':'ordered'}).status_code==200
    payload={'external_id':'only-1','lines':[{'line_id':line,'quantity':2}]}
    def post(_):return c.post(f'/api/admin/workflows/orders/{oid}/receipts',headers=auth,json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(post,range(2)))
    assert all(r.status_code==201 for r in responses),[(r.status_code,r.text) for r in responses]
    assert sorted(r.json()['duplicate'] for r in responses)==[False,True]
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',('central',)).fetchone()['id']
        assert conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(sid,'XL-BLK')).fetchone()['quantity']==2
