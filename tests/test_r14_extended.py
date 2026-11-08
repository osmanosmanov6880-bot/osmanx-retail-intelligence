"""R1.4 release gate: idempotency, matching, linked costs, tenant isolation, evidence."""
from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','1')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    import backend.database as database
    import backend.app as api
    importlib.reload(database);importlib.reload(api)
    with TestClient(api.app) as client:
        yield client,database


def packet(client,external='receipt-001',amount=10000,source='integration'):
    return client.post('/api/admin/r14/inbox',json={'slug':'central','source':source,
        'external_id':external,'kind':'receipt',
        'payload':{'amount_kopeks':amount,'occurred_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}})


def test_invoice_input_requires_timezone_and_rejects_hidden_personal_data(site):
    c,_=site
    base={'slug':'central','source':'pos-v1','external_id':'receipt-abc','kind':'receipt',
         'payload':{'amount_kopeks':1200,'occurred_at':'2026-11-08T12:00:00'}}
    assert c.post('/api/admin/r14/inbox',json=base).status_code==422
    assert c.post('/api/admin/r14/inbox',json={**base,'payload':{**base['payload'],'occurred_at':'nonsense'}}).status_code==422
    assert c.post('/api/admin/r14/inbox',json={**base,'payload':{**base['payload'],'buyer_email':'private@invalid.test'}}).status_code==422
    assert c.post('/api/admin/r14/inbox',json={**base,'payload':{**base['payload'],'amount_kopeks':True}}).status_code==422
    assert c.post('/api/admin/r14/inbox',json={**base,'payload':{**base['payload'],'occurred_at':'2026-11-08T12:00:00+03:00'}}).status_code==201


def test_stock_event_limits_and_duplicate_is_stable(site):
    c,_=site
    x={'slug':'central','source':'erp-1','external_id':'stock-1','kind':'stock','payload':{'sku':'COAT-1','quantity':0}}
    a=c.post('/api/admin/r14/inbox',json=x)
    assert a.status_code==201,a.text
    assert c.post('/api/admin/r14/inbox',json=x).json()['duplicate'] is True
    assert c.post('/api/admin/r14/inbox',json={**x,'payload':{**x['payload'],'quantity':12}}).status_code==409
    assert c.post('/api/admin/r14/inbox',json={**x,'external_id':'stock-2','payload':{'sku':'COAT-1','quantity':-2}}).status_code==422


def test_atomic_duplicate_concurrency(site):
    c,db=site
    def send(_):return packet(c,external='race-receipt-101')
    with ThreadPoolExecutor(max_workers=5) as pool:res=list(pool.map(send,range(5)))
    assert all(r.status_code==201 for r in res),[r.text for r in res]
    ids={r.json()['id'] for r in res}
    assert len(ids)==1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM r14_inbox WHERE external_id='race-receipt-101'").fetchone()[0]==1


def test_reconciliation_detailed_and_export_safe(site):
    c,db=site
    first=packet(c,'receipt-one',10000,'source-1');assert first.status_code==201
    packet(c,'receipt-two',40000,'source-1');packet(c,'receipt-three',20000,'source-1')
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        for external,cost in [('receipt-one',10000),('receipt-two',50000)]:
            conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                  (sid,cost,'source-1',datetime.now(timezone.utc).isoformat(timespec='seconds'),external))
        conn.commit()
    summary=c.get('/api/admin/r14/reconciliation').json()
    assert (summary['matched'],summary['amount_conflicts'],summary['missing'])==(1,1,1)
    detail=c.get('/api/admin/r14/reconciliation/items').json()
    assert detail['total']==3 and {x['comparison'] for x in detail['items']}=={'matched','missing','amount_conflict'}
    download=c.get('/api/admin/r14/reconciliation/export.csv')
    assert download.status_code==200 and download.text.startswith('\ufeff') and 'receipt-three' in download.text
    assert c.get('/api/admin/r14/reconciliation/items?days=0').status_code==422


def test_gift_cost_manual_vs_linked_proof_and_no_double_count(site):
    c,db=site
    from backend.r11 import ensure_schema as ensure_r11
    from backend.r12 import ensure_schema as ensure_r12
    with db.connect() as conn:
        ensure_r11(conn);ensure_r12(conn)
        st=conn.execute("SELECT id,organization_id FROM stores WHERE slug='central'").fetchone()
        org,sid=st['organization_id'],st['id']
        camp=conn.execute('''INSERT INTO campaigns_r11(organization_id,store_id,title,reward_description,unit_cost_kopeks,budget_kopeks,max_claims,
             min_spend_kopeks,starts_on,ends_on,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
             (org,sid,'Открытие','Небольшой подарок',5400,54000,10,0,'2026-10-01','2027-01-31',db.now_iso())).lastrowid
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                          (sid,140000,'pos',db.now_iso(),'proof-receipt-1')).lastrowid
        claim=conn.execute('''INSERT INTO campaign_claims_r11(organization_id,campaign_id,member_id,coupon_sha256,status,sale_id,issued_at,redeemed_at)
              VALUES(?,?,?,?,?,?,?,?)''',(org,camp,None,'sample-claim-hash','redeemed',sale,db.now_iso(),db.now_iso())).lastrowid
        conn.execute('''INSERT INTO coupon_fulfillments_r12(organization_id,store_id,claim_id,proof_reference,note,recorded_at)
              VALUES(?,?,?,?,?,?)''',(org,sid,claim,'evidence-001','Акт выдачи',db.now_iso()))
        conn.commit()
    manual={'slug':'central','reference':'manual-001','campaign':'Рекламная акция','cost_kopeks':1000,'note':'Проверен первичный документ'}
    response=c.post('/api/admin/r14/gifts',json=manual)
    assert response.status_code==201
    assert response.json()['evidence_level']=='manual_entry'
    valid={'slug':'central','reference':'evidence-001','campaign':'Открытие','cost_kopeks':5400,
           'note':'Подписанный акт выдачи','coupon_claim_id':claim}
    linked=c.post('/api/admin/r14/gifts',json=valid)
    assert linked.status_code==201,linked.text
    assert linked.json()['evidence_level']=='linked_coupon_proof'
    assert c.post('/api/admin/r14/gifts',json=valid).json()['duplicate'] is True
    assert c.post('/api/admin/r14/gifts',json={**valid,'reference':'wrong-ref-002'}).status_code==422
    costs=c.get('/api/admin/r14/board').json()
    assert costs['gift_cost_kopeks']==6400
    assert costs['gift_evidence']['manual']==1 and costs['gift_evidence']['linked']==1
    assert c.post(f"/api/admin/r14/gifts/{linked.json()['id']}/reverse?reason=Акт%20ошибочен").status_code==200
    assert c.get('/api/admin/r14/board').json()['gift_cost_kopeks']==1000


def test_incident_stable_fingerprint_history_reopening(site):
    c,db=site
    packet(c,external='missing-001')
    first=c.post('/api/admin/r14/incidents/sync').json()['items']
    assert len(first)==2  # pending and missing
    second=c.post('/api/admin/r14/incidents/sync').json()['items']
    assert {x['id'] for x in first}=={x['id'] for x in second}
    missing=next(x for x in first if 'Кассовые' in x['title'])
    iid=missing['id']
    h=c.get(f'/api/admin/r14/incidents/{iid}/history').json()['items']
    assert [x['next_status'] for x in h]==['open']
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'acknowledged','note':'Назначена проверка'}).status_code==200
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'resolved','note':'Проверка выполнена'}).status_code==200
    c.post('/api/admin/r14/incidents/sync')
    h=c.get(f'/api/admin/r14/incidents/{iid}/history').json()['items']
    assert [x['next_status'] for x in h]==['open','acknowledged','resolved','open']


def test_board_export_clearly_separates_manual_evidence(site):
    c,_=site
    data={'slug':'central','reference':'gift-123','campaign':'Тест','cost_kopeks':700,'note':'Ручной акт выдачи'}
    assert c.post('/api/admin/r14/gifts',json=data).status_code==201
    x=c.get('/api/admin/r14/board').json()
    assert x['gift_evidence']['manual']==1
    assert 'вручную' in ' '.join(x['warnings'])
    csv=c.get('/api/admin/r14/board/export.csv')
    assert csv.status_code==200 and 'gift_cost_kopeks' in csv.text
    assert c.get('/api/admin/r14/board?days=100').status_code==422


def test_non_demo_requires_authorization(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','temporary-development-password-123')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','temporary-secure-session-test-secret-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-for-local-test-012345')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','test-owner@osmanx.local')
    import backend.app as api
    import backend.database as database
    importlib.reload(database);importlib.reload(api)
    with TestClient(api.app) as c:
        for path in ['/api/admin/r14/inbox','/api/admin/r14/board','/api/admin/r14/board/export.csv']:
            assert c.get(path).status_code==401
        assert c.post('/api/admin/r14/gifts',json={'slug':'central','reference':'ref123','campaign':'open','cost_kopeks':1000,'note':'test'}).status_code==401
