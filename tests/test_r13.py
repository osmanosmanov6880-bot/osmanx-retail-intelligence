"""R1.3 acceptance: merchant CSV, quality, demand, stock diagnostics and action board."""
import importlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r13-bootstrap-password-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r13-session-master-secret-123456789000')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r13-device-master-secret-123456789000')
    import backend.database as db
    import backend.app as app
    importlib.reload(db);importlib.reload(app)
    with TestClient(app.app) as c:
        auth=c.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r13-bootstrap-password-2026'})
        assert auth.status_code==200,auth.text
        yield c,{'Authorization':'Bearer '+auth.json()['token']},db


def get(site,path):
    c,h,_=site;return c.get('/api/admin/r13'+path,headers=h)


def post(site,path,payload):
    c,h,_=site;return c.post('/api/admin/r13'+path,json=payload,headers=h)


def create_stock(site,sku='JACKET-XL',product='Куртка',size='XL',color='чёрный',qty=3,slug='central'):
    _,_,db=site
    with db.connect() as conn:
        sid=conn.execute('SELECT id FROM stores WHERE slug=?',(slug,)).fetchone()['id']
        conn.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                     (sid,sku,product,size,color,qty,'manual',db.now_iso()))
        conn.commit()
        return sid


def add_demand(site,sid,count=3,product='Куртка',size='XL',color='чёрный'):
    _,_,db=site
    with db.connect() as conn:
        for _ in range(count):
            conn.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                         (sid,product,size,color,'open',db.now_iso(),db.now_iso()))
        conn.commit()


def test_r13_all_routes_need_auth(site):
    c,_,_=site
    for path in ('/quality','/demand','/stock','/findings','/actions'):
        assert c.get('/api/admin/r13'+path).status_code==401
    assert c.post('/api/admin/r13/csv/preview',json={}).status_code==401
    assert c.post('/api/admin/r13/actions',json={}).status_code==401


def test_csv_inventory_semicolon_russian_preview_commit_idempotent(site):
    text='Артикул;Наименование;Размер;Цвет;Остаток\nCOAT-L;Пальто;L;бежевый;5\nCOAT-XL;Пальто;XL;чёрный;0\n'
    r=post(site,'/csv/preview',{'slug':'central','kind':'inventory','csv_text':text})
    assert r.status_code==201,r.text
    data=r.json();assert data['preview']['added']==2 and data['csv']['rows']==2
    key=data['batch_key']
    assert get(site,'/stock').json()['items']==[]
    first=post(site,'/csv/commit',{'batch_key':key})
    assert first.status_code==200,first.text
    assert first.json()['applied'] and not first.json()['already_applied']
    again=post(site,'/csv/commit',{'batch_key':key})
    assert again.status_code==200 and again.json()['already_applied']
    with site[2].connect() as db:
        assert db.execute("SELECT quantity FROM inventory WHERE sku='COAT-L'").fetchone()[0]==5
        assert db.execute("SELECT COUNT(*) FROM inventory WHERE sku='COAT-L'").fetchone()[0]==1
    assert get(site,'/stock').json()['total_positions']==1


def test_csv_receipts_converts_store_time_and_decimal(site):
    text='Номер чека;Сумма;Дата и время\nR001;1 299,50;01.11.2026 14:30\n'
    r=post(site,'/csv/preview',{'slug':'central','kind':'pos','csv_text':text})
    assert r.status_code==201,r.text
    assert r.json()['csv']['sample'][0]['amount_rub']=='1299.50'
    assert post(site,'/csv/commit',{'batch_key':r.json()['batch_key']}).status_code==200
    with site[2].connect() as db:
        row=db.execute("SELECT * FROM sales WHERE external_id='R001'").fetchone()
        assert row['amount_kopeks']==129950
        assert datetime.fromisoformat(row['occurred_at']).utcoffset()==timedelta(0)


@pytest.mark.parametrize('csv_text',[
  'Артикул;Наименование;Остаток\nA-01;Пальто;-1',
  'Артикул;Наименование;Остаток\nA-01;Пальто;1\nA-01;Пальто;3',
  'Артикул;Наименование;Остаток\nA-01;Пальто;not-a-number',
  'Код;Артикул;Наименование;Остаток\nA-01;A-01;Пальто;1',
  'Артикул;Наименование;Остаток\nA-01;Пальто;1;BROKEN',
])
def test_csv_invalid_rows_never_partially_commit(site,csv_text):
    before=get(site,'/stock').json()['total_positions']
    result=post(site,'/csv/preview',{'slug':'central','kind':'inventory','csv_text':csv_text})
    assert result.status_code==422,result.text
    assert get(site,'/stock').json()['total_positions']==before


def test_csv_commit_requires_matching_preview(site):
    text='Артикул;Наименование;Остаток\nSK-1;Куртка;10\n'
    r=post(site,'/csv/preview',{'slug':'central','kind':'inventory','csv_text':text})
    assert r.status_code==201,r.text
    create_stock(site,sku='SK-1',qty=1)
    result=post(site,'/csv/commit',{'batch_key':r.json()['batch_key']})
    assert result.status_code==409
    with site[2].connect() as db:
        assert db.execute("SELECT quantity FROM inventory WHERE sku='SK-1'").fetchone()[0]==1


def test_quality_separates_sources_and_requires_item_coverage(site):
    _,_,db=site
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        for source in ['manual','sensor-a']:
            conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                         (sid,10,source,db.now_iso(),uuid.uuid4().hex))
        sale_id=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                             (sid,350000,'pos_import',db.now_iso(),'C-1')).lastrowid
        conn.commit()
    r=get(site,'/quality').json()
    assert any(x['key']=='mixed_sources' for x in r['flags'])
    assert r['receipt_coverage']['missing_items']==1
    with db.connect() as conn:
        conn.execute('INSERT INTO sale_items(organization_id,store_id,sale_id,sku,quantity,unit_revenue_kopeks,unit_cost_kopeks,external_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (1,sid,sale_id,'C-1',1,150000,50000,'L1',db.now_iso()))
        conn.commit()
    after=get(site,'/quality').json()
    assert after['receipt_coverage']['mismatched']==1


def test_demand_matrix_respects_held_and_ambiguous_skus(site):
    sid=create_stock(site,qty=1)
    add_demand(site,sid,3)
    one=get(site,'/demand').json()
    assert one['request_count']==3
    assert one['items'][0]['sku']=='JACKET-XL' and one['items'][0]['available_local']==1
    create_stock(site,sku='JACKET-XL-B',qty=3)
    two=get(site,'/demand').json()['items'][0]
    assert two['sku'] is None and two['signal']=='verify_sku'


def test_stock_health_no_profit_claim_and_known_cost_coverage(site):
    sid=create_stock(site,qty=4)
    health=get(site,'/stock').json()
    assert health['total_stock_cost_kopeks'] is None
    assert health['positions_without_known_cost']==1
    assert health['items'][0]['signal']=='no_recorded_sales'
    _,_,db=site
    with db.connect() as conn:
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                          (sid,500000,'pos',db.now_iso(),'B-1')).lastrowid
        conn.execute('INSERT INTO sale_items(organization_id,store_id,sale_id,sku,quantity,unit_revenue_kopeks,unit_cost_kopeks,external_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)',
                     (1,sid,sale,'JACKET-XL',1,500000,230000,'B-1-L1',db.now_iso()))
        conn.commit()
    report=get(site,'/stock').json()
    assert report['valued_known_stock_kopeks']==4*230000
    assert report['items'][0]['sold_units']==1


def test_findings_create_action_idempotent_versioned_evidence_and_csv(site):
    sid=create_stock(site,qty=3)
    add_demand(site,sid,3)
    found=get(site,'/findings').json()['items']
    assert found
    candidate=next(x for x in found if x['source']=='stock')
    payload={'slug':'central','source':candidate['source'],'signal_key':candidate['key'],'request_id':'R13-UNIQUE-REQUEST-1234'}
    one=post(site,'/actions',payload)
    assert one.status_code==201,one.text
    assert len(one.json()['evidence_sha256'])==64
    assert post(site,'/actions',payload).json()['duplicate']
    assert post(site,'/actions',{**payload,'signal_key':'another'}).status_code==409
    action=one.json()['id']
    c,h,db=site
    assert c.patch(f'/api/admin/r13/actions/{action}',headers=h,json={'version':1,'status':'resolved','result_note':'short'}).status_code==422
    done=c.patch(f'/api/admin/r13/actions/{action}',headers=h,json={'version':1,'status':'resolved','result_note':'Проверено вручную: требуется дополнительный сбор данных'} )
    assert done.status_code==200,done.text
    assert c.patch(f'/api/admin/r13/actions/{action}',headers=h,json={'version':1,'status':'testing'}).status_code==409
    assert get(site,'/actions').json()['items'][0]['status']=='resolved'
    export=c.get('/api/admin/r13/actions.csv',headers=h)
    assert export.status_code==200 and 'text/csv' in export.headers['content-type']
    with db.connect() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT COUNT(*) FROM control_actions_r13').fetchone()[0]==1


def test_user_store_isolation_across_organizations(site):
    c,h,db=site
    with db.connect() as conn:
        from backend.security import hash_password
        conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('other','Другая организация',db.now_iso()))
        org=conn.execute("SELECT id FROM organizations WHERE slug='other'").fetchone()[0]
        conn.execute('INSERT INTO stores(slug,name,organization_id,created_at) VALUES(?,?,?,?)',('other-shop','Тестовый магазин',org,db.now_iso()))
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (org,'other@osmanx.local',hash_password('another-strong-password-2026'),'owner',db.now_iso()))
        conn.commit()
    assert get(site,'/quality?slug=other-shop').status_code==404
    assert post(site,'/csv/preview',{'slug':'other-shop','kind':'inventory','csv_text':'Артикул;Наименование;Остаток\nSK-1;Пальто;2'}).status_code==404
    assert get(site,'/actions?slug=other-shop').status_code==404
    token=c.post('/api/auth/login',json={'email':'other@osmanx.local','password':'another-strong-password-2026'}).json()['token']
    headers={'Authorization':'Bearer '+token}
    assert c.get('/api/admin/r13/quality?slug=central',headers=headers).status_code==404
    assert c.get('/api/admin/r13/quality?slug=other-shop',headers=headers).status_code==200


def test_inventory_csv_cannot_overwrite_active_reserved_stock(site):
    c,h,db=site
    sid=create_stock(site,qty=2)
    with db.connect() as conn:
        # Released reservation schema uses source_inventory_id, current local schema uses target_store_id.
        inv=conn.execute('SELECT * FROM inventory WHERE store_id=?',(sid,)).fetchone()
        columns={r['name'] for r in conn.execute('PRAGMA table_info(reservations)')}
        expiry=(datetime.now(timezone.utc)+timedelta(hours=6)).isoformat(timespec='seconds')
        if 'source_inventory_id' in columns:
            did=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                             (sid,'Куртка','XL','чёрный',db.now_iso(),db.now_iso())).lastrowid
            conn.execute('INSERT INTO reservations(organization_id,request_id,demand_id,source_inventory_id,source_store_id,destination_store_id,quantity,status,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                         (1,'R13-RESERVED-123',did,inv['id'],sid,sid,2,'held',expiry,db.now_iso(),db.now_iso()))
        else:
            conn.execute('INSERT INTO reservations(organization_id,store_id,target_store_id,sku,customer_reference,state,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                         (1,sid,sid,'JACKET-XL','R13-HOLD','held',expiry,db.now_iso(),db.now_iso()))
        conn.commit()
    csv_text='Артикул;Наименование;Размер;Цвет;Остаток\nJACKET-XL;Куртка;XL;чёрный;0'
    staged=post(site,'/csv/preview',{'slug':'central','kind':'inventory','csv_text':csv_text})
    assert staged.status_code==201,staged.text
    applied=post(site,'/csv/commit',{'batch_key':staged.json()['batch_key']})
    assert applied.status_code==409,applied.text
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv['id'],)).fetchone()[0]==2


def test_csv_formula_cell_escaping_for_action_export(site):
    sid=create_stock(site,sku='SKU-A',product='=SUM(1+1)',size='M',qty=3)
    add_demand(site,sid,3,product='=SUM(1+1)',size='M')
    candidates=get(site,'/findings').json()['items']
    candidate=next(x for x in candidates if x['source']=='stock')
    payload={'slug':'central','source':'stock','signal_key':candidate['key'],'request_id':'R13-FORMULA-123456789'}
    assert post(site,'/actions',payload).status_code==201
    action=post(site,'/actions',payload).json()['id']
    c,h,_=site
    response=c.patch(f'/api/admin/r13/actions/{action}',headers=h,json={'version':1,'status':'testing','result_note':'=SUM(1+1)'})
    assert response.status_code==200,response.text
    data=get(site,'/actions.csv').text
    assert "'=SUM(1+1)" in data or "\t=SUM(1+1)" in data
