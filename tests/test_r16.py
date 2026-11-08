"""R1.6 acceptance: five workflows, RBAC, idempotency, integrity and dates."""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

TODAY=lambda: datetime.now(ZoneInfo('Europe/Moscow')).date()

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DEMO_MODE','0')
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    monkeypatch.setenv('OSMANX_SESSION_SECRET','session-master-secret-super-long-123456789')
    monkeypatch.setenv('OSMANX_DEVICE_MASTER_SECRET','device-master-secret-super-long-123456789')
    import backend.database as database
    import backend.app as module
    importlib.reload(database);importlib.reload(module)
    with TestClient(module.app) as client:
        login=client.post('/api/auth/login',json={'email':'owner@osmanx.local','password':'bootstrap-super-secret-2026'})
        assert login.status_code==200,login.text
        yield client,{'Authorization':'Bearer '+login.json()['token']},database


def make_pilot(site,request='r16-pilot-key-01',slug='central',metric='receipts_per_100_entries'):
    c,h,_=site;t=TODAY()
    payload={'slug':slug,'request_id':request,'title':'Снижение потерь от отсутствующих размеров',
             'hypothesis':'Повысим доступность размеров, затем сравним число чеков на вход.',
             'metric':metric,'source_mode':'manual','before_start':str(t-timedelta(days=14)),
             'before_end':str(t-timedelta(days=8)),
             'after_start':str(t-timedelta(days=7)),'after_end':str(t-timedelta(days=1)),
             'budget_kopeks':200000}
    r=c.post('/api/admin/r15/pilots',json=payload,headers=h)
    assert r.status_code==201,r.text
    return r.json()['id']


def seed_days(site,receipts_before=2,receipts_after=3):
    c,h,db=site
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        for before in (True,False):
            for i in range(7):
                d=TODAY()-timedelta(days=(14 if before else 7)-i)
                stamp=d.isoformat()+'T13:00:00+03:00'
                conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                             (store,100,'manual',stamp,f'r16-v-{before}-{i}'))
                for j in range(receipts_before if before else receipts_after):
                    conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                                 (store,1000000,'pos',stamp,f'r16-s-{before}-{i}-{j}'))
        conn.commit()


def attest(site,pid):
    c,h,_=site
    for cat in ('traffic','pos'):
        r=c.post(f'/api/admin/r15/pilots/{pid}/sources',json={'category':cat,'status':'checked','note':'Сверено оператором по первичным записям'},headers=h)
        assert r.status_code==200,r.text


def activate(site,pid):
    c,h,_=site
    assert c.post(f'/api/admin/r15/pilots/{pid}/start',headers=h).status_code==200
    a=c.post(f'/api/admin/r15/pilots/{pid}/actions',json={'request_id':'r16-action-seed-001','category':'assortment',
        'description':'Ввели учёт отсутствующих размеров и проверили фактическое наличие',
        'cost_kopeks':100000,'evidence':'pilot-manual-17'},headers=h)
    assert a.status_code==201,a.text


def other_owner(site):
    c,h,db=site
    from backend.security import hash_password
    with db.connect() as conn:
        conn.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                     (1,'reviewer@osmanx.local','Второй владелец',hash_password('independent-owner-2026'),
                      'owner',datetime.now(ZoneInfo('Europe/Moscow')).isoformat()))
        conn.commit()
    r=c.post('/api/auth/login',json={'email':'reviewer@osmanx.local','password':'independent-owner-2026'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}


def test_all_new_endpoints_require_session(site):
    c,h,_=site
    pid=make_pilot(site)
    for url in ('/portfolio','/portfolio.csv',f'/pilots/{pid}/quality',f'/pilots/{pid}/scenarios',f'/pilots/{pid}/rollout',f'/pilots/{pid}/followups'):
        assert c.get('/api/admin/r16'+url).status_code==401,url
    assert c.post(f'/api/admin/r16/pilots/{pid}/scenarios',json={}).status_code==401


def test_portfolio_and_quality_flags_are_not_silent_zeroes(site):
    c,h,_=site;pid=make_pilot(site)
    q=c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=h).json()
    assert q['status']=='needs_attention' and q['blocking']>0
    assert any(x['code']=='baseline_gaps' for x in q['checks'])
    result=c.get('/api/admin/r16/portfolio',headers=h).json()
    assert result['total']==1 and result['items'][0]['id']==pid
    assert result['items'][0]['quality']=='needs_attention'
    csv=c.get('/api/admin/r16/portfolio.csv',headers=h)
    assert csv.status_code==200 and 'text/csv' in csv.headers['content-type']


def test_complete_synthetic_schedule_generates_reviewable_sources(site):
    c,h,_=site;pid=make_pilot(site);seed_days(site);attest(site,pid)
    q=c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=h)
    assert q.status_code==200,q.text
    data=q.json();assert data['status']=='reviewable',data['checks']
    assert data['baseline']['visits']==700 and data['intervention']['visits']==700
    assert data['delta']==1.0 and data['blocking']==0


def test_scenario_idempotency_conflict_and_exact_kopeks(site):
    c,h,_=site;pid=make_pilot(site);seed_days(site);attest(site,pid);activate(site,pid)
    body={'request_id':'r16-scenario-000001','ticket_kopeks':500000,'gross_margin_bps':4000,
          'note':'Допущения руководителя: средний чек и маржа из внутренней оценки'}
    first=c.post(f'/api/admin/r16/pilots/{pid}/scenarios',headers=h,json=body)
    assert first.status_code==201,first.text
    result=first.json()['result']
    assert result['observed_delta_receipts_per_100_entries']==1
    assert result['scenario_incremental_receipts']==7
    assert result['scenario_gross_contribution_kopeks']==1400000
    assert result['logged_actions_cost_kopeks']==100000
    assert result['scenario_net_after_logged_costs_kopeks']==1300000
    assert 'не означает причинный' in result['disclaimer']
    repeated=c.post(f'/api/admin/r16/pilots/{pid}/scenarios',headers=h,json=body)
    assert repeated.status_code==201 and repeated.json()['duplicate']
    conflict=c.post(f'/api/admin/r16/pilots/{pid}/scenarios',headers=h,json={**body,'ticket_kopeks':400000})
    assert conflict.status_code==409
    records=c.get(f'/api/admin/r16/pilots/{pid}/scenarios',headers=h).json()['items']
    assert len(records)==1


def test_scenario_unsupported_kpi_and_missing_data(site):
    c,h,_=site;pid=make_pilot(site,metric='feedback_per_100_entries')
    r=c.post(f'/api/admin/r16/pilots/{pid}/scenarios',headers=h,json={'request_id':'scenario-other-kpi-01',
       'ticket_kopeks':300000,'gross_margin_bps':4000,'note':'Подтверждаем экономику вручную'})
    assert r.status_code==422
    p2=make_pilot(site,request='r16-pilot-key-02')
    r=c.post(f'/api/admin/r16/pilots/{p2}/scenarios',headers=h,json={'request_id':'scenario-without-data-01',
       'ticket_kopeks':300000,'gross_margin_bps':4000,'note':'Пока нет наблюдаемых чеков'})
    assert r.status_code==201 and r.json()['result']['scenario_net_after_logged_costs_kopeks'] is None


def test_rollout_requires_frozen_snapshot_and_independent_owner(site):
    c,h,_=site;pid=make_pilot(site);seed_days(site);attest(site,pid);activate(site,pid)
    body={'request_id':'rollout-request-0001','proposal':'Проверить расширение на второй филиал только после валидации источников'}
    denied=c.post(f'/api/admin/r16/pilots/{pid}/rollout',json=body,headers=h)
    assert denied.status_code==409
    closed=c.post(f'/api/admin/r15/pilots/{pid}/close',headers=h,json={'decision':'completed',
                   'note':'Подтверждены зарегистрированные записи и ограничения методики'})
    assert closed.status_code==200,closed.text
    first=c.post(f'/api/admin/r16/pilots/{pid}/rollout',json=body,headers=h)
    assert first.status_code==201,first.text
    rid=first.json()['id']
    assert c.post(f'/api/admin/r16/pilots/{pid}/rollout',json=body,headers=h).json()['duplicate']
    assert c.post(f'/api/admin/r16/rollouts/{rid}/review',json={'decision':'approved','note':'Есть данные для обсуждения ограниченного внедрения'},headers=h).status_code==409
    reviewer=other_owner(site)
    approved=c.post(f'/api/admin/r16/rollouts/{rid}/review',json={'decision':'approved','note':'Подтверждаю ограниченный пилот, без автоматического запуска'},headers=reviewer)
    assert approved.status_code==200,approved.text
    assert approved.json()['state']=='approved'
    assert c.post(f'/api/admin/r16/rollouts/{rid}/review',json={'decision':'approved','note':'Повторная проверка не требуется'},headers=reviewer).status_code==409


def test_rollout_blocks_unverified_or_tampered_snapshot(site):
    c,h,db=site;pid=make_pilot(site);activate(site,pid)
    c.post(f'/api/admin/r15/pilots/{pid}/close',headers=h,json={'decision':'completed','note':'Недостаточно данных для вывода по продажам'})
    body={'request_id':'rollout-unverified-01','proposal':'Нужно провести дополнительный пилот и сверить кассовые чеки'}
    create=c.post(f'/api/admin/r16/pilots/{pid}/rollout',json=body,headers=h)
    assert create.status_code==201,create.text
    reviewer=other_owner(site)
    assert c.post(f"/api/admin/r16/rollouts/{create.json()['id']}/review",headers=reviewer,
                  json={'decision':'approved','note':'Предлагаю внедрить несмотря на отсутствие данных'}).status_code==409
    assert c.post(f"/api/admin/r16/rollouts/{create.json()['id']}/review",headers=reviewer,
                  json={'decision':'rejected','note':'Данных недостаточно; требуется проверить источники'}).status_code==200
    with db.connect() as conn:
        conn.execute('UPDATE pilot_snapshots_r15 SET payload_json=? WHERE pilot_id=?',('tampered',pid));conn.commit()
    q=c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=h).json()
    assert any(x['code']=='snapshot_invalid' for x in q['checks'])


def test_followup_lifecycle_history_idempotency_and_conflicts(site):
    c,h,_=site;pid=make_pilot(site)
    body={'request_id':'r16-followup-00001','title':'Проверить остатки и подтвердить размеры','owner':'Директор',
         'due_date':str(TODAY()+timedelta(days=10))}
    first=c.post(f'/api/admin/r16/pilots/{pid}/followups',json=body,headers=h)
    assert first.status_code==201,first.text
    tid=first.json()['id']
    assert c.post(f'/api/admin/r16/pilots/{pid}/followups',json=body,headers=h).json()['duplicate']
    assert c.post(f'/api/admin/r16/pilots/{pid}/followups',json={**body,'title':'Новый смысл задачи'},headers=h).status_code==409
    assert c.patch(f'/api/admin/r16/followups/{tid}',json={'status':'done','note':'Проверено'},headers=h).status_code==409
    assert c.patch(f'/api/admin/r16/followups/{tid}',json={'status':'working','note':'Взято на проверку'},headers=h).status_code==200
    assert c.patch(f'/api/admin/r16/followups/{tid}',json={'status':'done','note':'Найдены документы по заказам'},headers=h).status_code==200
    assert c.patch(f'/api/admin/r16/followups/{tid}',json={'status':'working','note':'Повторно открыл'},headers=h).status_code==409
    history=c.get(f'/api/admin/r16/followups/{tid}/history',headers=h).json()['items']
    assert [x['next_state'] for x in history]==['working','done']


def test_no_cross_tenant_or_unassigned_store_visibility(site):
    c,h,db=site;pid=make_pilot(site)
    from backend.security import hash_password
    with db.connect() as conn:
        conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('other-tenant','Second business',datetime.now().astimezone().isoformat()))
        other=conn.execute("SELECT id FROM organizations WHERE slug='other-tenant'").fetchone()['id']
        conn.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                     (other,'other@tenant.test','Other',hash_password('tenant-password-2026'),'owner',datetime.now().astimezone().isoformat()))
        conn.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                     (1,'store-limited@osmanx.local','Limited',hash_password('limited-manager-2026'),'manager',datetime.now().astimezone().isoformat()))
        conn.commit()
    login=c.post('/api/auth/login',json={'email':'other@tenant.test','password':'tenant-password-2026'}).json()
    other_header={'Authorization':'Bearer '+login['token']}
    assert c.get('/api/admin/r16/portfolio',headers=other_header).json()['total']==0
    assert c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=other_header).status_code==404
    assert c.post(f'/api/admin/r16/pilots/{pid}/followups',headers=other_header,json={'request_id':'outside-tenant-request','title':'Любая задача для проверки','owner':'Кто-то','due_date':str(TODAY()+timedelta(days=4))}).status_code==404
    login2=c.post('/api/auth/login',json={'email':'store-limited@osmanx.local','password':'limited-manager-2026'}).json()
    limited={'Authorization':'Bearer '+login2['token']}
    assert c.get('/api/admin/r16/portfolio',headers=limited).json()['total']==0
    assert c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=limited).status_code==404


def test_frozen_pilot_detects_late_event_injection(site):
    c,h,db=site;pid=make_pilot(site);seed_days(site);attest(site,pid);activate(site,pid)
    close=c.post(f'/api/admin/r15/pilots/{pid}/close',headers=h,
                 json={'decision':'completed','note':'Сохраняем зафиксированный период без подмены данных'})
    assert close.status_code==200,close.text
    initial=c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=h).json()
    assert initial['blocking']==0
    with db.connect() as conn:
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        stamp=(TODAY()-timedelta(days=4)).isoformat()+'T17:00:00+03:00'
        conn.execute('INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                     (store,12,'manual',stamp,'r16-late-event'))
        conn.commit()
    now=c.get(f'/api/admin/r16/pilots/{pid}/quality',headers=h).json()
    assert any(x['code']=='snapshot_data_drift' for x in now['checks'])
