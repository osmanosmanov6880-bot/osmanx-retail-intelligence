"""R1.8: five workflow acceptance tests on a real isolated SQLite store."""
from __future__ import annotations
import importlib
import hashlib
import json
from datetime import date,timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

FORM={'slug':'central','request_id':'r18-survey-create-key-001','title':'Что помешало покупке?',
 'questions':[
  {'id':'purchase','title':'Удалось совершить покупку?', 'type':'choice','options':[{'id':'yes','label':'Да'},{'id':'no','label':'Нет'}]},
  {'id':'reason','title':'Почему не купили сегодня?', 'type':'choice','options':[{'id':'size','label':'Нужного размера нет'},{'id':'price','label':'Высокая цена'},{'id':'other','label':'Другое'}],
   'show_if':{'question':'purchase','equals':'no'}},
  {'id':'rating','title':'Как оцениваете посещение?', 'type':'rating'}]}

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path));monkeypatch.setenv('OSMANX_DEMO_MODE','1')
    import backend.database as database
    import backend.r15 as r15
    import backend.r17 as r17
    import backend.r18 as r18
    importlib.reload(database)
    database.initialize_db(demo=True)
    with database.connect() as db:
        r15.ensure_schema(db);r17.ensure_schema(db);r18.ensure_schema(db);db.commit()
    from backend.security import Principal
    def admin():return Principal(0,1,'demo@osmanx.local','owner',demo=True)
    def db_conn():
        with database.connect() as conn:yield conn
    app=FastAPI()
    app.include_router(r15.build_router(admin,db_conn))
    app.include_router(r17.build_router(admin,db_conn))
    app.include_router(r18.build_router(admin,db_conn))
    with TestClient(app) as c:yield c,database


def populate(site,count=4):
    c,_=site
    form=c.post('/api/admin/r17/forms',json=FORM)
    assert form.status_code==201,form.text
    fid=form.json()['id']
    pub=c.post(f'/api/admin/r17/forms/{fid}/publish');assert pub.status_code==200,pub.text
    placement=c.post('/api/admin/r17/placements',json={'form_id':fid,'name':'Выход из магазина','medium':'qr'})
    assert placement.status_code==201,placement.text
    p=placement.json();key={'X-OSMANX-Voice-Key':p['secret']}
    path=f"/api/voice/r17/{p['public_id']}"
    cfg=c.get(path+'/form',headers=key).json()
    for i in range(count):
        body={'request_id':f'r18-customer-session-{i:05}','version_hash':cfg['version_hash']}
        opened=c.post(path+'/open',json=body,headers=key)
        assert opened.status_code==201,opened.text
        submitted=c.post(path+'/submit',json={**body,'answers':{'purchase':'no','reason':'size','rating':3}},headers=key)
        assert submitted.status_code==201,submitted.text
    return p,pub.json()['version_id']


def form_hyp(p,v):
    return {'slug':'central','request_id':'r18-hypothesis-req-0001','placement_id':p['id'],'version_id':v,
            'question_id':'reason','choice':'size','days':14,
            'title':'Проверить дефицит размеров после опросов покупателей','category':'stock'}


def create_hyp(site):
    c,_=site
    p,v=populate(site)
    data=form_hyp(p,v)
    resp=c.post('/api/admin/r18/hypotheses',json=data)
    assert resp.status_code==201,resp.text
    return resp.json()['id'],p,v,data


def pilot_spec():
    today=date.today();base_start=today-timedelta(days=14)
    return {'request_id':'r18-bridge-pilot-000001','metric':'receipts_per_100_entries','source_mode':'manual',
       'before_start':str(base_start),'before_end':str(base_start+timedelta(days=6)),
       'after_start':str(base_start+timedelta(days=7)),'after_end':str(base_start+timedelta(days=13)),
       'budget_kopeks':150000}


def test_signals_and_frozen_evidence(site):
    c,_=site;p,v=populate(site)
    report=c.get('/api/admin/r18/signals?days=14')
    assert report.status_code==200,report.text
    signal=next(x for x in report.json()['items'] if x['question_id']=='reason')
    assert signal['support']==4 and signal['eligible_answers']==4
    first=c.post('/api/admin/r18/hypotheses',json=form_hyp(p,v));assert first.status_code==201,first.text
    assert first.json()['evidence']['support']==4
    hid=first.json()['id']
    result=c.get(f'/api/admin/r18/hypotheses/{hid}').json()['item']
    assert result['evidence_valid'] is True and result['evidence']['support']==4
    again=c.post('/api/admin/r18/hypotheses',json=form_hyp(p,v));assert again.status_code==201 and again.json()['duplicate']
    conflict=c.post('/api/admin/r18/hypotheses',json={**form_hyp(p,v),'choice':'price'})
    assert conflict.status_code==409


def test_mutation_pilot_compatible_and_idempotent(site):
    c,db=site;hid,p,v,data=create_hyp(site)
    assert c.post(f'/api/admin/r18/hypotheses/{hid}/pilot',json=pilot_spec()).status_code==409
    state=c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={'status':'investigating','note':'Проверим подтверждения со склада'})
    assert state.status_code==200,state.text
    pilot=c.post(f'/api/admin/r18/hypotheses/{hid}/pilot',json=pilot_spec());assert pilot.status_code==201,pilot.text
    pid=pilot.json()['id']
    assert c.get(f'/api/admin/r15/pilots/{pid}').status_code==200
    again=c.post(f'/api/admin/r18/hypotheses/{hid}/pilot',json=pilot_spec())
    assert again.status_code==201 and again.json()['duplicate']
    assert c.post(f'/api/admin/r18/hypotheses/{hid}/pilot',json={**pilot_spec(),'budget_kopeks':1}).status_code==409
    assert c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={'status':'resolved','note':'Пилот ещё не завершился документально'}).status_code==409
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pilots_r15 WHERE id=?',(pid,)).fetchone()[0]==1


def test_task_lifecycle_and_owner_evidence(site):
    c,_=site;hid,*_=create_hyp(site)
    t={'request_id':'r18-task-request-000001','title':'Проверить размеры и сроки доставки','owner':'Управляющий магазина',
       'due_date':str(date.today()+timedelta(days=5))}
    created=c.post(f'/api/admin/r18/hypotheses/{hid}/tasks',json=t)
    assert created.status_code==201,created.text
    tid=created.json()['id']
    assert c.post(f'/api/admin/r18/hypotheses/{hid}/tasks',json=t).json()['duplicate']
    assert c.post(f'/api/admin/r18/hypotheses/{hid}/tasks',json={**t,'owner':'Другой'}).status_code==409
    assert c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={'status':'investigating','note':'Получили первую партию запросов'}).status_code==200
    assert c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={'status':'resolved','note':'Не закончили задачу, результат рано'}).status_code==409
    assert c.patch(f'/api/admin/r18/tasks/{tid}',json={'status':'done','note':'Пропущен этап работы'}).status_code==409
    assert c.patch(f'/api/admin/r18/tasks/{tid}',json={'status':'working','note':'Сверяем с данными склада'}).status_code==200
    assert c.patch(f'/api/admin/r18/tasks/{tid}',json={'status':'done','note':'Сверили размеры и зафиксировали итог документом'}).status_code==200
    assert len(c.get(f'/api/admin/r18/tasks/{tid}/history').json()['items'])==2
    assert c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={'status':'resolved','note':'Задача завершена и результат зафиксирован'}).status_code==200


def test_tamper_alert_and_csv_escaping(site):
    c,db=site;hid,*_=create_hyp(site)
    with db.connect() as conn:
        conn.execute("UPDATE bridge_hypotheses_r18 SET title=? WHERE id=?",('=IMPORT(\"http://bad.example\")',hid))
        conn.execute('UPDATE bridge_hypotheses_r18 SET evidence_json=? WHERE id=?',('{"support":99999}',hid));conn.commit()
    summary=c.get('/api/admin/r18/board').json()
    assert summary['proof_alerts']==1
    csv=c.get('/api/admin/r18/board.csv')
    assert csv.status_code==200 and 'text/csv' in csv.headers.get('content-type','')
    assert "'=IMPORT" in csv.text


def test_reject_invalid_scope_or_unauthorized_role(site):
    c,db=site;hid,p,v,_=create_hyp(site)
    from backend.r18 import _scope, _task_scope
    from backend.security import Principal
    with db.connect() as conn:
        other=conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('second','Other',date.today().isoformat())).lastrowid
        outsider=Principal(99,other,'another@org.test','owner')
        with pytest.raises(Exception):_scope(conn,hid,outsider)
        viewer=Principal(99,1,'viewer@org.test','viewer')
        # A viewer can read but may not mutate protected resources.
        from backend.security import require_role
        with pytest.raises(Exception):require_role(viewer,'owner','manager')
    assert c.get('/api/admin/r18/signals?days=91').status_code==422
    assert c.post('/api/admin/r18/hypotheses',json={**form_hyp(p,v),'request_id':'r18-wrong-version-0001','version_id':999999}).status_code==404
    assert c.post('/api/admin/r18/hypotheses',json={**form_hyp(p,v),'request_id':'r18-hypothesis-wrong-12', 'question_id':'rating'}).status_code==422


def test_schema_idempotent_and_atomic_snapshot(site):
    c,db=site;hid,*_=create_hyp(site)
    from backend.r18 import ensure_schema
    with db.connect() as conn:
        ensure_schema(conn);ensure_schema(conn)
        row=conn.execute('SELECT evidence_json,evidence_sha FROM bridge_hypotheses_r18 WHERE id=?',(hid,)).fetchone()
        assert hashlib.sha256(json.dumps(json.loads(row['evidence_json']),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==row['evidence_sha']
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_real_http_authorization_and_cross_tenant_visibility(site):
    """An actual Bearer-token dependency protects routes beyond the demo owner."""
    c,db=site;hid,p,v,_=create_hyp(site)
    from backend.security import hash_password,issue_session,verify_session
    from fastapi import Depends,Header,HTTPException
    from backend.r18 import build_router
    from backend.security import Principal
    from fastapi.testclient import TestClient
    secret='r18-test-session-secret-with-sufficient-entropy-2026'
    with db.connect() as conn:
        stamp=date.today().isoformat()
        owner=conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                (1,'owner@local.test',hash_password('long-password-2026'), 'owner',stamp)).lastrowid
        viewer=conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                (1,'viewer@local.test',hash_password('long-password-2026'), 'viewer',stamp)).lastrowid
        other=conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('r18other','Другой аккаунт',stamp)).lastrowid
        outsider=conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                (other,'other@local.test',hash_password('long-password-2026'),'owner',stamp)).lastrowid
        store=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(viewer,store));conn.commit()
        tokens={role:issue_session(conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(),secret)
                for role,uid in [('owner',owner),('viewer',viewer),('other',outsider)]}

    def conn_dep():
        with db.connect() as conn:yield conn
    def admin_dep(authorization:str|None=Header(default=None),conn=Depends(conn_dep)):
        if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Необходимо войти')
        return verify_session(authorization.split(' ',1)[1],secret,conn)
    app=FastAPI();app.include_router(build_router(admin_dep,conn_dep))
    with TestClient(app) as auth:
        path=f'/api/admin/r18/hypotheses/{hid}'
        headers=lambda role:{'Authorization':'Bearer '+tokens[role]}
        assert auth.get(path).status_code==401
        assert auth.get(path,headers=headers('other')).status_code==404
        assert auth.get('/api/admin/r18/board?slug=central',headers=headers('other')).status_code==404
        assert auth.get(path,headers=headers('viewer')).status_code==200
        assert auth.post('/api/admin/r18/hypotheses',headers=headers('viewer'),json=form_hyp(p,v)).status_code==403
        assert auth.patch(f'{path}/status',headers=headers('viewer'),json={
            'status':'investigating','note':'Тестовое обновление гипотезы'}).status_code==403
        assert auth.get(path,headers=headers('owner')).status_code==200


def test_bridge_refuses_tampered_voice_evidence(site):
    c,db=site;hid,*_=create_hyp(site)
    assert c.patch(f'/api/admin/r18/hypotheses/{hid}/status',json={
      'status':'investigating','note':'Начинаем анализ записанных причин'}).status_code==200
    with db.connect() as conn:
        conn.execute('UPDATE bridge_hypotheses_r18 SET evidence_json=? WHERE id=?',
                     ('{"support":100000}',hid));conn.commit()
    denied=c.post(f'/api/admin/r18/hypotheses/{hid}/pilot',json=pilot_spec())
    assert denied.status_code==409
    assert 'Контрольная сумма' in denied.json()['detail']
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM pilots_r15').fetchone()[0]==0
