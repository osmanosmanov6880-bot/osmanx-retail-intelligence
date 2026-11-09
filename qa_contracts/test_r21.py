"""R2.1 local integration tests: real SQLite tables and R2.0 router.

The imported R2.0 fixture provides minimal shims for *older* auth helpers;
these tests do not claim complete production auth integration or full CI.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa_contracts'))
import test_r20
from test_r20 import Principal
from backend.r21 import ensure_schema, build_router, _preflight, sha_text


@pytest.fixture
def site(tmp_path):
    generated=test_r20.site.__wrapped__(tmp_path)
    client,acting,connect=next(generated)
    with connect() as db:
        db.execute("ALTER TABLE stores ADD COLUMN name TEXT NOT NULL DEFAULT 'Магазин'")
        db.executescript('''
          CREATE TABLE pilots_r15 (id INTEGER PRIMARY KEY,organization_id INTEGER,store_id INTEGER,
            status TEXT NOT NULL DEFAULT 'draft',started_at TEXT);
        ''')
        ensure_schema(db)
        db.commit()
    def admin():return acting['user']
    def db_conn():
        with connect() as c:yield c
    client.app.include_router(build_router(admin,db_conn))
    try:yield client,acting,connect
    finally:
        try:next(generated)
        except StopIteration:pass


def start(site):
    client,_,_=site
    p=client.post('/api/admin/r20/days',json={'slug':'central','business_day':str(date.today())})
    assert p.status_code==201,p.text
    return p.json()['id']


def prepare_reviewed(site):
    c,acting,connect=site
    day=start(site)
    handover=test_r20.fill(site,day)
    acting['user']=Principal(2,1,'manager@test','manager')
    ack=c.post(f'/api/admin/r20/handovers/{handover}/ack',json={'note':'Подтверждаю журнал и передачу оборудования'})
    assert ack.status_code==200,ack.text
    req=c.post(f'/api/admin/r20/days/{day}/review-request')
    assert req.status_code==200,req.text
    acting['user']=Principal(1,1,'owner@test','owner')
    review=c.post(f'/api/admin/r20/days/{day}/review',json={'decision':'reviewed','note':'Сверены документы и наблюдения работы магазина'})
    assert review.status_code==200,review.text
    return day


def pilot(site,store_id=1):
    _,_,connect=site
    with connect() as db:
        p=db.execute('INSERT INTO pilots_r15(organization_id,store_id,status) VALUES(?,?,?)',(1,store_id,'draft'))
        db.commit();return p.lastrowid


def test_portfolio_scoped_and_csv(site):
    c,actor,connect=site
    day=start(site)
    r=c.get('/api/admin/r21/portfolio')
    assert r.status_code==200,r.text
    row=next(x for x in r.json()['stores'] if x['slug']=='central')
    assert row['readiness_id']==day and row['status']=='draft'
    assert c.get('/api/admin/r21/portfolio.csv').status_code==200
    actor['user']=Principal(9,2,'foreign@test','owner')
    other=c.get('/api/admin/r21/portfolio').json()
    assert all(x['slug']!='central' for x in other['stores'])
    assert c.get('/api/admin/r21/continuity?slug=central').status_code==404
    assert c.get(f'/api/admin/r21/continuity?slug=central&readiness_id={day}').status_code==404


def test_calibration_drift_and_unreliable_samples(site):
    c,_,_=site
    day=start(site)
    empty=c.get('/api/admin/r21/drift').json()
    assert empty['status']=='no_data'
    for i,actual in enumerate((100,114,99)):
        r=c.post(f'/api/admin/r20/days/{day}/calibrations',json={
          'request_id':f'r21-drift-sample-{i:04}','reference_count':100,'counter_count':actual,
          'method':'Два сотрудника сравнили счётчик с ручным подсчётом'})
        assert r.status_code==201,r.text
    report=c.get('/api/admin/r21/drift').json()
    assert report['status']=='drift' and report['above_10pct']==1
    assert report['valid_calibrations']==3
    assert c.get('/api/admin/r21/drift?days=4').status_code==422


def test_continuity_catches_new_events_after_freeze(site):
    c,_,connect=site
    day=prepare_reviewed(site)
    before=c.get(f'/api/admin/r21/continuity?readiness_id={day}').json()
    assert before['status']=='verified_rows'
    with connect() as db:
        stamp=str(date.today())+'T16:00:00+00:00'
        db.execute('INSERT INTO visits(store_id,quantity,source,occurred_at) VALUES(?,?,?,?)',(1,19,'manual',stamp))
        db.commit()
    after=c.get(f'/api/admin/r21/continuity?readiness_id={day}').json()
    assert after['status']=='changed'
    assert after['delta']['visits']==19
    assert 'События изменились' in ' '.join(after['issues'])


def test_ticket_sync_assignment_independent_resolution_and_history(site):
    c,actor,connect=site
    day=start(site)
    actor['user']=Principal(2,1,'manager@test','manager')
    first=c.post('/api/admin/r21/tickets/sync',json={'readiness_id':day})
    assert first.status_code==200,first.text
    assert first.json()['issues_found']>0
    tid=first.json()['added'][0]
    again=c.post('/api/admin/r21/tickets/sync',json={'readiness_id':day}).json()
    assert len(again['added'])==0
    assert tid in again['existing']
    assert c.patch(f'/api/admin/r21/tickets/{tid}',json={'status':'working','note':'Пока никто не назначен'}).status_code==409
    assign=c.patch(f'/api/admin/r21/tickets/{tid}/assign',json={'owner':'Управляющий','due_date':str(date.today()+timedelta(days=2))})
    assert assign.status_code==200,assign.text
    assert c.patch(f'/api/admin/r21/tickets/{tid}',json={'status':'working','note':'Обнаружена проблема и начата проверка'}).status_code==200
    assert c.patch(f'/api/admin/r21/tickets/{tid}',json={'status':'verified','note':'Сам проверяю свою задачу'}).status_code==403
    actor['user']=Principal(1,1,'owner@test','owner')
    verified=c.patch(f'/api/admin/r21/tickets/{tid}',json={'status':'verified','note':'Независимо проверил исправление по протоколу'})
    assert verified.status_code==200,verified.text
    assert c.patch(f'/api/admin/r21/tickets/{tid}',json={'status':'working','note':'Не предусмотрено повторное открытие'}).status_code==409
    history=c.get(f'/api/admin/r21/tickets/{tid}/history').json()['items']
    assert len(history)==3
    assert [x['to_status'] for x in history][-2:]==['working','verified']


def test_safe_pilot_start_requires_independent_review(site):
    c,acting,connect=site
    day=start(site);pid=pilot(site)
    denied=c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day})
    assert denied.status_code==409
    report=c.get(f'/api/admin/r21/pilots/{pid}/preflight?readiness_id={day}').json()
    assert report['ready'] is False
    day=prepare_reviewed_different_day(site)
    start_ok=c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day})
    assert start_ok.status_code==200,start_ok.text
    assert start_ok.json()['status']=='running'
    repeated=c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day})
    assert repeated.status_code==200 and repeated.json()['duplicate']
    proof=c.get(f'/api/admin/r21/pilots/{pid}/startup-proof').json()
    assert proof['integrity'] is True
    with connect() as db:
        assert db.execute('SELECT status FROM pilots_r15 WHERE id=?',(pid,)).fetchone()['status']=='running'


def prepare_reviewed_different_day(site):
    c,actor,connect=site
    # The same business-day record is unique. Once started empty, fill it instead.
    day=c.get('/api/admin/r20/days').json()['items'][0]['id']
    handover=test_r20.fill(site,day)
    actor['user']=Principal(2,1,'manager@test','manager')
    c.post(f'/api/admin/r20/handovers/{handover}/ack',json={'note':'Второй сотрудник проверил все записи'})
    assert c.post(f'/api/admin/r20/days/{day}/review-request').status_code==200
    actor['user']=Principal(1,1,'owner@test','owner')
    assert c.post(f'/api/admin/r20/days/{day}/review',json={'decision':'reviewed','note':'Готовность подтверждена независимым владельцем'}).status_code==200
    return day


def test_safe_start_blocks_late_data_and_open_tickets(site):
    c,acting,connect=site
    day=prepare_reviewed(site)
    pid=pilot(site)
    c.post('/api/admin/r21/tickets/sync',json={'readiness_id':day})
    # Add late data after review: cannot grant a startup permit.
    with connect() as db:
        db.execute('INSERT INTO sales(store_id,occurred_at) VALUES(?,?)',(1,str(date.today())+'T23:00:00+00:00'))
        db.commit()
    r=c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day})
    assert r.status_code==409
    assert 'События изменились' in r.json()['detail']
    with connect() as db:
        assert db.execute('SELECT status FROM pilots_r15 WHERE id=?',(pid,)).fetchone()['status']=='draft'


def test_safe_start_blocks_changed_hash_and_other_store(site):
    c,acting,connect=site
    day=prepare_reviewed(site);pid=pilot(site)
    with connect() as db:
        db.execute('UPDATE readiness_reviews_r20 SET payload_json=? WHERE readiness_id=?',('tampered',day));db.commit()
    assert c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day}).status_code==409
    with connect() as db:
        db.execute('UPDATE readiness_reviews_r20 SET payload_sha=? WHERE readiness_id=?',('0'*64,day));db.commit()
    proof=c.get(f'/api/admin/r21/pilots/{pid}/preflight?readiness_id={day}').json()
    assert proof['ready'] is False and not proof['readiness_sha']


def test_idempotent_migration_and_snapshot_integrity(site):
    c,actor,connect=site
    day=prepare_reviewed(site);pid=pilot(site)
    assert c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day}).status_code==200
    with connect() as db:
        ensure_schema(db);ensure_schema(db)
        db.execute('UPDATE assurance_pilot_starts_r21 SET preflight_json=? WHERE pilot_id=?',('{"changed":true}',pid))
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    proof=c.get(f'/api/admin/r21/pilots/{pid}/startup-proof').json()
    assert proof['integrity'] is False and proof['report'] is None


def test_pilot_id_org_and_store_scope(site):
    c,actor,connect=site
    day=start(site);pid=pilot(site)
    actor['user']=Principal(8,2,'foreign@test','owner')
    assert c.get(f'/api/admin/r21/pilots/{pid}/preflight?readiness_id={day}').status_code==404
    assert c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day}).status_code==404


def test_safe_start_rejects_modified_check_data_after_review(site):
    c,_,connect=site
    day=prepare_reviewed(site);pid=pilot(site)
    with connect() as db:
        db.execute("UPDATE readiness_checks_r20 SET note='Forged source note' WHERE readiness_id=? AND key='tablet'",(day,))
        db.commit()
    result=c.get(f'/api/admin/r21/pilots/{pid}/preflight?readiness_id={day}').json()
    assert any('после независимой проверки' in x for x in result['issues'])
    assert c.post(f'/api/admin/r21/pilots/{pid}/safe-start',json={'readiness_id':day}).status_code==409


def test_safe_start_refuses_older_shift_when_new_draft_exists(site):
    c,_,connect=site
    day=prepare_reviewed(site);pid=pilot(site)
    later=(date.today()+timedelta(days=1)).isoformat()
    resp=c.post('/api/admin/r20/days',json={'slug':'central','business_day':later})
    assert resp.status_code==201,resp.text
    result=c.get(f'/api/admin/r21/pilots/{pid}/preflight?readiness_id={day}').json()
    assert not result['ready']
    assert 'более новая смена' in ' '.join(result['issues'])
