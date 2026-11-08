"""R1.0 acceptance: benchmark, shifts, assistance SLA, paired pulse, incidents."""
from __future__ import annotations
import importlib
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def site(tmp_path,monkeypatch):
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
        response=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert response.status_code==200,response.text
        yield client,{'Authorization':'Bearer '+response.json()['token']},db

def store_id(site,slug='central'):
    with site[2].connect() as db:
        return db.execute('SELECT id FROM stores WHERE slug=?',(slug,)).fetchone()['id']

def other_store(site):
    client,head,_=site
    result=client.post('/api/admin/stores',headers=head,json={'name':'Торговый центр','slug':'mall'})
    assert result.status_code==201,result.text
    return store_id(site,'mall')

def second_org(site):
    client,head,dbmod=site
    from backend.security import hash_password
    with dbmod.connect() as db:
        oid=db.execute("INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)",('r10-other','Чужая организация',dbmod.now_iso())).lastrowid
        sid=db.execute("INSERT INTO stores(slug,name,organization_id,created_at) VALUES(?,?,?,?)",('other-r10','Чужой магазин',oid,dbmod.now_iso())).lastrowid
        uid=db.execute("INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",(oid,'other-r10@test.local',hash_password('other-password-2026'),'owner',dbmod.now_iso())).lastrowid
        db.commit()
    login=client.post('/api/auth/login',json={'email':'other-r10@test.local','password':'other-password-2026'})
    assert login.status_code==200
    return sid,{'Authorization':'Bearer '+login.json()['token']}

def test_schema_and_auth_guard(site):
    client,headers,dbmod=site
    from backend.r10 import ensure_schema
    with dbmod.connect() as db:
        ensure_schema(db);ensure_schema(db)
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    for endpoint in ('benchmark','shifts','service','pulse','incidents'):
        assert client.get('/api/admin/r10/'+endpoint).status_code==401
    assert client.get('/api/admin/r10/benchmark?days=31',headers=headers).status_code==422

def test_benchmark_only_real_sources_and_own_org(site):
    client,headers,dbmod=site
    other_store(site)
    ts=dbmod.now_iso()
    with dbmod.connect() as db:
        for slug in ('central','mall'):
            sid=db.execute('SELECT id FROM stores WHERE slug=?',(slug,)).fetchone()[0]
            db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,60,'sensor',ts,'real-'+slug))
            db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,30,'manual',ts,'manual-'+slug))
            db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,1000,'demo_sensor',ts,'demo-'+slug))
            db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',(sid,125000,'pos',ts,'real-'+slug))
        db.commit()
    result=client.get('/api/admin/r10/benchmark?days=14&source_mode=sensor',headers=headers).json()
    assert len(result['stores'])==2
    for item in result['stores']:
        assert item['visits']==60 and item['checks']==1 and item['revenue_kopeks']==125000
        assert not item['comparable'] and any('Демонстрационные' in x for x in item['warnings'])
    assert client.get('/api/admin/r10/benchmark?source_mode=invalid',headers=headers).status_code==422
    sid,h2=second_org(site)
    assert len(client.get('/api/admin/r10/benchmark',headers=h2).json()['stores'])==1

def test_shift_idempotency_overlap_cancel_and_capacity(site):
    c,h,_=site
    start=datetime.now(timezone.utc).replace(hour=10,minute=0,second=0,microsecond=0)+timedelta(days=1)
    payload={'slug':'central','label':'Смена консультанта','capacity_per_hour':20,
       'start_at':start.isoformat(),'end_at':(start+timedelta(hours=5)).isoformat(),
       'request_id':'shift-unique-key-r10-001'}
    r=c.post('/api/admin/r10/shifts',headers=h,json=payload)
    assert r.status_code==201,r.text
    assert c.post('/api/admin/r10/shifts',headers=h,json=payload).json()['duplicate']
    assert c.post('/api/admin/r10/shifts',headers=h,json={**payload,'capacity_per_hour':25}).status_code==409
    result=c.get('/api/admin/r10/shifts?day='+start.date().isoformat(),headers=h).json()
    assert len(result['shifts'])==1 and max(x['planned_capacity'] for x in result['hours'])==20
    assert c.post(f"/api/admin/r10/shifts/{r.json()['id']}/cancel",headers=h).json()['cancelled']
    assert c.post(f"/api/admin/r10/shifts/{r.json()['id']}/cancel",headers=h).json()['duplicate']
    assert c.get('/api/admin/r10/shifts?day='+start.date().isoformat(),headers=h).json()['shifts']==[]

def test_shift_user_overlap_across_stores_and_role(site):
    c,h,dbmod=site;other_store(site)
    from backend.security import hash_password
    with dbmod.connect() as db:
        uid=db.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
          (1,'employee@osmanx.local',hash_password('employee-password-2026'),'viewer',dbmod.now_iso())).lastrowid
        db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,store_id(site)))
        db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,store_id(site,'mall')))
        db.commit()
    now=datetime.now(timezone.utc)+timedelta(days=1)
    base={'user_id':uid,'label':'Консультант','capacity_per_hour':10,
          'start_at':now.isoformat(),'end_at':(now+timedelta(hours=2)).isoformat(),'request_id':'shift-for-employee-01'}
    assert c.post('/api/admin/r10/shifts',headers=h,json={**base,'slug':'central'}).status_code==201
    conflicting={**base,'slug':'mall','request_id':'shift-for-employee-02'}
    assert c.post('/api/admin/r10/shifts',headers=h,json=conflicting).status_code==409
    foreign,auth_other=second_org(site)
    assert c.post('/api/admin/r10/shifts',headers=auth_other,json={**base,'request_id':'shift-other-valid-001', 'slug':'central'}).status_code==404
    assert c.post('/api/admin/r10/shifts',headers=auth_other,json={**base,'request_id':'shift-invalid-001','slug':'other-r10'}).status_code==404

def test_service_standards_and_actual_response_times(site):
    c,h,dbmod=site
    assert c.put('/api/admin/r10/service/targets',headers=h,json={'slug':'central','accept_minutes':4,'resolve_minutes':2}).status_code==422
    assert c.put('/api/admin/r10/service/targets',headers=h,json={'slug':'central','accept_minutes':3,'resolve_minutes':14}).status_code==200
    p=c.post('/api/admin/r07/assistance/points',headers=h,json={'slug':'central','name':'Примерочная 1'})
    assert p.status_code==201,p.text
    now=datetime.now(timezone.utc)
    with dbmod.connect() as db:
        sid=store_id(site)
        # A historical, completed and delayed assistance request to exercise SLA.
        db.execute('INSERT INTO assistance_requests_r07(point_id,store_id,request_id,category,status,created_at,accepted_at,resolved_at) VALUES(?,?,?,?,?,?,?,?)',
          (p.json()['id'],sid,'historical-sla-unique-1','size','resolved',(now-timedelta(minutes=22)).isoformat(timespec='seconds'),
           (now-timedelta(minutes=15)).isoformat(timespec='seconds'),(now-timedelta(minutes=8)).isoformat(timespec='seconds')))
        db.commit()
    d=c.get('/api/admin/r10/service',headers=h).json()
    assert d['accepted']==1 and d['resolved']==1 and d['accept_rate_percent']==0.0
    assert d['p50_accept_minutes']==7.0 and d['resolve_rate_percent']==100.0

def test_pulse_needs_paired_kiosk_idempotent_and_replace(site):
    c,h,dbmod=site
    campaign={'slug':'central','title':'Причина отказа','question':'Что сегодня помешало вам купить вещь?',
              'options':['Не подошёл размер','Высокая цена','Просто смотрел']}
    created=c.post('/api/admin/r10/pulse',headers=h,json=campaign)
    assert created.status_code==201,created.text
    cid=created.json()['id']
    assert c.post(f'/api/admin/r10/pulse/{cid}/activate',headers=h).status_code==409
    pair=c.post('/api/admin/kiosks/central/rotate',headers=h).json()
    token=pair['token'];head={'X-OSMANX-Kiosk':token}
    assert c.get('/api/public/r10/pulse/central').status_code==401
    assert c.post(f'/api/admin/r10/pulse/{cid}/activate',headers=h).status_code==200
    assert c.get('/api/public/r10/pulse/central',headers=head).json()['question']==campaign['question']
    payload={'campaign_id':cid,'request_id':'pulse-request-r10-unique-001','option_index':1}
    r=c.post('/api/public/r10/pulse/central',headers=head,json=payload)
    assert r.status_code==201,r.text
    assert c.post('/api/public/r10/pulse/central',headers=head,json=payload).json()['duplicate']
    assert c.post('/api/public/r10/pulse/central',headers=head,json={**payload,'option_index':0}).status_code==409
    assert c.post('/api/public/r10/pulse/central',headers=head,json={**payload,'request_id':'pulse-request-r10-unique-002','option_index':3}).status_code==422
    assert c.get('/api/admin/r10/pulse',headers=h).json()['items'][0]['counts']=={'1':1}
    new=c.post('/api/admin/r10/pulse',headers=h,json={**campaign,'title':'Следующий опрос'}).json()['id']
    assert c.post(f'/api/admin/r10/pulse/{new}/activate',headers=h).status_code==200
    assert c.get('/api/admin/r10/pulse',headers=h).json()['items'][0]['active']==1
    assert c.post('/api/public/r10/pulse/central',headers=head,json={**payload,'request_id':'pulse-request-r10-unique-003'}).status_code==409
    new_token=c.post('/api/admin/kiosks/central/rotate',headers=h).json()['token']
    assert c.get('/api/public/r10/pulse/central',headers=head).status_code==401
    assert c.get('/api/public/r10/pulse/central',headers={'X-OSMANX-Kiosk':new_token}).status_code==200
    assert c.post(f'/api/admin/r10/pulse/{new}/disable',headers=h).status_code==200
    assert c.get('/api/public/r10/pulse/central',headers={'X-OSMANX-Kiosk':new_token}).status_code==404

def test_pulse_org_isolation(site):
    c,h,_=site
    sid,h2=second_org(site)
    campaign={'slug':'central','title':'Не нашли товар','question':'Что хотелось бы улучшить в магазине?',
              'options':['Размеры','Модели']}
    assert c.post('/api/admin/r10/pulse',headers=h2,json=campaign).status_code==404
    created=c.post('/api/admin/r10/pulse',headers=h,json=campaign).json()['id']
    assert c.post(f'/api/admin/r10/pulse/{created}/activate?slug=other-r10',headers=h2).status_code==404
    assert c.get('/api/admin/r10/pulse?slug=central',headers=h2).status_code==404

def test_incident_scan_notes_task_and_no_duplicated_task(site):
    c,h,dbmod=site
    sid=store_id(site)
    with dbmod.connect() as db:
        for i in range(3):
            db.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                       (sid,10000,'r10-pos',dbmod.now_iso(),f'missing-lines-{i}'))
        db.commit()
    created=c.post('/api/admin/r10/incidents/scan',headers=h)
    assert created.status_code==200,created.text
    assert created.json()['created']==1
    assert c.post('/api/admin/r10/incidents/scan',headers=h).json()['created']==0
    items=c.get('/api/admin/r10/incidents',headers=h).json()['items']
    assert len(items)==1
    iid=items[0]['id']
    assert c.patch(f'/api/admin/r10/incidents/{iid}',headers=h,json={'status':'resolved','note':'Проверили чек'}).status_code==409
    result=c.patch(f'/api/admin/r10/incidents/{iid}',headers=h,json={'status':'acknowledged','note':'Проверить загрузку кассы','make_task':True})
    assert result.status_code==200,result.text
    assert result.json()['task_id']
    assert c.patch(f'/api/admin/r10/incidents/{iid}',headers=h,json={'status':'acknowledged','note':'Перепроверяем загрузку кассы','make_task':True}).json()['task_id']==result.json()['task_id']
    assert c.patch(f'/api/admin/r10/incidents/{iid}',headers=h,json={'status':'resolved','note':'Кассовый импорт проверен повторно'}).status_code==200
    assert c.patch(f'/api/admin/r10/incidents/{iid}',headers=h,json={'status':'acknowledged','note':'Открываем его снова'}).status_code==409
    with dbmod.connect() as db:
        count=db.execute("SELECT COUNT(*) FROM action_tasks_r08 WHERE request_id=?",(f'r10-incident-{iid}',)).fetchone()[0]
        assert count==1

def test_incident_tenant_scope(site):
    c,h,dbmod=site
    sid,h2=second_org(site)
    with dbmod.connect() as db:
        row=db.execute("INSERT INTO incidents_r10(organization_id,store_id,incident_key,kind,title,evidence,severity,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
          (1,store_id(site),'r10-test','test','Тестовые строки','Запись только этой организации','medium','new',dbmod.now_iso(),dbmod.now_iso()))
        db.commit()
    assert c.patch(f'/api/admin/r10/incidents/{row.lastrowid}',headers=h2,json={'status':'acknowledged','note':'Проверили не свой инцидент'}).status_code==404
    assert c.get('/api/admin/r10/incidents?slug=central',headers=h2).status_code==404

def test_pulse_rate_limit_is_store_scoped_and_duplicate_safe(site):
    c,h,dbmod=site
    campaign={'slug':'central','title':'Опрос в торговом зале','question':'Чего вам не хватает в ассортименте?',
              'options':['Размеров','Фасонов']}
    cid=c.post('/api/admin/r10/pulse',headers=h,json=campaign).json()['id']
    secret=c.post('/api/admin/kiosks/central/rotate',headers=h).json()['token']
    assert c.post(f'/api/admin/r10/pulse/{cid}/activate',headers=h).status_code==200
    with dbmod.connect() as db:
        sid=store_id(site)
        for i in range(120):
            db.execute('INSERT INTO pulse_responses_r10(campaign_id,store_id,request_id,option_index,created_at) VALUES(?,?,?,?,?)',
                       (cid,sid,f'preloaded-pulse-r10-{i:03}',0,dbmod.now_iso()))
        db.commit()
    assert c.post('/api/public/r10/pulse/central',headers={'X-OSMANX-Kiosk':secret},
                 json={'request_id':'new-over-limit-00001','campaign_id':cid,'option_index':1}).status_code==429
    # Idempotent retry of an already accepted response remains possible when capped.
    replay=c.post('/api/public/r10/pulse/central',headers={'X-OSMANX-Kiosk':secret},
                 json={'request_id':'preloaded-pulse-r10-000','campaign_id':cid,'option_index':0})
    assert replay.status_code==201 and replay.json()['duplicate']


def test_pulse_retention_dry_run_and_apply(site):
    c,h,dbmod=site
    cid=c.post('/api/admin/r10/pulse',headers=h,json={'slug':'central','title':'Опросная кампания','question':'Что стоит добавить в магазин?',
              'options':['Обувь','Одежду']}).json()['id']
    with dbmod.connect() as db:
        sid=store_id(site)
        old=(datetime.now(timezone.utc)-timedelta(days=105)).isoformat(timespec='seconds')
        db.execute('INSERT INTO pulse_responses_r10(campaign_id,store_id,request_id,option_index,created_at) VALUES(?,?,?,?,?)',
                   (cid,sid,'expired-pulse-r10-uuid-001',0,old))
        db.commit()
    import scripts.purge_pulse_r10 as maintenance
    importlib.reload(maintenance)
    assert maintenance.purge(apply=False)['total']==1
    assert c.get('/api/admin/r10/pulse',headers=h).json()['items'][0]['responses']==1
    assert maintenance.purge(apply=True)['total']==1
    assert c.get('/api/admin/r10/pulse',headers=h).json()['items'][0]['responses']==0


def test_viewer_can_read_but_cannot_change_settings(site):
    c,h,dbmod=site
    from backend.security import hash_password
    with dbmod.connect() as db:
        sid=store_id(site)
        uid=db.execute('''INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)''',
          (1,'viewer-r10@test.local',hash_password('viewer-password-2026'),'viewer',dbmod.now_iso())).lastrowid
        db.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(uid,sid))
        db.commit()
    response=c.post('/api/auth/login',json={'email':'viewer-r10@test.local','password':'viewer-password-2026'})
    assert response.status_code==200
    hv={'Authorization':'Bearer '+response.json()['token']}
    for path in ('benchmark','shifts','service','pulse','incidents'):
        assert c.get('/api/admin/r10/'+path,headers=hv).status_code==200
    assert c.put('/api/admin/r10/service/targets',headers=hv,json={'slug':'central','accept_minutes':4,'resolve_minutes':12}).status_code==403
    assert c.post('/api/admin/r10/incidents/scan',headers=hv).status_code==403
    assert c.post('/api/admin/r10/pulse',headers=hv,json={'slug':'central','title':'Несанкционированный',
                'question':'Что нравится в этом магазине?','options':['Цены','Товары']}).status_code==403
