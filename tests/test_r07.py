"""R0.7 acceptance: five real workflows, idempotency, isolation and stock safety."""
from __future__ import annotations

import importlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','r07-bootstrap-secret-pass-123')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','r07-master-session-secret-123456789-000')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','r07-master-device-secret-123456789-000')
    from backend import app, database
    importlib.reload(database)
    importlib.reload(app)
    with TestClient(app.app) as client:
        r=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'r07-bootstrap-secret-pass-123'})
        assert r.status_code==200,r.text
        yield client,{'Authorization':'Bearer '+r.json()['token']},database


def setup_stores(site,qty=5):
    c,h,db=site
    r=c.post('/api/admin/stores',headers=h,json={'slug':'north','name':'Бутик Северный'})
    assert r.status_code in (201,409),r.text
    with db.connect() as conn:
        source=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        dest=conn.execute("SELECT id FROM stores WHERE slug='north'").fetchone()['id']
        cursor=conn.execute("""INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
          VALUES(?,?,?,?,?,?,?,?)""",(source,'COAT-L','Пальто','L','чёрный',qty,'manual',db.now_iso()))
        inv=cursor.lastrowid
        conn.commit()
    return source,dest,inv


def count(c,h,inv,quantity,request_id='cycle-count-test-01',reason='Проверка фактических остатков'):
    return c.post('/api/admin/r07/counts',headers=h,json={'slug':'central','request_id':request_id,
      'lines':[{'inventory_id':inv,'observed_qty':quantity,'reason':reason}]})


def transfer(c,h,inv,quantity=2,request_id='transfer-id-test-01',source='central',target='north'):
    return c.post('/api/admin/r07/transfers',headers=h,json={'source_slug':source,'target_slug':target,
      'inventory_id':inv,'quantity':quantity,'request_id':request_id})


def test_schema_idempotent_no_breaking_previous_workflows(site):
    c,h,db=site
    with db.connect() as conn:
        from backend.r07 import ensure_schema
        ensure_schema(conn);ensure_schema(conn)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert c.get('/api/admin/workflows/overview',headers=h).status_code==200
    assert c.get('/api/admin/r07/brief',headers=h).status_code==200


def test_cycle_count_review_apply_idempotent_audit_and_stock(site):
    c,h,db=site
    _,_,inv=setup_stores(site,qty=5)
    first=count(c,h,inv,3)
    assert first.status_code==201,first.text
    cid=first.json()['id']
    assert count(c,h,inv,3).json()['duplicate'] is True
    assert count(c,h,inv,2).status_code==409
    before=c.get('/api/admin/r07/stock',headers=h).json()['items'][0]
    assert before['quantity']==5
    changed=c.post(f'/api/admin/r07/counts/{cid}/apply',headers=h)
    assert changed.status_code==200,changed.text
    assert changed.json()['applied']
    assert c.post(f'/api/admin/r07/counts/{cid}/apply',headers=h).json()['duplicate']
    assert c.post(f'/api/admin/r07/counts/{cid}/cancel',headers=h).status_code==409
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv,)).fetchone()[0]==3
        assert conn.execute("SELECT delta FROM stock_adjustments_r07 WHERE kind='cycle_count'").fetchone()[0]==-2
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='r07.count.apply'").fetchone()[0]==1


def test_cycle_count_requires_explanation_and_rejects_stale_update(site):
    c,h,db=site
    _,_,inv=setup_stores(site,qty=5)
    assert count(c,h,inv,4,reason='').status_code==422
    created=count(c,h,inv,4,request_id='cycle-stale-0123')
    assert created.status_code==201,created.text
    with db.connect() as conn:
        conn.execute('UPDATE inventory SET quantity=6,updated_at=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),inv))
        conn.commit()
    assert c.post(f"/api/admin/r07/counts/{created.json()['id']}/apply",headers=h).status_code==409
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv,)).fetchone()[0]==6
    assert c.post(f"/api/admin/r07/counts/{created.json()['id']}/cancel",headers=h).status_code==200


def test_transfer_ship_receive_exactly_once_and_collision(site):
    c,h,db=site
    source,dest,inv=setup_stores(site,qty=4)
    p=transfer(c,h,inv,2)
    assert p.status_code==201,p.text
    tid=p.json()['id']
    assert transfer(c,h,inv,2).json()['duplicate']
    assert transfer(c,h,inv,3).status_code==409
    assert c.post(f'/api/admin/r07/transfers/{tid}/receive',headers=h).status_code==409
    assert c.post(f'/api/admin/r07/transfers/{tid}/ship',headers=h).status_code==200
    assert c.post(f'/api/admin/r07/transfers/{tid}/ship',headers=h).status_code==409
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv,)).fetchone()[0]==2
    assert c.post(f'/api/admin/r07/transfers/{tid}/receive',headers=h).status_code==200
    assert c.post(f'/api/admin/r07/transfers/{tid}/receive',headers=h).json()['duplicate']
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(dest,'COAT-L')).fetchone()[0]==2
        rows=conn.execute('SELECT kind,delta FROM stock_adjustments_r07 WHERE reference_id=? ORDER BY id',(tid,)).fetchall()
        assert [tuple(x) for x in rows]==[('transfer_ship',-2),('transfer_receive',2)]
    assert c.get('/api/admin/r07/transfers?slug=north',headers=h).status_code==200


def test_transfer_uses_realtime_stock_not_draft_snapshot(site):
    c,h,db=site
    _,_,inv=setup_stores(site,qty=1)
    a=transfer(c,h,inv,1,request_id='transfer-race-a-0001').json()['id']
    b=transfer(c,h,inv,1,request_id='transfer-race-b-0002').json()['id']
    def ship(i):return c.post(f'/api/admin/r07/transfers/{i}/ship',headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(ship,[a,b]))
    assert sorted(statuses)==[200,409]
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv,)).fetchone()[0]==0
        assert conn.execute("SELECT COUNT(*) FROM transfers_r07 WHERE status='shipped'").fetchone()[0]==1


def test_transfer_rejects_conflicting_destination_metadata(site):
    c,h,db=site
    _,dest,inv=setup_stores(site,qty=3)
    with db.connect() as conn:
        conn.execute('''INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at)
          VALUES(?,?,?,?,?,?,?,?)''',(dest,'COAT-L','Другое название','L','чёрный',2,'test',db.now_iso()))
        conn.commit()
    r=transfer(c,h,inv,1,request_id='transfer-conflict-01')
    tid=r.json()['id']
    assert c.post(f'/api/admin/r07/transfers/{tid}/ship',headers=h).status_code==200
    assert c.post(f'/api/admin/r07/transfers/{tid}/receive',headers=h).status_code==409
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(dest,'COAT-L')).fetchone()[0]==2


def test_assistance_public_token_requests_and_lifecycle(site):
    c,h,db=site
    unauthorized=c.post('/api/admin/r07/assistance/points',json={'slug':'central','name':'Примерочная 1'})
    assert unauthorized.status_code==401
    p=c.post('/api/admin/r07/assistance/points',headers=h,json={'slug':'central','name':'Примерочная 1'})
    assert p.status_code==201,p.text
    path=p.json()['path'];pid=p.json()['id']
    assert c.get(path).status_code==200
    assert c.post('/api/assist/not-a-real-point',json={'request_id':'help-customer-1234','category':'size'}).status_code==404
    payload={'request_id':'help-customer-1234','category':'size'}
    created=c.post('/api'+path,json=payload)
    assert created.status_code==201,created.text
    aid=created.json()['id']
    assert c.post('/api'+path,json=payload).json()['duplicate']
    assert c.post('/api'+path,json={**payload,'category':'help'}).status_code==409
    assert c.post('/api'+path,json={'request_id':'help-other-1234567','category':'help'}).status_code==429
    assert c.post(f'/api/admin/r07/assistance/{aid}/status',headers=h,json={'status':'resolved'}).status_code==409
    assert c.post(f'/api/admin/r07/assistance/{aid}/status',headers=h,json={'status':'accepted'}).status_code==200
    assert c.post(f'/api/admin/r07/assistance/{aid}/status',headers=h,json={'status':'resolved'}).status_code==200
    assert c.get('/api/admin/r07/assistance',headers=h).json()['requests'][0]['status']=='resolved'
    assert c.post(f'/api/admin/r07/assistance/points/{pid}/disable',headers=h).status_code==200
    assert c.post('/api'+path,json={'request_id':'help-third-123456','category':'help'}).status_code==404
    with db.connect() as conn:
        token_hash=conn.execute('SELECT token_hash FROM assistance_points_r07 WHERE id=?',(pid,)).fetchone()[0]
        assert token_hash!=p.json()['token_once']


def test_zones_trial_requires_zone_and_reports_cautiously(site):
    c,h,db=site
    st,_,_=setup_stores(site,qty=1)
    today=date.today();a=today-timedelta(days=5);b=today-timedelta(days=2)
    with db.connect() as conn:
        zid=conn.execute('INSERT INTO zones(store_id,code,name,x,y) VALUES(?,?,?,?,?)',
          (st,'display-a','Витрина',25,25)).lastrowid
        for i in range(3):
            for period,qty in [(a,3),(b,5)]:
                ts=datetime.combine(period+timedelta(days=i),datetime.min.time(),tzinfo=timezone.utc).isoformat()
                conn.execute('INSERT INTO zone_events(store_id,zone_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?,?)',
                  (st,zid,qty,'signed_sensor',ts,f'{period}-{i}'))
        conn.commit()
    payload={'slug':'central','zone_id':zid,'title':'Витрина: размещение новой коллекции',
      'variant_a':'Стойка без подсветки','variant_b':'Стойка с подсветкой',
      'a_start':a.isoformat(),'a_end':(a+timedelta(days=2)).isoformat(),
      'b_start':b.isoformat(),'b_end':today.isoformat()}
    assert c.post('/api/admin/r07/zone-trials',headers=h,json={**payload,'zone_id':999999}).status_code==404
    created=c.post('/api/admin/r07/zone-trials',headers=h,json=payload)
    assert created.status_code==201,created.text
    assert created.json()['report']['period_a']['count']==9
    assert created.json()['report']['period_b']['count']==15
    assert created.json()['report']['change_percent']==66.67
    assert 'не доказывает' in created.json()['report']['interpretation']
    bad=c.post('/api/admin/r07/zone-trials',headers=h,json={**payload,'a_end':b.isoformat()})
    assert bad.status_code==422
    assert c.get('/api/admin/r07/zone-trials',headers=h).status_code==200


def test_brief_real_inputs_warnings_and_csv_safe(site):
    c,h,db=site
    sid,_,inv=setup_stores(site,qty=1)
    c.post('/api/admin/events',headers=h,json={'slug':'central','kind':'entry','quantity':12})
    c.post('/api/admin/events',headers=h,json={'slug':'central','kind':'sale','amount_rub':4000,'quantity':1})
    c.post('/api/admin/demand',headers=h,json={'slug':'central','product':'Пальто','size':'L','color':'чёрный'})
    assert count(c,h,inv,1,request_id='brief-count-00001').status_code==201
    result=c.get('/api/admin/r07/brief',headers=h)
    assert result.status_code==200,result.text
    b=result.json()
    assert b['metrics']['visitors']==12
    assert b['metrics']['sales']==1
    assert b['metrics']['open_demand']==1
    assert b['metrics']['pending_counts']==1
    assert b['metrics']['conversion_percent']>0
    assert b['warnings'] and b['priorities']
    text=c.get('/api/admin/r07/brief.csv',headers=h)
    assert text.status_code==200 and text.content.startswith(b'\xef\xbb\xbf')
    assert 'text/csv' in text.headers['content-type']
    assert c.get('/api/admin/r07/brief.csv').status_code==401


def test_multi_tenant_all_r07_endpoints_not_exposed(site):
    c,h,db=site
    from backend.security import hash_password
    with db.connect() as conn:
        org=conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('other-business','Другая организация',db.now_iso())).lastrowid
        st=conn.execute('INSERT INTO stores(slug,name,organization_id,created_at) VALUES(?,?,?,?)',
          ('other-shop','Чужой магазин',org,db.now_iso())).lastrowid
        conn.execute('''INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at)
          VALUES(?,?,?,?,?,?)''',(org,'other@osmanx.local','Директор',hash_password('other-strong-password-0001'),'owner',db.now_iso()))
        conn.commit()
    r=c.post('/api/auth/login',json={'email':'other@osmanx.local','password':'other-strong-password-0001'})
    assert r.status_code==200,r.text
    other={'Authorization':'Bearer '+r.json()['token']}
    for path in ('stock','counts','transfers','assistance','zone-trials','brief','brief.csv'):
        assert c.get('/api/admin/r07/'+path+'?slug=central',headers=other).status_code==404
        assert c.get('/api/admin/r07/'+path+'?slug=other-shop',headers=h).status_code==404
    assert c.post('/api/admin/r07/counts',headers=other,json={'slug':'central','request_id':'other-cycle-00001',
      'lines':[{'inventory_id':1,'observed_qty':1}]}).status_code==404
    assert c.post('/api/admin/r07/transfers',headers=other,json={'source_slug':'other-shop','target_slug':'central',
      'inventory_id':1,'quantity':1,'request_id':'other-transfer-0001'}).status_code==404


def test_stock_count_and_transfer_respect_held_reservations(site):
    c,h,db=site
    sid,north,inv=setup_stores(site,qty=3)
    with db.connect() as conn:
        columns={x['name'] for x in conn.execute('PRAGMA table_info(reservations)')}
        future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(timespec='seconds')
        if 'source_inventory_id' in columns:
            demand=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
              (north,'Пальто','L','чёрный',db.now_iso(),db.now_iso())).lastrowid
            conn.execute('''INSERT INTO reservations(organization_id,request_id,demand_id,source_inventory_id,
              source_store_id,destination_store_id,quantity,status,expires_at,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (1,'r07-held-test-0001',demand,inv,sid,north,2,'held',future,db.now_iso(),db.now_iso()))
        else:
            conn.execute('''INSERT INTO reservations(organization_id,store_id,target_store_id,sku,customer_reference,
              expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)''',
              (1,north,sid,'COAT-L','r07-hold',future,db.now_iso(),db.now_iso()))
            conn.execute('''INSERT INTO reservations(organization_id,store_id,target_store_id,sku,customer_reference,
              expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)''',
              (1,north,sid,'COAT-L','r07-hold-2',future,db.now_iso(),db.now_iso()))
        conn.commit()
    assert c.get('/api/admin/r07/stock',headers=h).json()['items'][0]['available']==1
    assert count(c,h,inv,2,request_id='reserved-count-0001').status_code==201
    assert count(c,h,inv,0,request_id='reserved-count-0002').status_code==409
    assert transfer(c,h,inv,quantity=2,request_id='reserved-transfer-01').status_code==409
    okay=transfer(c,h,inv,quantity=1,request_id='reserved-transfer-02')
    assert okay.status_code==201,okay.text
    assert c.post(f"/api/admin/r07/transfers/{okay.json()['id']}/ship",headers=h).status_code==200
    with db.connect() as conn:
        assert conn.execute('SELECT quantity FROM inventory WHERE id=?',(inv,)).fetchone()[0]==2


def test_staff_only_sees_own_assigned_store(site):
    c,h,db=site
    _,north,inv=setup_stores(site,qty=3)
    from backend.security import hash_password
    with db.connect() as conn:
        uid=conn.execute('''INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at)
          VALUES(?,?,?,?,?,?)''',(1,'north-manager@osmanx.local','Менеджер Север',
                 hash_password('north-manager-password-r07'),'manager',db.now_iso())).lastrowid
        conn.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,north))
        conn.commit()
    response=c.post('/api/auth/login',json={'email':'north-manager@osmanx.local',
                                             'password':'north-manager-password-r07'})
    assert response.status_code==200,response.text
    staff={'Authorization':'Bearer '+response.json()['token']}
    assert c.get('/api/admin/r07/brief?slug=north',headers=staff).status_code==200
    for endpoint in ['counts','stock','transfers','assistance','zone-trials','brief']:
        assert c.get('/api/admin/r07/'+endpoint+'?slug=central',headers=staff).status_code==404
    assert c.post('/api/admin/r07/transfers',headers=staff,json={'source_slug':'central',
     'target_slug':'north','inventory_id':inv,'quantity':1,'request_id':'staff-no-access-01'}).status_code==404
