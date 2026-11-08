"""R1.4 independent acceptance of five operational workflows."""
import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_DEMO_MODE','1')
    import backend.database as database
    import backend.app as module
    importlib.reload(database)
    importlib.reload(module)
    with TestClient(module.app) as client:
        yield client,database

def send(client,external='receipt-abc-001',amount=120000,source='qa'):
    return client.post('/api/admin/r14/inbox',json={'slug':'central','source':source,'external_id':external,'kind':'receipt','payload':{'amount_kopeks':amount,'occurred_at':'2026-11-08T12:00:00+00:00'}})

def test_idempotent_inbox_conflict_and_validation(site):
    c,_=site
    x=send(c);assert x.status_code==201,x.text
    assert x.json()['duplicate'] is False
    assert send(c).json()['duplicate'] is True
    assert send(c,amount=130000).status_code==409
    assert send(c,external='zzzz',amount=-1).status_code==422
    assert c.post('/api/admin/r14/inbox',json={'source':'qa','external_id':'s-101','kind':'stock','payload':{'sku':'A1','quantity':2}}).status_code==201

def test_review_one_way(site):
    c,_=site;x=send(c).json()['id']
    r=c.post(f'/api/admin/r14/inbox/{x}/review',json={'status':'reviewed','note':'Проверено оператором'})
    assert r.status_code==200,r.text
    assert c.post(f'/api/admin/r14/inbox/{x}/review',json={'status':'rejected','note':'Повторная проверка'}).status_code==409

def test_reconciliation_matched_conflicts_and_missing(site):
    c,db=site
    send(c,'receipt-1',120000);send(c,'receipt-2',99000);send(c,'receipt-3',10000)
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        for ext,price in [('receipt-1',120000),('receipt-2',70000)]:
            conn.execute("INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)",(store,price,'qa',db.now_iso(),ext))
        conn.commit()
    report=c.get('/api/admin/r14/reconciliation').json()
    assert report['matched']==1 and report['amount_conflicts']==1 and report['missing']==1,report

def test_confirm_gift_and_reverse_is_idempotent(site):
    c,_=site
    data={'slug':'central','reference':'manual-gift-001','campaign':'Открытие','cost_kopeks':42000,'note':'Подтверждено по акту выдачи'}
    x=c.post('/api/admin/r14/gifts',json=data);assert x.status_code==201,x.text
    assert c.post('/api/admin/r14/gifts',json=data).json()['duplicate']
    assert c.post('/api/admin/r14/gifts',json={**data,'cost_kopeks':84000}).status_code==409
    gid=x.json()['id']
    assert c.post(f'/api/admin/r14/gifts/{gid}/reverse?reason=Ошибка%20акта%20выдачи').status_code==200
    assert c.post(f'/api/admin/r14/gifts/{gid}/reverse?reason=Повторная%20отмена').status_code==409
    assert c.get('/api/admin/r14/board').json()['gift_cost_kopeks']==0

def test_incident_lifecycle(site):
    c,_=site;send(c)
    r=c.post('/api/admin/r14/incidents/sync');assert r.status_code==200,r.text
    items=r.json()['items'];assert items
    iid=items[0]['id']
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'resolved','note':'Проверил входящие чеки'}).status_code==409
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'acknowledged','note':'Взял в обработку'}).status_code==200
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'resolved','note':'Дубликаты устранены'}).status_code==200
    assert c.post(f'/api/admin/r14/incidents/{iid}',json={'status':'resolved','note':'Повторная попытка'}).status_code==409

def test_board_and_invalid_window(site):
    c,_=site;send(c)
    result=c.get('/api/admin/r14/board?days=7');assert result.status_code==200,result.text
    assert result.json()['inbox_pending']==1
    assert c.get('/api/admin/r14/board?days=100').status_code==422
    assert c.get('/api/admin/r14/reconciliation?days=0').status_code==422
