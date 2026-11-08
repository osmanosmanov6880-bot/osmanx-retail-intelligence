"""R0.8 acceptance: five real workflows, tenant scope and safe uncertainty labels."""
import importlib
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r08-bootstrap-password-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r08-session-master-secret-123456789000')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r08-device-master-secret-123456789000')
    import backend.database as database
    import backend.app as app
    importlib.reload(database)
    importlib.reload(app)
    with TestClient(app.app) as client:
        auth=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r08-bootstrap-password-2026'})
        assert auth.status_code==200,auth.text
        yield client,{'Authorization':'Bearer '+auth.json()['token']},database


def demand_and_stock(site,product='Пальто',size='L',sku='COAT-L',stock=0):
    c,h,db=site
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                     (store,sku,product,size,'чёрный',stock,'manual',db.now_iso()))
        for _ in range(4):
            conn.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                         (store,product,size,'чёрный','open',db.now_iso(),db.now_iso()))
        conn.commit()
    return store


def post(c,h,url,payload):
    return c.post('/api/admin/r08/'+url,json=payload,headers=h)


def get(c,h,url):
    return c.get('/api/admin/r08/'+url,headers=h)


def test_all_modules_require_authenticated_session(site):
    c,_,_=site
    for part in ['replenishment/preview','replenishment','suppliers','fittings','tasks','brief','brief/snapshots']:
        assert c.get('/api/admin/r08/'+part).status_code==401,part
    for part in ['replenishment','suppliers/review','fittings/actions','tasks','brief/snapshot']:
        assert c.post('/api/admin/r08/'+part,json={}).status_code==401,part


def test_replenishment_preview_plan_draft_order_and_idempotence(site):
    c,h,db=site
    demand_and_stock(site)
    preview=get(c,h,'replenishment/preview').json()
    assert preview['total_requests']==4 and preview['total_unresolved']==0
    assert preview['lines'][0]['sku']=='COAT-L' and preview['lines'][0]['recommended_qty']==4
    p={'slug':'central','period_days':30,'safety_units':1,'request_id':'R08-RESTOCK-1'}
    first=post(c,h,'replenishment',p);assert first.status_code==201,first.text
    assert first.json()['lines']==1
    assert post(c,h,'replenishment',p).json()['duplicate'] is True
    assert post(c,h,'replenishment',{**p,'safety_units':2}).status_code==409
    plan=first.json()['id']
    assert get(c,h,'replenishment').json()['items'][0]['lines'][0]['recommended_qty']==5
    impossible=post(c,h,f'replenishment/{plan}/order',{'supplier':'Текстиль','reference':'REF-1','costs':[{'sku':'WRONG','unit_cost_rub':'2500.00'}]})
    assert impossible.status_code==422
    assert post(c,h,f'replenishment/{plan}/order',{'supplier':'Текстиль','reference':'REF-0','costs':[{'sku':'COAT-L','unit_cost_rub':'0.00'}]}).status_code==422
    payload={'supplier':'Текстиль','reference':'REF-1','expected_date':(date.today()+timedelta(days=10)).isoformat(),
             'costs':[{'sku':'COAT-L','unit_cost_rub':'2500.00'}]}
    made=post(c,h,f'replenishment/{plan}/order',payload)
    assert made.status_code==201,made.text
    assert not made.json()['duplicate']
    again=post(c,h,f'replenishment/{plan}/order',payload).json();assert again['duplicate'] and again['id']==made.json()['id']
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM purchase_orders WHERE id=?',(made.json()['id'],)).fetchone()['status']=='draft'
        line=conn.execute('SELECT ordered_qty,unit_cost_kopeks FROM purchase_order_lines WHERE order_id=?',(made.json()['id'],)).fetchone()
        assert (line['ordered_qty'],line['unit_cost_kopeks'])==(5,250000)
        assert conn.execute('SELECT quantity FROM inventory WHERE sku=?',('COAT-L',)).fetchone()[0]==0


def test_unresolved_sku_is_never_invented(site):
    c,h,db=site
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        conn.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
          (sid,'Пальто неизвестное','XXL','белый','open',db.now_iso(),db.now_iso()))
        conn.commit()
    report=get(c,h,'replenishment/preview').json()
    assert report['total_unresolved']==1 and report['lines']==[]
    r=post(c,h,'replenishment',{'request_id':'R08-NO-SKU-1'})
    assert r.status_code==422


def test_supplier_card_handles_small_samples_and_reviews(site):
    c,h,db=site
    sid=demand_and_stock(site)
    expected=(date.today()-timedelta(days=3)).isoformat()
    with db.connect() as conn:
        order=conn.execute('INSERT INTO purchase_orders(organization_id,store_id,supplier,reference,status,expected_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (1,sid,'Фабрика Икс','r08-late-order','ordered',expected,db.now_iso(),db.now_iso())).lastrowid
        conn.execute('INSERT INTO purchase_order_lines(order_id,sku,product,ordered_qty,unit_cost_kopeks) VALUES(?,?,?,?,?)',
            (order,'COAT-L','Пальто',3,100000))
        conn.commit()
    data=get(c,h,'suppliers').json()['items'][0]
    assert data['supplier']=='Фабрика Икс' and data['overdue_open']==1 and data['outstanding_units']==3
    assert data['on_time_percent'] is None
    r=post(c,h,'suppliers/review',{'slug':'central','supplier':'Фабрика Икс','rating':2,'issue':'Нарушены сроки поставки'})
    assert r.status_code==201,r.text
    assert get(c,h,'suppliers').json()['items'][0]['reviews'][0]['rating']==2
    assert post(c,h,'suppliers/review',{'supplier':'Несуществующий','rating':5}).status_code==422


def test_fitting_insights_and_evidenced_action(site):
    c,h,db=site
    sid=demand_and_stock(site)
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fitting_observations'").fetchone():
            conn.execute('INSERT INTO fitting_observations(store_id,product,size,trials,purchases,reason,observed_at,created_at) VALUES(?,?,?,?,?,?,?,?)',
                  (sid,'Пальто','L',10,1,'fit',db.now_iso(),db.now_iso()))
        else:
            conn.execute('INSERT INTO fittings(organization_id,store_id,sku,quantity,outcome,reason,occurred_at) VALUES(?,?,?,?,?,?,?)',
                  (1,sid,'COAT-L',10,'not_purchased','fit',db.now_iso()))
        conn.commit()
    data=get(c,h,'fittings').json();assert data['items'][0]['signal']=='needs_review'
    r=post(c,h,'fittings/actions',{'product':'Пальто','size':'L','hypothesis':'Проверить посадку на примерках'})
    assert r.status_code==201,r.text
    a=r.json()['id']
    assert c.patch(f'/api/admin/r08/fittings/actions/{a}',headers=h,json={'status':'done','evidence':'нет'}).status_code==422
    assert c.patch(f'/api/admin/r08/fittings/actions/{a}',headers=h,json={'status':'testing'}).status_code==200
    assert c.patch(f'/api/admin/r08/fittings/actions/{a}',headers=h,json={'status':'done','evidence':'Проверена посадка на 10 примерках'}).status_code==200
    assert c.patch(f'/api/admin/r08/fittings/actions/{a}',headers=h,json={'status':'testing'}).status_code==409


def test_tasks_idempotence_evidence_and_scoping(site):
    c,h,db=site
    task={'request_id':'R08-TASK-ONE','title':'Сверить товар у поставщика','category':'supplier','slug':'central'}
    r=post(c,h,'tasks',task);assert r.status_code==201,r.text
    tid=r.json()['id']
    assert post(c,h,'tasks',task).json()['duplicate'] is True
    assert post(c,h,'tasks',{**task,'title':'Другое действие'}).status_code==409
    assert c.patch(f'/api/admin/r08/tasks/{tid}',headers=h,json={'status':'done','evidence':'нет'}).status_code==422
    assert c.patch(f'/api/admin/r08/tasks/{tid}',headers=h,json={'status':'in_progress'}).status_code==200
    assert c.patch(f'/api/admin/r08/tasks/{tid}',headers=h,json={'status':'done','evidence':'Сверены остатки по накладной №123'}).status_code==200
    assert get(c,h,'tasks').json()['items'][0]['status']=='done'
    assert c.patch(f'/api/admin/r08/tasks/{tid}',headers=h,json={'status':'done','evidence':'Повторная попытка'}).status_code==409
    with db.connect() as conn:
        conn.execute("INSERT INTO organizations(slug,name,created_at) VALUES('other-org','Чужая',?)",(db.now_iso(),))
        other=conn.execute("SELECT id FROM organizations WHERE slug='other-org'").fetchone()[0]
        conn.execute("INSERT INTO stores(slug,name,organization_id,created_at) VALUES('other-r08','Чужой магазин',?,?)",(other,db.now_iso()))
        conn.commit()
    assert get(c,h,'tasks?slug=other-r08').status_code==404
    assert get(c,h,'brief?slug=other-r08').status_code==404
    assert post(c,h,'replenishment',{'slug':'other-r08','request_id':'R08-OTHER-1'}).status_code==404


def test_daily_brief_snapshots_csv_and_no_double_count_claim(site):
    c,h,db=site
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        now=db.now_iso()
        conn.execute("INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)",(sid,7,'manual',now,'r08-v1'))
        conn.execute("INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)",(sid,10,'sensor',now,'r08-v2'))
        conn.execute("INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)",(sid,220000,'pos',now,'r08-s1'))
        conn.commit()
    d=get(c,h,'brief').json()
    assert d['visitors']==17 and d['revenue_kopeks']==220000 and d['purchases']==1
    assert any('двойное' in x.lower() for x in d['warnings'])
    x=post(c,h,'brief/snapshot?slug=central',{});assert x.status_code==201,x.text
    y=post(c,h,'brief/snapshot?slug=central',{});assert y.status_code==201 and y.json()['duplicate']
    assert y.json()['saved_sha256']==x.json()['saved_sha256']
    csv=c.get('/api/admin/r08/brief/export.csv',headers=h)
    assert csv.status_code==200 and csv.text.startswith('\ufeff') and 'Выручка' in csv.text
    assert len(get(c,h,'brief/snapshots').json()['items'])==1
    assert get(c,h,'brief?day=2050-01-01').status_code==422
