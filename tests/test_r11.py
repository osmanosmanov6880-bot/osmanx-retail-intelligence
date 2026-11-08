"""R1.1 Growth Intelligence acceptance: real receipts, privacy, budgets and isolation."""
from __future__ import annotations
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r11-bootstrap-super-secure-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r11-session-master-secret-super-long-12345678')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r11-device-master-secret-super-long-12345678')
    import backend.database as database
    import backend.app as application
    importlib.reload(database)
    importlib.reload(application)
    with TestClient(application.app) as c:
        login=c.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r11-bootstrap-super-secure-2026'})
        assert login.status_code==200,login.text
        yield c,{'Authorization':'Bearer '+login.json()['token']},database


def get(site,url):
    return site[0].get('/api/admin/r11/'+url,headers=site[1])


def post(site,url,data):
    return site[0].post('/api/admin/r11/'+url,headers=site[1],json=data)


def member(site,slug='central'):
    r=post(site,'members',{'slug':slug,'explicit_opt_in':True})
    assert r.status_code==201,r.text
    return r.json()


def sale(site,slug='central',amount=100000,occurred=None):
    c,h,database=site
    with database.connect() as db:
        sid=db.execute('SELECT id FROM stores WHERE slug=?',(slug,)).fetchone()[0]
        code='r11-manual-sale-'+str(db.execute('SELECT COUNT(*) FROM sales').fetchone()[0]+1)
        cur=db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
            (sid,amount,'test-receipt',occurred or database.now_iso(),code))
        db.commit()
        return cur.lastrowid


def campaign(site,slug='central',cost=10000,budget=20000,max_claims=2,min_spend=50000):
    today=datetime.now(timezone.utc).date()
    r=post(site,'campaigns',{'slug':slug,'title':'Бонус за обратную связь','reward_description':'Подарок при предъявлении кода',
        'unit_cost_kopeks':cost,'budget_kopeks':budget,'max_claims':max_claims,
        'min_spend_kopeks':min_spend,'starts_on':(today-timedelta(days=1)).isoformat(),
        'ends_on':(today+timedelta(days=20)).isoformat()})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_auth_and_consent_required(site):
    c,h,_=site
    for route in ['members','receipts','retention','campaigns','assortment']:
        assert c.get('/api/admin/r11/'+route).status_code==401
    assert c.post('/api/admin/r11/members',json={'explicit_opt_in':True}).status_code==401
    assert post(site,'members',{'explicit_opt_in':False}).status_code==422
    created=member(site)
    assert len(created['member_code'])==36 and created['member_code'].startswith('OXM-')
    listed=get(site,'members').json()['items'][0]
    assert 'member_code' not in listed and 'code_sha256' not in listed
    with site[2].connect() as db:
        assert created['member_code'] not in '\n'.join(db.iterdump())


def test_receipt_link_idempotence_and_conflict(site):
    m=member(site);other=member(site);s=sale(site)
    first=post(site,'receipts',{'member_code':m['member_code'],'sale_id':s})
    assert first.status_code==201 and not first.json()['duplicate']
    again=post(site,'receipts',{'member_code':m['member_code'],'sale_id':s})
    assert again.status_code==201 and again.json()['duplicate']
    conflicting=post(site,'receipts',{'member_code':other['member_code'],'sale_id':s})
    assert conflicting.status_code==409
    linked=get(site,'receipts').json()['items'][0]
    assert linked['sale_id']==s and linked['member_id']==m['id']


def test_revocation_unlinks_receipts_and_invalidates_secret(site):
    m=member(site);s=sale(site)
    assert post(site,'receipts',{'member_code':m['member_code'],'sale_id':s}).status_code==201
    r=site[0].delete('/api/admin/r11/members/'+str(m['id']),headers=site[1]);assert r.status_code==200
    assert get(site,'receipts').json()['items']==[]
    assert post(site,'receipts',{'member_code':m['member_code'],'sale_id':s}).status_code==404
    assert site[0].delete('/api/admin/r11/members/'+str(m['id']),headers=site[1]).json()['already_revoked']


def test_campaign_rejects_invalid_economics_and_dates(site):
    p={'slug':'central','title':'Слабая акция','reward_description':'Подарок',
       'unit_cost_kopeks':10000,'budget_kopeks':9000,'max_claims':10,'min_spend_kopeks':0,
       'starts_on':'2026-10-01','ends_on':'2026-10-15'}
    assert post(site,'campaigns',p).status_code==422
    assert post(site,'campaigns',{**p,'budget_kopeks':10000,'ends_on':'2026-09-01'}).status_code==422


def test_campaign_capacity_duplicate_claim_and_pause(site):
    cid=campaign(site);m1=member(site);m2=member(site);m3=member(site)
    a=post(site,f'campaigns/{cid}/claim',{'member_code':m1['member_code']})
    assert a.status_code==201 and a.json()['coupon_code'].startswith('OXC-')
    assert post(site,f'campaigns/{cid}/claim',{'member_code':m1['member_code']}).status_code==409
    assert post(site,f'campaigns/{cid}/claim',{'member_code':m2['member_code']}).status_code==201
    assert post(site,f'campaigns/{cid}/claim',{'member_code':m3['member_code']}).status_code==409
    row=get(site,'campaigns').json()['items'][0]
    assert row['issued']==2 and row['remaining_budget_kopeks']==0
    assert site[0].patch(f'/api/admin/r11/campaigns/{cid}',headers=site[1],json={'active':False}).status_code==200


def test_campaign_redemption_requires_member_receipt_and_minimum(site):
    cid=campaign(site,min_spend=100000);m=member(site);s=sale(site,amount=50000)
    token=post(site,f'campaigns/{cid}/claim',{'member_code':m['member_code']}).json()['coupon_code']
    assert post(site,f'campaigns/{cid}/redeem',{'coupon_code':token,'sale_id':s}).status_code==422
    assert post(site,'receipts',{'member_code':m['member_code'],'sale_id':s}).status_code==201
    assert post(site,f'campaigns/{cid}/redeem',{'coupon_code':token,'sale_id':s}).status_code==422
    s2=sale(site,amount=180000)
    post(site,'receipts',{'member_code':m['member_code'],'sale_id':s2})
    redeemed=post(site,f'campaigns/{cid}/redeem',{'coupon_code':token,'sale_id':s2})
    assert redeemed.status_code==200,redeemed.text
    assert post(site,f'campaigns/{cid}/redeem',{'coupon_code':token,'sale_id':s2}).status_code==409
    report=get(site,f'campaigns/{cid}/effect').json()
    assert report['verified_receipts']==1 and report['linked_receipt_revenue_kopeks']==180000
    assert report['roi_percent'] is None and report['estimated_reward_cost_kopeks']==10000


def test_campaign_code_cannot_cross_member(site):
    cid=campaign(site);m=member(site);n=member(site)
    code=post(site,f'campaigns/{cid}/claim',{'member_code':m['member_code']}).json()['coupon_code']
    s=sale(site,amount=90000)
    post(site,'receipts',{'member_code':n['member_code'],'sale_id':s})
    assert post(site,f'campaigns/{cid}/redeem',{'coupon_code':code,'sale_id':s}).status_code==422


def test_campaign_claim_is_concurrent_budget_safe(site):
    cid=campaign(site,budget=10000,max_claims=10);a=member(site);b=member(site)
    codes=[a['member_code'],b['member_code']]
    with ThreadPoolExecutor(max_workers=2) as ex:
        res=list(ex.map(lambda x:post(site,f'campaigns/{cid}/claim',{'member_code':x}).status_code,codes))
    assert sorted(res)==[201,409],res
    assert get(site,'campaigns').json()['items'][0]['issued']==1


def test_retention_cohort_maturity_and_coverage(site):
    m=member(site);n=member(site)
    old=datetime.now(timezone.utc)-timedelta(days=65)
    x=sale(site,amount=50000,occurred=old.isoformat(timespec='seconds'))
    y=sale(site,amount=90000,occurred=(old+timedelta(days=9)).isoformat(timespec='seconds'))
    z=sale(site,amount=20000,occurred=site[2].now_iso())
    for code,receipt in [(m['member_code'],x),(m['member_code'],y),(n['member_code'],z)]:
        assert post(site,'receipts',{'member_code':code,'sale_id':receipt}).status_code==201
    out=get(site,'retention').json()
    assert out['observed_members']==2 and out['observed_repeat_members']==1
    mature=[r for r in out['cohorts'] if r['matured']]
    assert mature[0]['repeat_rate_30d_percent']==100
    assert out['linked_receipts']==3
    assert any(r['repeat_rate_30d_percent'] is None for r in out['cohorts'])


def test_assortment_restock_and_ambiguity(site):
    _,_,database=site
    with database.connect() as db:
        sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        db.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                  (sid,'OX-JACKET-XL','Куртка','XL','чёрный',0,'manual',database.now_iso()))
        for _ in range(4):
            db.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                       (sid,'Куртка','XL','чёрный','open',database.now_iso(),database.now_iso()))
        db.execute('INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                       (sid,'Неизвестная модель','M','белый','open',database.now_iso(),database.now_iso()))
        db.commit()
    out=get(site,'assortment?days=30').json()
    assert out['items'][0]['sku']=='OX-JACKET-XL' and out['items'][0]['signal']=='check_restock'
    assert out['unresolved_demand']==1
    assert get(site,'assortment?days=2').status_code==422


def test_tenant_isolation_for_members_campaigns_and_sales(site):
    c,h,database=site
    m=member(site);cid=campaign(site);s=sale(site)
    with database.connect() as db:
        org=db.execute("INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)",('other-r11','Other',database.now_iso())).lastrowid
        sid=db.execute('INSERT INTO stores(slug,name,created_at,organization_id) VALUES(?,?,?,?)',
                       ('other-r11','Other store',database.now_iso(),org)).lastrowid
        from backend.security import hash_password
        db.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                   (org,'other-r11@local.test',hash_password('other-secret-12345'),'owner',database.now_iso()))
        db.commit()
    other=c.post('/api/auth/login',json={'email':'other-r11@local.test','password':'other-secret-12345'}).json()['token']
    hdr={'Authorization':'Bearer '+other}
    assert c.get('/api/admin/r11/members?slug=central',headers=hdr).status_code==404
    assert c.get(f'/api/admin/r11/campaigns/{cid}/effect',headers=hdr).status_code==404
    assert c.post('/api/admin/r11/receipts',json={'member_code':m['member_code'],'sale_id':s},headers=hdr).status_code==404
    assert c.get('/api/admin/r11/assortment?slug=central',headers=hdr).status_code==404


def test_viewer_cannot_mutate(site):
    c,_,database=site
    with database.connect() as db:
        from backend.security import hash_password
        owner=db.execute("SELECT organization_id FROM users WHERE email='owner@osmanx.local'").fetchone()[0]
        uid=db.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                       (owner,'viewer-r11@local.test',hash_password('viewer-secret-12345'),'viewer',database.now_iso())).lastrowid
        sid=db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
        db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,sid))
        db.commit()
    session=c.post('/api/auth/login',json={'email':'viewer-r11@local.test','password':'viewer-secret-12345'}).json()['token']
    hdr={'Authorization':'Bearer '+session}
    assert c.get('/api/admin/r11/retention',headers=hdr).status_code==200
    assert c.post('/api/admin/r11/members',json={'explicit_opt_in':True},headers=hdr).status_code==403
    assert c.post('/api/admin/r11/campaigns',json={},headers=hdr).status_code==422 # schema validation precedes auth


def test_existing_tables_and_foreign_keys_survive_r11(site):
    _,_,database=site
    with database.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('demand','sales','inventory','recovery_playbooks_r09')").fetchone()[0]==4
