"""R1.2 checkout, coupon proofs, budgets, retention, reporting and isolation."""
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import csv
import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','very-secure-r12-test-password')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r12-session-secret-with-at-least-32-characters')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r12-device-secret-with-at-least-32-characters')
    import backend.database as database
    import backend.app as application
    importlib.reload(database);importlib.reload(application)
    with TestClient(application.app) as client:
        r=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'very-secure-r12-test-password'})
        assert r.status_code==200,r.text
        yield client,{'Authorization':'Bearer '+r.json()['token']},database


def post(site,path,body,headers=None):
    c,h,_=site
    return c.post('/api/admin/'+path,json=body,headers=headers if headers is not None else h)


def get(site,path,headers=None):
    c,h,_=site
    return c.get('/api/admin/'+path,headers=headers if headers is not None else h)


def member(site):
    r=post(site,'r11/members',{'slug':'central','explicit_opt_in':True})
    assert r.status_code==201,r.text
    return r.json()


def sale(site,source='retail-pos',external_id=None,amount=100000,occurred=None):
    _,_,d=site
    with d.connect() as db:
        sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        external_id=external_id or f'test-{db.execute("SELECT COUNT(*) FROM sales").fetchone()[0]+1}'
        r=db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                     (sid,amount,source,occurred or d.now_iso(),external_id))
        db.commit();return r.lastrowid,external_id


def camp(site,budget=30000,unit=10000):
    today=datetime.now(timezone.utc).date()
    result=post(site,'r11/campaigns',{'slug':'central','title':'Тестовая кампания',
        'reward_description':'Физический сувенир','unit_cost_kopeks':unit,'budget_kopeks':budget,
        'max_claims':3,'min_spend_kopeks':0,
        'starts_on':(today-timedelta(days=1)).isoformat(),
        'ends_on':(today+timedelta(days=14)).isoformat()})
    assert result.status_code==201,result.text
    return result.json()['id']


def claim(site,campaign_id,member_code):
    r=post(site,f'r11/campaigns/{campaign_id}/claim',{'member_code':member_code})
    assert r.status_code==201,r.text
    return r.json()['coupon_code']


def linked(site,code,source='retail-pos',external_id='c123'):
    s,ext=sale(site,source,external_id)
    r=post(site,'r12/cashier/link',{'slug':'central','source':source,'external_id':ext,'member_code':code})
    assert r.status_code==201,r.text
    return s


def redeemed(site,campaign_id,member_code,coupon_code,external_id):
    sid=linked(site,member_code,external_id=external_id)
    result=post(site,f'r11/campaigns/{campaign_id}/redeem',{'coupon_code':coupon_code,'sale_id':sid})
    assert result.status_code==200,result.text
    return sid


def test_requires_auth_and_validates_inputs(site):
    c,h,_=site
    for method,path in [('get','r12/executive'),('get','r12/campaigns/controls'),
                        ('post','r12/cashier/link'),('post','r12/coupons/fulfill')]:
        assert getattr(c,method)('/api/admin/'+path,**({'json':{}} if method=='post' else {})).status_code==401
    assert post(site,'r12/cashier/receipt',{'slug':'central','source':'','external_id':'A'}).status_code==422
    assert post(site,'r12/coupons/inspect',{'slug':'central','coupon_code':'123'}).status_code==422
    assert get(site,'r12/executive?days=200').status_code==422


def test_cashier_lookup_and_idempotent_link(site):
    m=member(site);other=member(site);sid,ext=sale(site,'web-pos','receipt-a')
    payload={'slug':'central','source':'web-pos','external_id':ext}
    found=post(site,'r12/cashier/receipt',payload)
    assert found.status_code==200 and found.json()['sale']['id']==sid and not found.json()['linked']
    assert post(site,'r12/cashier/receipt',{**payload,'source':'other'}).status_code==404
    first=post(site,'r12/cashier/link',{**payload,'member_code':m['member_code']})
    second=post(site,'r12/cashier/link',{**payload,'member_code':m['member_code']})
    assert first.status_code==201 and not first.json()['duplicate']
    assert second.status_code==201 and second.json()['duplicate']
    assert post(site,'r12/cashier/link',{**payload,'member_code':other['member_code']}).status_code==409
    assert post(site,'r12/cashier/receipt',payload).json()['linked']


def test_wrong_store_not_readable_and_no_guessing(site):
    member_code=member(site)['member_code']
    sid,ext=sale(site,source='source-z',external_id='same-external-id')
    assert post(site,'r12/cashier/receipt',{'slug':'north','source':'source-z','external_id':ext}).status_code==404
    created=post(site,'stores',{'name':'Северный','slug':'north'})
    assert created.status_code==201,created.text
    assert post(site,'r12/cashier/receipt',{'slug':'north','source':'source-z','external_id':ext}).status_code==404
    assert post(site,'r12/cashier/link',{'slug':'north','source':'source-z','external_id':ext,'member_code':member_code}).status_code==404


def test_coupon_inspection_cancellation_and_budget_release(site):
    m=member(site);campaign=camp(site,budget=10000)
    code=claim(site,campaign,m['member_code'])
    inspected=post(site,'r12/coupons/inspect',{'slug':'central','coupon_code':code})
    assert inspected.status_code==200 and inspected.json()['can_cancel']
    assert not inspected.json()['receipt_verified']
    before=get(site,'r12/campaigns/controls').json()['items'][0]
    assert before['committed_kopeks']==10000 and before['limit_available']==0
    cancelled=post(site,'r12/coupons/cancel',{'slug':'central','coupon_code':code})
    assert cancelled.status_code==200 and not cancelled.json()['duplicate']
    again=post(site,'r12/coupons/cancel',{'slug':'central','coupon_code':code})
    assert again.status_code==200 and again.json()['duplicate']
    after=get(site,'r12/campaigns/controls').json()['items'][0]
    assert after['committed_kopeks']==0 and after['cancelled']==1 and after['limit_available']==1
    assert post(site,'r12/coupons/fulfill',{'slug':'central','coupon_code':code,'proof_reference':'HANDOFF-1','note':'Фактически передан сувенир'}).status_code==409


def test_physical_handoff_only_after_receipt_and_is_unique(site):
    m=member(site);campaign=camp(site);code=claim(site,campaign,m['member_code'])
    data={'slug':'central','coupon_code':code,'proof_reference':'GIFT-2026-001','note':'Сотрудник передал подарок покупателю'}
    assert post(site,'r12/coupons/fulfill',data).status_code==409
    redeemed(site,campaign,m['member_code'],code,'receipt-fulfill-1')
    first=post(site,'r12/coupons/fulfill',data)
    assert first.status_code==201,first.text
    assert first.json()['disclaimer'].startswith('Факт выдачи')
    second=post(site,'r12/coupons/fulfill',data)
    assert second.status_code==201 and second.json()['duplicate']
    assert post(site,'r12/coupons/fulfill',{**data,'proof_reference':'ANOTHER-REF'}).status_code==409
    inspection=post(site,'r12/coupons/inspect',{'slug':'central','coupon_code':code}).json()
    assert inspection['fulfilled'] and not inspection['can_attest_fulfillment']
    assert post(site,'r12/coupons/cancel',{'slug':'central','coupon_code':code}).status_code==409
    row=get(site,'r12/campaigns/controls').json()['items'][0]
    assert (row['redeemed'],row['fulfilled'],row['attested_cost_kopeks'])==(1,1,10000)


def test_campaign_funnel_verified_receipt_not_incremental_roi(site):
    m=member(site);camp_id=camp(site)
    code=claim(site,camp_id,m['member_code'])
    first=get(site,'r12/campaigns/controls').json()
    assert first['items'][0]['issued']==1 and first['items'][0]['attested_cost_kopeks']==0
    assert any('не является доказательством' in w for w in first['warnings'])
    redeemed(site,camp_id,m['member_code'],code,'campaign-sale')
    after=get(site,'r12/campaigns/controls').json()['items'][0]
    assert after['redeemed']==1 and after['unfulfilled_redeemed']==1 and after['linked_sale_kopeks']==100000
    assert after['attested_cost_kopeks']==0


def test_matured_windows_and_immature_cohorts(site):
    a=member(site);b=member(site)
    now=datetime.now(timezone.utc)
    first,_=sale(site,external_id='old-first',occurred=(now-timedelta(days=75)).isoformat())
    second,_=sale(site,external_id='old-repeat',occurred=(now-timedelta(days=70)).isoformat())
    third,_=sale(site,external_id='recent-first',occurred=(now-timedelta(days=2)).isoformat())
    for sale_id,code in [(first,a['member_code']),(second,a['member_code']),(third,b['member_code'])]:
        assert post(site,'r11/receipts',{'member_code':code,'sale_id':sale_id}).status_code==201
    rep=get(site,'r12/retention').json()
    windows={x['days']:x for x in rep['windows']}
    assert windows[7]['matured']==1 and windows[7]['repeated']==1
    assert windows[30]['matured']==1 and windows[30]['repeated']==1
    assert windows[60]['matured']==1 and windows[60]['repeated']==1
    assert rep['members_with_receipts']==2 and rep['linked_receipts']==3
    assert rep['coverage_pct']==100


def test_revoked_card_disappears_from_retention(site):
    m=member(site)
    r,_=sale(site)
    assert post(site,'r11/receipts',{'member_code':m['member_code'],'sale_id':r}).status_code==201
    assert get(site,'r12/retention').json()['members_with_receipts']==1
    assert site[0].delete('/api/admin/r11/members/'+str(m['id']),headers=site[1]).status_code==200
    assert get(site,'r12/retention').json()['members_with_receipts']==0


def test_executive_truthful_sales_demand_and_csv(site):
    sale(site,amount=195000)
    r=get(site,'r12/executive?days=30')
    assert r.status_code==200,r.text
    report=r.json()
    assert report['sales_count']==1 and report['receipt_revenue_kopeks']==195000
    assert report['receipt_conversion_pct'] is None
    assert 'чист' in report['note']
    csv_response=get(site,'r12/executive/export?days=30')
    assert csv_response.status_code==200 and csv_response.content.startswith(b'\xef\xbb\xbf')
    rows=list(csv.reader(io.StringIO(csv_response.content.decode('utf-8-sig'))))
    assert any(row[0]=='receipt_revenue_kopeks' and row[1]=='195000' for row in rows)


def test_executive_flags_multi_source_quality(site):
    _,_,database=site
    with database.connect() as db:
        store_id=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        for i,src in enumerate(['demo_sensor','manual']):
            db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                       (store_id,10,src,database.now_iso(),f'visit-{i}'))
        db.commit()
    body=get(site,'r12/executive').json()
    assert body['recorded_visits']==20
    assert any('двойного подсчёта' in w for w in body['warnings'])
    assert any('демонстрационные' in w for w in body['warnings'])


def test_concurrent_fulfillment_atomic(site):
    m=member(site);campaign=camp(site);code=claim(site,campaign,m['member_code'])
    redeemed(site,campaign,m['member_code'],code,'concurrent-handout')
    payload={'slug':'central','coupon_code':code,'proof_reference':'PARALLEL-001','note':'Выдача подтверждена сотрудником'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:post(site,'r12/coupons/fulfill',payload),range(2)))
    assert all(r.status_code==201 for r in replies)
    assert sorted(r.json()['duplicate'] for r in replies)==[False,True]
    with site[2].connect() as db:
        assert db.execute('SELECT COUNT(*) FROM coupon_fulfillments_r12').fetchone()[0]==1


def test_scoped_permissions_for_read_and_write(site):
    _,h,db_module=site
    with db_module.connect() as db:
        from backend.security import hash_password
        org_id=db.execute('SELECT organization_id FROM stores WHERE slug=?',('central',)).fetchone()[0]
        cur=db.execute("INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
             (org_id,'viewer@osmanx.local','Только просмотр',hash_password('read-only-super-secret-2026'),'viewer',db_module.now_iso()))
        uid=cur.lastrowid
        sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,sid))
        db.commit()
    logged=site[0].post('/api/auth/login',json={'email':'viewer@osmanx.local','password':'read-only-super-secret-2026'})
    assert logged.status_code==200,logged.text
    viewer={'Authorization':'Bearer '+logged.json()['token']}
    assert get(site,'r12/executive',viewer).status_code==200
    assert post(site,'r12/cashier/link',{'slug':'central','source':'x','external_id':'id','member_code':'OXM-'+'A'*32},viewer).status_code==403
    assert post(site,'r12/coupons/cancel',{'slug':'central','coupon_code':'OXC-'+'F'*32},viewer).status_code==403
    assert post(site,'r12/coupons/fulfill',{'slug':'central','coupon_code':'OXC-'+'F'*32,'proof_reference':'TEST-001','note':'Подтверждено вручную'},viewer).status_code==403


def test_migrates_twice_and_integrity(site):
    with site[2].connect() as db:
        from backend.r12 import ensure_schema
        ensure_schema(db);ensure_schema(db)
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
