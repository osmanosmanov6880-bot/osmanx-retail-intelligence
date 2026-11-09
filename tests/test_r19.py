"""R1.9 Field Operations: server, SQLite, permissions and end-to-end R1.7 questionnaire integration."""
from __future__ import annotations
import importlib
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.testclient import TestClient

FORM={'slug':'central','request_id':'voice-r19-form-00001','title':'Ваше мнение о магазине',
  'questions':[{'id':'purchase','title':'Удалось ли купить товар?', 'type':'choice',
        'options':[{'id':'yes','label':'Да'},{'id':'no','label':'Нет'}]},
    {'id':'rating','title':'Оцените ваше посещение', 'type':'rating'}]}
SECRET='safe-session-secret-for-r19-test-long'

@pytest.fixture
def site(tmp_path,monkeypatch):
    monkeypatch.setenv('OSMANX_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('OSMANX_ADMIN_PASSWORD','bootstrap-super-secret-2026')
    monkeypatch.setenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local')
    import backend.database as database
    import backend.security as security
    import backend.r17 as r17
    import backend.r19 as r19
    importlib.reload(database)
    database.initialize_db(demo=False)
    with database.connect() as db:
        r17.ensure_schema(db);r19.ensure_schema(db);db.commit()
        owner=db.execute("SELECT * FROM users WHERE email='owner@osmanx.local'").fetchone()
        signed=security.issue_session(owner,SECRET)
    app=FastAPI()
    def conn():
        db=database.connect()
        try:yield db
        finally:db.close()
    def auth(authorization:str|None=Header(default=None),db=Depends(conn)):
        if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Требуется вход')
        return security.verify_session(authorization[7:],SECRET,db)
    app.include_router(r17.build_router(auth,conn))
    app.include_router(r19.build_router(auth,conn))
    with TestClient(app) as c:yield c,{'Authorization':'Bearer '+signed},database


def pair(site):
    c,h,_=site
    f=c.post('/api/admin/r17/forms',headers=h,json=FORM)
    assert f.status_code==201,f.text
    fid=f.json()['id']
    pub=c.post(f'/api/admin/r17/forms/{fid}/publish',headers=h)
    assert pub.status_code==200,pub.text
    p=c.post('/api/admin/r17/placements',headers=h,json={'form_id':fid,'name':'Планшет на выходе','medium':'kiosk'})
    assert p.status_code==201,p.text
    return p.json(), {'X-OSMANX-Voice-Key':p.json()['secret']}


def reply(c,placement,key,reqid):
    url=f"/api/voice/r17/{placement['public_id']}"
    cfg=c.get(url+'/form',headers=key)
    assert cfg.status_code==200,cfg.text
    opened=c.post(url+'/open',headers=key,json={'request_id':reqid,'version_hash':cfg.json()['version_hash']})
    assert opened.status_code==201,opened.text
    return c.post(url+'/submit',headers=key,json={'request_id':reqid,'version_hash':cfg.json()['version_hash'],'answers':{'purchase':'no','rating':4}})


def heartbeat(c,p,key,event='heartbeat-event-00001',queue=0):
    return c.post(f"/api/voice/r19/{p['public_id']}/heartbeat",headers=key,json={
      'request_id':event,'queue_depth':queue,'app_version':'r1.9','network_state':'recovering' if queue else 'online'})


def test_schedule_opt_in_and_legacy_default(site):
    c,h,_=site;p,key=pair(site);base=f"/api/admin/r19/placements/{p['id']}/schedule"
    legacy=c.get(base,headers=h).json()
    assert legacy['is_open'] and legacy['revision']==0 and not legacy['configured']
    hours={'expected_revision':0,'enabled':True,'weekdays':[0,1,2,3,4,5,6],'start':'10:00','end':'12:00'}
    res=c.put(base,headers=h,json=hours)
    assert res.status_code==200,res.text
    assert res.json()['revision']==1
    stale=c.put(base,headers=h,json=hours)
    assert stale.status_code==409
    # Disabled shifts forbid new opens and reading the form, but do not disable the placement key.
    disabled=c.put(base,headers=h,json={**hours,'expected_revision':1,'enabled':False})
    assert disabled.status_code==200
    assert c.get(f"/api/voice/r17/{p['public_id']}/form",headers=key).status_code==423
    assert c.post(f"/api/voice/r17/{p['public_id']}/open",headers=key,json={
        'request_id':'open-while-closed-001','version_hash':'0'*64}).status_code==423
    # Back online after removing the schedule restriction: no hidden dependence on local server TZ.
    ok=c.put(base,headers=h,json={**hours,'expected_revision':2,'enabled':True,'start':'00:00','end':'24:00'})
    assert ok.status_code==200 and ok.json()['is_open']
    assert reply(c,p,key,'test-response-after-reopen-1').status_code==201


def test_schedule_rejects_invalid_time_and_day(site):
    c,h,_=site;p,_=pair(site);u=f"/api/admin/r19/placements/{p['id']}/schedule"
    standard={'expected_revision':0,'enabled':True,'weekdays':[0,1],'start':'12:00','end':'08:00'}
    assert c.put(u,headers=h,json=standard).status_code==422
    assert c.put(u,headers=h,json={**standard,'start':'09:00','end':'bad'}).status_code==422
    assert c.put(u,headers=h,json={**standard,'weekdays':[0,0]}).status_code==422
    assert c.put(u,headers=h,json={**standard,'weekdays':[9]}).status_code==422
    assert c.get(u,headers=h).json()['revision']==0


def test_heartbeat_idempotency_rotation_and_fleet(site):
    c,h,db=site;p,key=pair(site)
    assert heartbeat(c,p,key).status_code==201
    assert heartbeat(c,p,key).json()['duplicate']
    bad=heartbeat(c,p,key,queue=1)
    assert bad.status_code==409
    assert heartbeat(c,p,{'X-OSMANX-Voice-Key':'wrong'},'heartbeat-untrusted-0001').status_code==401
    assert c.post(f"/api/voice/r19/{p['public_id']}/heartbeat",headers=key,json={
      'request_id':'heartbeat-oversize-001','queue_depth':50,'app_version':'r1.9','network_state':'online'}).status_code==422
    assert heartbeat(c,p,key,'heartbeat-event-00002',queue=7).status_code==201
    fleet=c.get('/api/admin/r19/fleet?slug=central',headers=h).json()
    assert fleet['online']==1 and fleet['items'][0]['health']['queue_depth']==7
    assert fleet['items'][0]['health']['app_version']=='r1.9'
    assert 'text/csv' in c.get('/api/admin/r19/fleet.csv?slug=central',headers=h).headers['content-type']
    with db.connect() as conn:
        old=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec='seconds')
        conn.execute('UPDATE field_heartbeat_r19 SET last_seen=?',(old,));conn.commit()
    assert c.get('/api/admin/r19/fleet?slug=central',headers=h).json()['items'][0]['health']['state']=='offline'
    rotation=c.post(f"/api/admin/r17/placements/{p['id']}/rotate",headers=h)
    assert rotation.status_code==200
    assert heartbeat(c,p,key,'heartbeat-old-key-test').status_code==401
    new_key={'X-OSMANX-Voice-Key':rotation.json()['secret']}
    assert heartbeat(c,p,new_key,'heartbeat-new-key-test').status_code==201
    assert c.post(f"/api/admin/r17/placements/{p['id']}/disable",headers=h).status_code==200
    assert heartbeat(c,p,new_key,'heartbeat-disabled-id').status_code==404


def test_voice_submission_after_closing_schedule_and_duplicate_not_counted(site):
    c,h,db=site;p,key=pair(site);u=f"/api/voice/r17/{p['public_id']}"
    v=c.get(u+'/form',headers=key).json()['version_hash'];rid='queued-retry-while-offline-0001'
    assert c.post(u+'/open',headers=key,json={'request_id':rid,'version_hash':v}).status_code==201
    schedule={'expected_revision':0,'enabled':False,'weekdays':[0,1,2,3,4,5,6],'start':'08:00','end':'20:00'}
    assert c.put(f"/api/admin/r19/placements/{p['id']}/schedule",headers=h,json=schedule).status_code==200
    sub={'request_id':rid,'version_hash':v,'answers':{'purchase':'no','rating':3}}
    assert c.post(u+'/submit',headers=key,json=sub).status_code==201
    again=c.post(u+'/submit',headers=key,json=sub)
    assert again.status_code==201 and again.json()['duplicate']
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM voice_responses_r17 WHERE request_id=?',(rid,)).fetchone()[0]==1


def test_quality_metrics_and_no_fabricated_conversion(site):
    c,h,db=site;p,key=pair(site)
    for i in range(5):assert reply(c,p,key,f'quality-measurement-{i:04}').status_code==201
    data=c.get('/api/admin/r19/quality?days=7',headers=h).json()
    assert data['items'][0]['opens']==5 and data['items'][0]['responses']==5
    assert data['items'][0]['completion_pct']==100.0 and data['items'][0]['fast_responses']==5
    assert 'unique' not in str(data).lower()
    assert c.get('/api/admin/r19/quality?days=31',headers=h).status_code==422
    csv=c.get('/api/admin/r19/quality.csv',headers=h)
    assert csv.status_code==200 and 'text/csv' in csv.headers['content-type']


def test_incident_creation_history_reopen_and_no_duplicate(site):
    c,h,db=site;p,key=pair(site)
    assert heartbeat(c,p,key,queue=8).status_code==201
    with db.connect() as conn:
        old=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec='seconds')
        conn.execute('UPDATE field_heartbeat_r19 SET last_seen=?',(old,));conn.commit()
    result=c.post('/api/admin/r19/incidents/sync',headers=h)
    assert result.status_code==200,result.text
    assert result.json()['signals']>=2
    incidents=c.get('/api/admin/r19/incidents',headers=h).json()['items']
    assert {x['signal'] for x in incidents}>={'offline','backlog'}
    assert c.post('/api/admin/r19/incidents/sync',headers=h).json()['created_or_reopened']==0
    inc=next(x for x in incidents if x['signal']=='backlog')
    route=f"/api/admin/r19/incidents/{inc['id']}"
    assert c.patch(route,headers=h,json={'status':'resolved','note':'Сразу закрываем без проверки'}).status_code==409
    ok=c.patch(route,headers=h,json={'status':'acknowledged','note':'Проверили сеть и осмотрели планшет'}); assert ok.status_code==200,ok.text
    done=c.patch(route,headers=h,json={'status':'resolved','note':'Очередь передана после восстановления интернета'})
    assert done.status_code==200,done.text
    assert c.post('/api/admin/r19/incidents/sync',headers=h).json()['created_or_reopened']==1
    history=c.get(route+'/history',headers=h).json()['items']
    assert [x['current_status'] for x in history]==['acknowledged','resolved','open']


def test_authorization_tenant_and_viewer(site):
    c,h,db=site;p,key=pair(site)
    assert c.get('/api/admin/r19/fleet').status_code==401
    from backend.security import hash_password,issue_session
    with db.connect() as conn:
        timestamp=datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',('other-shop','Другая компания',timestamp))
        other=conn.execute('SELECT id FROM organizations WHERE slug=?',('other-shop',)).fetchone()[0]
        conn.execute('INSERT INTO stores(slug,name,created_at,organization_id) VALUES(?,?,?,?)',('other-place','Чужая точка',timestamp,other))
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (other,'other-r19@osmanx.local',hash_password('other-super-secret-2026'),'owner',timestamp))
        conn.execute('INSERT INTO users(organization_id,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (1,'viewer-r19@osmanx.local',hash_password('viewer-super-secret-2026'),'viewer',timestamp))
        viewer=conn.execute("SELECT * FROM users WHERE email='viewer-r19@osmanx.local'").fetchone()
        conn.execute('INSERT INTO user_store_access(user_id,store_id) VALUES(?,?)',(viewer['id'],1))
        foreign=conn.execute("SELECT * FROM users WHERE email='other-r19@osmanx.local'").fetchone()
        vtoken=issue_session(viewer,SECRET);ftoken=issue_session(foreign,SECRET)
        conn.commit()
    v={'Authorization':'Bearer '+vtoken};f={'Authorization':'Bearer '+ftoken}
    assert c.get('/api/admin/r19/fleet',headers=v).status_code==200
    assert c.get('/api/admin/r19/fleet',headers=f).status_code==404
    assert c.put(f"/api/admin/r19/placements/{p['id']}/schedule",headers=v,json={
        'expected_revision':0,'enabled':True,'weekdays':[0],'start':'08:00','end':'20:00'}).status_code==403
    assert c.get(f"/api/admin/r19/placements/{p['id']}/schedule",headers=f).status_code==404
    assert c.post('/api/admin/r19/incidents/sync',headers=v).status_code==403
    assert c.get('/api/admin/r19/quality',headers=f).status_code==404


def test_repeat_schema_migration_keeps_answers(site):
    c,h,db=site;p,key=pair(site)
    assert reply(c,p,key,'migration-preserves-answers').status_code==201
    from backend.r19 import ensure_schema
    with db.connect() as conn:
        ensure_schema(conn);ensure_schema(conn)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert conn.execute('SELECT COUNT(*) FROM voice_responses_r17').fetchone()[0]==1


def test_legacy_r17_boot_without_field_schema(site):
    # Prior R1.8 fixtures intentionally initialize only R1.7 and R1.8 tables.
    # Default-open surveys must not fail when that older schema is loaded.
    c,h,db=site;p,key=pair(site)
    with db.connect() as conn:
        conn.execute('DROP TABLE field_schedule_r19');conn.commit()
    assert c.get(f"/api/voice/r17/{p['public_id']}/form",headers=key).status_code==200
    assert reply(c,p,key,'legacy-r17-scheme-form-001').status_code==201
