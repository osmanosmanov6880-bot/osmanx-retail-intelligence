"""R0.9 independent API integration tests; no fake automatic outcomes."""
from __future__ import annotations
import importlib
from datetime import date,timedelta,datetime,timezone
from fastapi.testclient import TestClient
import pytest

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r09-bootstrap-password-1234')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r09-long-session-secret-000000000000')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r09-long-device-secret-00000000000')
    import backend.database as db
    import backend.app as api
    importlib.reload(db);importlib.reload(api)
    with TestClient(api.app) as c:
        auth=c.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r09-bootstrap-password-1234'})
        assert auth.status_code==200,auth.text
        yield c,{'Authorization':'Bearer '+auth.json()['token']},db


def path(s):return '/api/admin/r09/'+s

def get(site,s):return site[0].get(path(s),headers=site[1])

def post(site,s,p):return site[0].post(path(s),headers=site[1],json=p)

def patch(site,s,p):return site[0].patch(path(s),headers=site[1],json=p)

def fill(site):
    _,_,db=site
    now=db.now_iso()
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        conn.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
          (sid,'SKU-XL','Куртка премиум','XL','синий',0,'manual',now))
        did=conn.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
          (sid,'Куртка премиум','XL','синий','open',now,now)).lastrowid
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
          (sid,700000,'pos',now,'r09-sale-1')).lastrowid
        conn.commit()
    return sid,did,sale


def line(site,sid,sale,sku='SKU-XL',amount=700000,cost=300000):
    with site[2].connect() as db:
        db.execute('INSERT INTO sale_items(organization_id,store_id,sale_id,sku,quantity,unit_revenue_kopeks,unit_cost_kopeks,external_id,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)',
          (1,sid,sale,sku,1,amount,cost,'r09-item-'+sku,site[2].now_iso()))
        db.commit()


def test_auth_required_for_every_module(site):
    c=site[0]
    for p in ('radar','recoveries','finance','protocols','dossiers'):
        assert c.get(path(p)).status_code==401,p
    for p in ('recoveries','protocols','dossiers'):
        assert c.post(path(p),json={}).status_code==401,p


def test_radar_unique_sku_stock_and_unresolved(site):
    sid,did,sale=fill(site)
    with site[2].connect() as db:
        now=site[2].now_iso()
        db.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (sid,'Неизвестная модель','S','красный','open',now,now))
        db.commit()
    r=get(site,'radar?days=14');assert r.status_code==200,r.text
    data=r.json();assert data['current_requests']==2
    match=next(x for x in data['items'] if x['sku']=='SKU-XL')
    assert match['current']==1 and match['available_local']==0 and match['signal']=='investigate'
    assert data['ambiguous_sku_records']==1
    assert get(site,'radar?days=2').status_code==422


def test_recovery_no_fake_sales_idempotency_and_verified_receipt(site):
    sid,did,sale=fill(site)
    p={'slug':'central','request_id':'r09-case-id-0001','demand_id':did,'action':'stock_check'}
    first=post(site,'recoveries',p);assert first.status_code==201,first.text
    rid=first.json()['id']
    assert post(site,'recoveries',p).json()['duplicate']
    assert post(site,'recoveries',{**p,'action':'fitting_fix'}).status_code==409
    assert post(site,'recoveries',{**p,'request_id':'r09-case-id-0002'}).status_code==409
    assert patch(site,f'recoveries/{rid}',{'status':'resolved','outcome':'confirmed_sale','sale_id':sale,'evidence':'Подтверждение по кассе'}).status_code==422
    line(site,sid,sale)
    done=patch(site,f'recoveries/{rid}',{'status':'resolved','outcome':'confirmed_sale','sale_id':sale,
                          'evidence':'В чеке подтверждена модель и количество товара'})
    assert done.status_code==200,done.text
    assert patch(site,f'recoveries/{rid}',{'status':'working'}).status_code==409
    with site[2].connect() as db:
        assert db.execute('SELECT status,sale_id FROM demand WHERE id=?',(did,)).fetchone()['status']=='converted'
        assert db.execute("SELECT COUNT(*) FROM demand_history WHERE demand_id=? AND next_status='converted'",(did,)).fetchone()[0]==1


def test_recovery_rejects_wrong_sku_and_operational_does_not_fake_sale(site):
    sid,did,sale=fill(site)
    line(site,sid,sale,sku='OTHER-XL')
    r=post(site,'recoveries',{'request_id':'r09-case-id-0009','demand_id':did,'action':'supplier_order'})
    rid=r.json()['id']
    assert patch(site,f'recoveries/{rid}',{'status':'resolved','outcome':'confirmed_sale','sale_id':sale,'evidence':'Проверен чек и наличие товара'}).status_code==422
    assert patch(site,f'recoveries/{rid}',{'status':'resolved','outcome':'operational_fix','evidence':'Проведена сверка и поправлен остаток'}).status_code==200
    assert get(site,'recoveries').json()['items'][0]['sale_id'] is None


def test_finance_withheld_until_full_line_reconciliation(site):
    sid,did,sale=fill(site)
    r=get(site,'finance');assert r.status_code==200
    assert r.json()['gross_contribution_kopeks'] is None
    line(site,sid,sale,amount=700000,cost=300000)
    good=get(site,'finance').json()
    assert good['gross_contribution_kopeks']==400000
    assert good['cost_coverage_percent']==100
    with site[2].connect() as db:
        db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
          (sid,20000,'pos',site[2].now_iso(),'r09-sale-2'))
        db.commit()
    dirty=get(site,'finance').json()
    assert dirty['gross_contribution_kopeks'] is None and dirty['reconciled_contribution_kopeks']==400000
    assert dirty['receipts']==2 and dirty['reconciled_receipts']==1


def test_finance_returns_are_logged_not_bank_refunds(site):
    sid,did,sale=fill(site)
    line(site,sid,sale)
    with site[2].connect() as db:
        table='merchandise_returns' if db.execute("SELECT 1 FROM sqlite_master WHERE name='merchandise_returns'").fetchone() else 'returns_log'
        if table=='merchandise_returns':
            db.execute('INSERT INTO merchandise_returns(store_id,sale_id,external_id,item_description,amount_kopeks,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                (sid,sale,'r09-ret-1','Куртка',100000,'fit',site[2].now_iso()))
        else:
            db.execute('INSERT INTO returns_log(organization_id,store_id,sale_id,amount_kopeks,reason,created_at,external_id) VALUES(?,?,?,?,?,?,?)',
                (1,sid,sale,100000,'fit',site[2].now_iso(),'r09-ret-1'))
        db.commit()
    val=get(site,'finance').json()
    assert val['documented_returns_kopeks']==100000
    assert any('банковского возврата' in x for x in val['warnings'])


def window(days_ago):
    return (date.today()-timedelta(days=days_ago)).isoformat()


def protocol_payload():
    return {'slug':'central','request_id':'r09-protocol-00001','title':'Проверка конверсии витрины',
      'hypothesis':'Новая раскладка должна улучшить долю чеков на входы',
      'metric':'check_rate','source_mode':'manual',
      'before_start':window(9),'before_end':window(8),'after_start':window(3),'after_end':window(2)}


def test_protocol_equal_windows_idempotency_freeze(site):
    payload=protocol_payload()
    wrong={**payload,'before_end':window(7)}
    assert post(site,'protocols',wrong).status_code==422
    first=post(site,'protocols',payload);assert first.status_code==201,first.text
    pid=first.json()['id']
    assert post(site,'protocols',payload).json()['duplicate']
    assert post(site,'protocols',{**payload,'title':'Другой заголовок'}).status_code==409
    p=get(site,f'protocols/{pid}/preview').json()
    assert p['verdict']=='insufficient_evidence' and p['delta'] is None
    r=post(site,f'protocols/{pid}/evaluate',{'evidence':'Сравнение выполнено, но данные отсутствуют для вывода'})
    assert r.status_code==200 and r.json()['status']=='evaluated'
    assert post(site,f'protocols/{pid}/evaluate',{'evidence':'Вторая попытка завершения эксперимента'}).status_code==409
    assert get(site,'protocols').json()['items'][0]['result']['result']['verdict']=='insufficient_evidence'


def test_protocol_control_store_scope_and_trend_math(site):
    sid,did,sale=fill(site)
    c,h,db=site
    with db.connect() as con:
        other=con.execute('INSERT INTO stores(slug,name,created_at,organization_id) VALUES(?,?,?,?)',
          ('comparison','Контрольный',db.now_iso(),1)).lastrowid
        # Four days of comparable visits; a recorded change does not imply a cause.
        for day_ago,store_id,visits,checks in [(9,sid,100,10),(8,sid,100,10),(3,sid,100,20),(2,sid,100,20),
             (9,other,100,10),(8,other,100,10),(3,other,100,15),(2,other,100,15)]:
            happened=(datetime.now(timezone.utc)-timedelta(days=day_ago)).replace(hour=12).isoformat(timespec='seconds')
            con.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
              (store_id,visits,'manual',happened,f'r09-visit-{store_id}-{day_ago}'))
            for n in range(checks):
                con.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                  (store_id,50000,'pos',happened,f'r09-sale-{store_id}-{day_ago}-{n}'))
        con.commit()
    p={**protocol_payload(),'control_slug':'comparison','request_id':'r09-protocol-00002'}
    made=post(site,'protocols',p)
    assert made.status_code==201,made.text
    result=get(site,f'protocols/{made.json()["id"]}/preview').json()
    assert result['before']['entries']==200 and result['after']['entries']==200
    assert result['delta']==10 and result['reference']['delta']==5
    assert result['difference_in_differences']==5
    assert result['verdict']=='descriptive_change'
    assert 'не доказывает' in result['disclaimer']


def test_foreign_org_cannot_access_any_r09_object(site):
    sid,did,sale=fill(site)
    c,h,db=site
    pid=post(site,'protocols',protocol_payload()).json()['id']
    rid=post(site,'recoveries',{'request_id':'r09-foreign-case-01','demand_id':did,'action':'stock_check'}).json()['id']
    with db.connect() as con:
        other=con.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('r09-foreign','Чужая',db.now_iso())).lastrowid
        con.execute('INSERT INTO stores(slug,name,organization_id,created_at) VALUES(?,?,?,?)',('r09-foreign-store','Чужой магазин',other,db.now_iso()))
        con.commit()
    assert get(site,'radar?slug=r09-foreign-store').status_code==404
    assert get(site,'finance?slug=r09-foreign-store').status_code==404
    assert get(site,'protocols?slug=r09-foreign-store').status_code==404
    assert post(site,'recoveries',{'slug':'r09-foreign-store','request_id':'r09-foreign-case-02','demand_id':did,'action':'stock_check'}).status_code==404
    assert post(site,'protocols',{**protocol_payload(),'request_id':'r09-foreign-protocol','control_slug':'r09-foreign-store'}).status_code==404


def test_dossier_idempotent_immutable_export_csv_and_sha(site):
    sid,did,sale=fill(site)
    p={'request_id':'r09-dossier-00001','slug':'central','start':window(4),'end':window(0)}
    first=post(site,'dossiers',p);assert first.status_code==201,first.text
    iid=first.json()['id']
    assert post(site,'dossiers',p).json()['duplicate']
    assert post(site,'dossiers',{**p,'start':window(5)}).status_code==409
    record=get(site,f'dossiers/{iid}').json()
    assert record['sha256']==first.json()['sha256']
    assert record['payload']['financial_integrity']['receipts']>=1
    exported=get(site,f'dossiers/{iid}/export.csv')
    assert exported.status_code==200 and 'sha256' in exported.text
    with site[2].connect() as con:
        con.execute('DELETE FROM sales WHERE id=?',(sale,))
        con.commit()
    assert get(site,f'dossiers/{iid}').json()['sha256']==record['sha256']


def test_published_r05_return_ledger_variant_supported(site):
    sid,did,sale=fill(site)
    with site[2].connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS merchandise_returns (
          id INTEGER PRIMARY KEY,store_id INTEGER,sale_id INTEGER,external_id TEXT,
          item_description TEXT,amount_kopeks INTEGER,reason TEXT,created_at TEXT)''')
        db.execute('INSERT INTO merchandise_returns(store_id,sale_id,external_id,item_description,amount_kopeks,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                   (sid,sale,'r09-published-schema','Куртка',45000,'size',site[2].now_iso()))
        db.commit()
    assert get(site,'finance').json()['documented_returns_kopeks']==45000


def test_recovery_uses_explicit_case_sku_if_stock_catalog_not_mapped(site):
    sid,did,sale=fill(site)
    with site[2].connect() as db:
        db.execute('INSERT INTO demand_cases(organization_id,store_id,demand_id,sku,requested_quantity,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                   (1,sid,did,'CASE-SKU-999',1,site[2].now_iso(),site[2].now_iso()))
        db.commit()
    created=post(site,'recoveries',{'request_id':'r09-explicit-sku-01','demand_id':did,'action':'stock_check'})
    assert created.status_code==201,created.text
    assert created.json()['sku']=='CASE-SKU-999'


def test_dossier_csv_escapes_spreadsheet_formulas_and_hash_is_reproducible(site):
    sid,did,sale=fill(site)
    from backend.r09 import sha
    with site[2].connect() as db:
        db.execute("UPDATE stores SET slug='=HYPERLINK(\"http://example.invalid\")' WHERE id=?",(sid,))
        db.commit()
    strange='=HYPERLINK("http://example.invalid")'
    p={'request_id':'r09-dossier-csv-id-1','slug':strange,'start':window(4),'end':window(0)}
    result=post(site,'dossiers',p)
    assert result.status_code==201,result.text
    record=get(site,f'dossiers/{result.json()["id"]}').json()
    assert sha(record['payload'])==record['sha256']
    exported=get(site,f'dossiers/{result.json()["id"]}/export.csv').text
    assert "'=HYPERLINK" in exported
